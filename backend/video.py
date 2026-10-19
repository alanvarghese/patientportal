"""Two-party demo WebRTC signaling. Media is never handled by this API."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
from pathlib import Path
import json
import os
import secrets
from threading import Lock
from time import monotonic
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.fixtures import DOCTOR_ID, TENANT_ID
from backend.models import AppointmentRecord, Patient, VideoRoom
from backend.patient_flow import account_for, web_request
from backend.turn import cloudflare_servers
from backend.staff import Staff, lookup_staff, require_role
from backend.encounters import ConsentInput, consent_view, record_consent

router=APIRouter(prefix='/api',tags=['WebRTC demo'])
Db=Annotated[Session,Depends(get_session)]
KEY_PATH=Path(__file__).resolve().parents[1]/'.local'/'video-signing.key'


def now(): return datetime.now(timezone.utc)


def signing_key():
    KEY_PATH.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        fd=os.open(KEY_PATH,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'wb') as f:f.write(secrets.token_bytes(32))
    except FileExistsError:pass
    return KEY_PATH.read_bytes()


def grant(room,role):
    payload=f'{room.id}.{role}.{int(room.expires_at.timestamp())}'
    return payload+'.'+hmac_new(signing_key(),payload.encode(),sha256).hexdigest()


def authorize(session,token,request):
    parts=token.split('.')
    if len(parts)!=4 or parts[1] not in ('doctor','patient'):raise HTTPException(401,'Invalid call invitation')
    payload='.'.join(parts[:3])
    if not compare_digest(hmac_new(signing_key(),payload.encode(),sha256).hexdigest(),parts[3]):raise HTTPException(401,'Invalid call invitation')
    room=session.get(VideoRoom,parts[0])
    if not room or room.tenant_id!=TENANT_ID or str(int(room.expires_at.timestamp()))!=parts[2]:raise HTTPException(401,'Invalid call invitation')
    if room.ended_at or room.expires_at<=now():raise HTTPException(410,'This call has ended or its invitation has expired')
    appointment=session.get(AppointmentRecord,(TENANT_ID,room.appointment_id))
    if not appointment or appointment.status=='completed':raise HTTPException(409,'This appointment is not available for a call')
    if parts[1] == "doctor":
        actor=lookup_staff(request,session)
        require_role(actor,"doctor")
        if actor.practitioner_id != appointment.practitioner_id: raise HTTPException(404,"Appointment not found")
    return room,parts[1]


def prepare(session,appointment):
    session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'video:'+appointment.id})
    room=session.scalar(select(VideoRoom).where(VideoRoom.tenant_id==TENANT_ID,VideoRoom.appointment_id==appointment.id,VideoRoom.ended_at.is_(None),VideoRoom.expires_at>now()))
    if not room:
        room=VideoRoom(id=uuid4().hex,tenant_id=TENANT_ID,appointment_id=appointment.id,expires_at=now()+timedelta(hours=2))
        session.add(room);session.flush()
    patient=session.get(Patient,(TENANT_ID,appointment.patient_id))
    return room,patient


class TokenInput(BaseModel):
    token:str=Field(max_length=256)


class GuestConsentInput(TokenInput, ConsentInput):
    pass


class ConnectInput(TokenInput):
    connection_id:str=Field(pattern=r'^[a-f0-9]{32}$')


class MessageInput(ConnectInput):
    type:Literal['offer','answer','ice']
    call_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    data:dict


class Hub:
    def __init__(self):self.rooms={};self.lock=Lock()
    def room(self,key):
        # Ephemeral SDP/ICE is memory-only, bounded and removed after inactivity.
        current=monotonic()
        for old in list(self.rooms):
            if current-self.rooms[old]['touched']>7200:del self.rooms[old]
        return self.rooms.setdefault(key,{'peers':{},'messages':[],'seq':0,'touched':current})
    def emit(self,r,target,type,data=None,call_id=None):
        r['seq']+=1;r['messages'].append({'seq':r['seq'],'target':target,'type':type,'data':data,'call_id':call_id})
        r['messages']=r['messages'][-256:]
    def expire(self,r):
        for role in list(r['peers']):
            if monotonic()-r['peers'][role]['seen']>20:
                del r['peers'][role];self.emit(r,'patient' if role=='doctor' else 'doctor','peer-left')
    def connect(self,key,role,cid):
        with self.lock:
            r=self.room(key);self.expire(r)
            existing=r['peers'].get(role)
            if existing and existing['id']!=cid:raise HTTPException(409,f'The {role} is already connected in another tab. Leave that call first or wait 20 seconds.')
            r['peers'][role]={'id':cid,'seen':monotonic()};r['touched']=monotonic()
            if len(r['peers'])==2:self.emit(r,'doctor','peer-ready')
            return {'cursor':r['seq'],'peer_present':len(r['peers'])==2}
    def member(self,r,role,cid):
        self.expire(r)
        if r['peers'].get(role,{}).get('id')!=cid:raise HTTPException(409,'Connection expired. Select Reconnect.')
        r['peers'][role]['seen']=monotonic();r['touched']=monotonic()
    def poll(self,key,role,cid,after):
        with self.lock:
            r=self.room(key);self.member(r,role,cid)
            return {'cursor':r['seq'],'messages':[{k:v for k,v in m.items() if k!='target'} for m in r['messages'] if m['seq']>after and m['target']==role]}
    def send(self,key,role,cid,message):
        with self.lock:
            r=self.room(key);self.member(r,role,cid)
            self.emit(r,'patient' if role=='doctor' else 'doctor',message.type,message.data,message.call_id)
    def leave(self,key,role,cid):
        with self.lock:
            r=self.room(key)
            if r['peers'].get(role,{}).get('id')==cid:
                del r['peers'][role];self.emit(r,'patient' if role=='doctor' else 'doctor','peer-left')
    def end(self,key):
        with self.lock:self.rooms.pop(key,None)


hub=Hub()


@router.post('/video/appointments/{appointment_id}/prepare')
def doctor_prepare(appointment_id:str,request:Request,session:Db,actor:Staff):
    require_role(actor,"doctor")
    web_request(request)
    with session.begin():
        appointment=session.get(AppointmentRecord,(TENANT_ID,appointment_id))
        if not appointment or appointment.practitioner_id!=actor.practitioner_id:raise HTTPException(404,'Appointment not found')
        if appointment.status=='completed':raise HTTPException(409,'Completed appointments cannot start a call')
        room,patient=prepare(session,appointment)
        return {'room_id':room.id,'token':grant(room,'doctor'),'guest_token':grant(room,'patient'),'patient':patient.name,'expires_at':room.expires_at}


@router.post('/patient/appointments/{appointment_id}/video')
def patient_prepare(appointment_id:str,request:Request,session:Db):
    web_request(request)
    with session.begin():
        account=account_for(request,session)
        appointment=session.get(AppointmentRecord,(TENANT_ID,appointment_id))
        if not appointment or appointment.patient_id!=account.patient_id:raise HTTPException(404,'Appointment not found')
        if appointment.status=='completed':raise HTTPException(409,'Completed appointments cannot join a call')
        room,patient=prepare(session,appointment)
        return {'room_id':room.id,'token':grant(room,'patient'),'patient':patient.name,'expires_at':room.expires_at}


@router.post('/video/info')
def info(payload:TokenInput,request:Request,session:Db):
    web_request(request);room,role=authorize(session,payload.token,request)
    servers=[]
    stun=[u.strip() for u in os.environ.get('WEBRTC_STUN_URLS','').split(',') if u.strip()]
    if stun:servers.append({'urls':stun})
    turn=[u.strip() for u in os.environ.get('WEBRTC_TURN_URLS','').split(',') if u.strip()]
    user=os.environ.get('WEBRTC_TURN_USERNAME','');password=os.environ.get('WEBRTC_TURN_CREDENTIAL','')
    enabled=bool(turn and user and password)
    if enabled:servers.append({'urls':turn,'username':user,'credential':password})
    managed=cloudflare_servers(room.id,role)
    if managed:
        servers=managed;enabled=True
    appointment=session.get(AppointmentRecord,(room.tenant_id,room.appointment_id))
    return {'room_id':room.id,'appointment_id':room.appointment_id,'role':role,'ice_servers':servers,'turn_configured':enabled,'expires_at':room.expires_at,'consent':consent_view(session,appointment,room.id)}


@router.post('/video/consent')
def guest_consent(payload:GuestConsentInput,request:Request,session:Db):
    web_request(request)
    with session.begin():
        room,role=authorize(session,payload.token,request)
        if role!='patient':raise HTTPException(403,'Only the patient can acknowledge consultation consent')
        appointment=session.get(AppointmentRecord,(room.tenant_id,room.appointment_id))
        return record_consent(session,appointment,payload,'demo_guest',room.id,room_id=room.id)


def require_patient_consent(session,room,role):
    appointment=session.get(AppointmentRecord,(room.tenant_id,room.appointment_id))
    if role=='patient' and not consent_view(session,appointment,room.id)['recorded']:
        raise HTTPException(409,'Please read and accept the consultation notice before joining')


@router.post('/video/connect')
def connect(payload:ConnectInput,request:Request,session:Db):
    web_request(request);room,role=authorize(session,payload.token,request)
    require_patient_consent(session,room,role)
    return hub.connect(room.id,role,payload.connection_id)


@router.post('/video/poll')
def poll(payload:ConnectInput,request:Request,session:Db,after:int=Query(0,ge=0)):
    web_request(request);room,role=authorize(session,payload.token,request)
    require_patient_consent(session,room,role)
    return hub.poll(room.id,role,payload.connection_id,after)


@router.post('/video/signal')
def signal(payload:MessageInput,request:Request,session:Db):
    web_request(request);room,role=authorize(session,payload.token,request)
    require_patient_consent(session,room,role)
    if len(json.dumps(payload.data))>65536:raise HTTPException(413,'Signaling message too large')
    if (payload.type=='offer' and role!='doctor') or (payload.type=='answer' and role!='patient'):raise HTTPException(403,'Invalid signaling role')
    hub.send(room.id,role,payload.connection_id,payload)
    return {'status':'sent'}


@router.post('/video/leave')
def leave(payload:ConnectInput,request:Request,session:Db):
    web_request(request);room,role=authorize(session,payload.token,request)
    hub.leave(room.id,role,payload.connection_id)
    return {'status':'left'}


@router.post('/video/end')
def end(payload:TokenInput,request:Request,session:Db):
    web_request(request)
    with session.begin():
        room,role=authorize(session,payload.token,request)
        if role!='doctor':raise HTTPException(403,'Only the doctor can end the room for everyone')
        room.ended_at=now();key=room.id
    hub.end(key)
    return {'status':'ended'}
