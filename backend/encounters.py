"""Demonstration consultation consent and assigned-doctor encounter lifecycle."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.fixtures import TENANT_ID
from backend.models import AppointmentRecord, ConsultationConsent, Encounter, EncounterRevision, Patient, StaffUser, VideoRoom
from backend.patient_flow import account_for, web_request
from backend.staff import Staff, audit, require_role

router=APIRouter(prefix='/api',tags=['Consultation consent and notes'])
Db=Annotated[Session,Depends(get_session)]
CONSENT_VERSION='demo-consultation-en-v1'
CONSENT_TEXT=("I agree to take part in this fictional online consultation demonstration and to have the doctor save demonstration consultation notes. "
    "Remote consultations have limits: the doctor may recommend an in-person visit if an online assessment is unsuitable. "
    "I can ask questions or stop the call. This service is not for emergencies. No recording is enabled. "
    "This draft notice is for product review only; do not use real patient information or treat it as approved clinical consent.")

class ConsentInput(BaseModel):
    accepted: bool
    notice_version: str = Field(max_length=64)

class Notes(BaseModel):
    model_config=ConfigDict(extra='forbid')
    presenting_concern: str = Field(default='',max_length=8000)
    history: str = Field(default='',max_length=8000)
    assessment: str = Field(default='',max_length=8000)
    plan: str = Field(default='',max_length=8000)
    mode: Literal['video','audio','text']='video'
    suitability: Literal['not_assessed','suitable','in_person_required']='not_assessed'
    identity_checked: bool=False

    @field_validator('presenting_concern','history','assessment','plan')
    @classmethod
    def trim(cls,value): return value.strip()

class DraftInput(BaseModel):
    expected_version: int = Field(ge=0)
    note: Notes

class FinalizeInput(BaseModel):
    expected_version: int = Field(ge=1)
    confirm_finalization: bool

class AddendumInput(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3,max_length=500)
    text: str = Field(min_length=3,max_length=8000)

    @field_validator('reason','text')
    @classmethod
    def trim(cls,value):
        value=value.strip()
        if len(value)<3: raise ValueError('Please enter at least three characters')
        return value

def consent_record(session,appointment,room_id=None):
    conditions=[ConsultationConsent.tenant_id==appointment.tenant_id,ConsultationConsent.appointment_id==appointment.id,
        ConsultationConsent.patient_id==appointment.patient_id,ConsultationConsent.notice_version==CONSENT_VERSION]
    if room_id:
        conditions.append(or_(ConsultationConsent.method=='patient_session',ConsultationConsent.room_id==room_id))
    return session.scalar(select(ConsultationConsent).where(*conditions).order_by(ConsultationConsent.accepted_at.desc()).limit(1))

def consent_view(session,appointment,room_id=None):
    record=consent_record(session,appointment,room_id)
    return {'recorded':bool(record),'method':record.method if record else None,'accepted_at':record.accepted_at if record else None,
        'notice_version':CONSENT_VERSION,'notice_text':CONSENT_TEXT}

def record_consent(session,appointment,payload,method,scope_key,account_id=None,room_id=None):
    if not payload.accepted or payload.notice_version!=CONSENT_VERSION:
        raise HTTPException(422,'Read and accept the current demonstration consultation notice')
    session.refresh(appointment,with_for_update=True)
    if appointment.status=='completed': raise HTTPException(409,'This visit is already complete')
    record=session.scalar(select(ConsultationConsent).where(ConsultationConsent.tenant_id==appointment.tenant_id,
        ConsultationConsent.appointment_id==appointment.id,ConsultationConsent.method==method,
        ConsultationConsent.scope_key==scope_key,ConsultationConsent.notice_version==CONSENT_VERSION))
    if not record:
        record=ConsultationConsent(id=uuid4().hex,tenant_id=appointment.tenant_id,appointment_id=appointment.id,patient_id=appointment.patient_id,
            method=method,scope_key=scope_key,account_id=account_id,room_id=room_id,notice_version=CONSENT_VERSION,wording=CONSENT_TEXT)
        session.add(record);session.flush()
    return consent_view(session,appointment,room_id)

def assigned(session,actor,appointment_id,lock=False):
    require_role(actor,'doctor')
    query=select(AppointmentRecord).where(AppointmentRecord.tenant_id==actor.tenant_id,
        AppointmentRecord.id==appointment_id,AppointmentRecord.practitioner_id==actor.practitioner_id)
    if lock: query=query.with_for_update()
    appointment=session.scalar(query)
    if not appointment: raise HTTPException(404,'Appointment not found')
    return appointment

def view(session,appointment):
    encounter=session.get(Encounter,(appointment.tenant_id,appointment.id))
    patient=session.get(Patient,(appointment.tenant_id,appointment.patient_id))
    revisions=session.execute(select(EncounterRevision,StaffUser.name).join(StaffUser,StaffUser.id==EncounterRevision.author_id)
        .where(EncounterRevision.tenant_id==appointment.tenant_id,EncounterRevision.appointment_id==appointment.id)
        .order_by(EncounterRevision.version.desc()).limit(30)).all()
    return {'appointment_id':appointment.id,'patient_id':patient.id,'patient':patient.name,'patient_number':patient.patient_number,
        'appointment_status':appointment.status,'version':encounter.version if encounter else 0,
        'note':encounter.data if encounter else Notes().model_dump(),'finalized_at':encounter.finalized_at if encounter else None,
        'updated_at':encounter.updated_at if encounter else None,'consent':consent_view(session,appointment),
        'revisions':[{'version':r.version,'kind':r.kind,'author':name,'at':r.created_at,'data':r.data} for r,name in revisions]}

def revision(session,actor,encounter,kind,data):
    session.add(EncounterRevision(id=uuid4().hex,tenant_id=actor.tenant_id,appointment_id=encounter.appointment_id,
        version=encounter.version,kind=kind,author_id=actor.id,data=data))

@router.post('/patient/appointments/{appointment_id}/consent')
def patient_consent(appointment_id:str,payload:ConsentInput,request:Request,session:Db):
    web_request(request)
    with session.begin():
        account=account_for(request,session)
        appointment=session.get(AppointmentRecord,(TENANT_ID,appointment_id))
        if not appointment or appointment.patient_id!=account.patient_id: raise HTTPException(404,'Appointment not found')
        return record_consent(session,appointment,payload,'patient_session',account.id,account_id=account.id)

@router.get('/encounters/appointments/{appointment_id}')
def read(appointment_id:str,session:Db,actor:Staff):
    with session.begin():
        appointment=assigned(session,actor,appointment_id)
        audit(session,actor,'encounter.read',appointment_id)
        return view(session,appointment)

@router.get('/encounters/appointments/{appointment_id}/consent')
def status(appointment_id:str,session:Db,actor:Staff):
    appointment=assigned(session,actor,appointment_id)
    return consent_view(session,appointment)

@router.put('/encounters/appointments/{appointment_id}')
def save(appointment_id:str,payload:DraftInput,request:Request,session:Db,actor:Staff):
    web_request(request)
    with session.begin():
        appointment=assigned(session,actor,appointment_id,lock=True)
        encounter=session.get(Encounter,(actor.tenant_id,appointment_id))
        if appointment.status=='completed' or (encounter and encounter.finalized_at): raise HTTPException(409,'This note is finalized. Add an attributed addendum instead.')
        version=encounter.version if encounter else 0
        data=payload.note.model_dump()
        if encounter and data==encounter.data and payload.expected_version in (version,version-1): return view(session,appointment)
        if payload.expected_version!=version: raise HTTPException(409,'Another tab changed this note. Your text has been kept; review the saved version before retrying.')
        if not encounter:
            encounter=Encounter(tenant_id=actor.tenant_id,appointment_id=appointment_id,version=1,data=data)
            session.add(encounter)
        else: encounter.version+=1;encounter.data=data
        session.flush();revision(session,actor,encounter,'draft',{'note':data})
        audit(session,actor,'encounter.draft.save',appointment_id);session.flush()
        return view(session,appointment)

@router.post('/encounters/appointments/{appointment_id}/complete')
def complete(appointment_id:str,payload:FinalizeInput,request:Request,session:Db,actor:Staff):
    web_request(request)
    if not payload.confirm_finalization: raise HTTPException(422,'Confirm that you reviewed the note before completing the visit')
    rooms=[]
    with session.begin():
        appointment=assigned(session,actor,appointment_id,lock=True)
        encounter=session.get(Encounter,(actor.tenant_id,appointment_id))
        if not encounter: raise HTTPException(409,'Save your consultation note first')
        if encounter.finalized_at and payload.expected_version in (encounter.version,encounter.version-1): return view(session,appointment)
        if encounter.finalized_at or encounter.version!=payload.expected_version: raise HTTPException(409,'The saved note changed. Review the latest version before completion.')
        consent=consent_record(session,appointment)
        if not consent: raise HTTPException(409,'The patient must record consultation consent before this visit can be completed')
        note=Notes(**encounter.data)
        if not note.identity_checked or note.suitability=='not_assessed' or len(note.assessment)<3 or len(note.plan)<3:
            raise HTTPException(422,'Record identity check, remote-care suitability, assessment and plan before completing the visit')
        encounter.version+=1;encounter.finalized_at=datetime.now(timezone.utc);encounter.finalized_by=actor.id
        revision(session,actor,encounter,'finalized',{'note':encounter.data,'consent_id':consent.id,'consent_method':consent.method})
        appointment.status='completed'
        rooms=session.scalars(select(VideoRoom).where(VideoRoom.tenant_id==actor.tenant_id,VideoRoom.appointment_id==appointment_id,VideoRoom.ended_at.is_(None))).all()
        for room in rooms: room.ended_at=encounter.finalized_at
        keys=[room.id for room in rooms]
        audit(session,actor,'encounter.finalize',appointment_id);session.flush();result=view(session,appointment)
    from backend.video import hub
    for key in keys: hub.end(key)
    return result

@router.post('/encounters/appointments/{appointment_id}/addenda')
def addendum(appointment_id:str,payload:AddendumInput,request:Request,session:Db,actor:Staff):
    web_request(request)
    with session.begin():
        appointment=assigned(session,actor,appointment_id,lock=True)
        encounter=session.get(Encounter,(actor.tenant_id,appointment_id))
        if not encounter or not encounter.finalized_at: raise HTTPException(409,'Addenda are available only after finalization')
        if encounter.version!=payload.expected_version: raise HTTPException(409,'A newer addendum exists. Reload before adding yours.')
        encounter.version+=1
        revision(session,actor,encounter,'addendum',{'reason':payload.reason,'text':payload.text})
        audit(session,actor,'encounter.addendum',appointment_id);session.flush()
        return view(session,appointment)
