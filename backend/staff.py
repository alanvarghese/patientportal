"""Individual staff authentication and practice/assignment access checks."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256, scrypt
from hmac import compare_digest
import os
import secrets
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import exists, select, delete
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.fixtures import TENANT_ID
from backend.models import AppointmentRecord, Patient, StaffAudit, StaffSession, StaffUser

router = APIRouter(prefix='/api/staff', tags=['Staff access'])
Db = Annotated[Session, Depends(get_session)]
COOKIE = 'practice_staff'

def now(): return datetime.now(timezone.utc)
def digest(value): return sha256(value.encode()).hexdigest()

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${value}'

def password_matches(password, stored):
    try:
        algorithm, salt, _ = stored.split('$')
        return algorithm == 'scrypt' and compare_digest(hash_password(password, salt), stored)
    except (ValueError, TypeError): return False

@dataclass(frozen=True)
class Actor:
    id: str
    tenant_id: str
    name: str
    role: str
    practitioner_id: str | None

def lookup_staff(request, session):
    token = request.cookies.get(COOKIE)
    login = session.get(StaffSession, digest(token)) if token else None
    user = session.get(StaffUser, login.user_id) if login and login.expires_at > now() else None
    if not user or not user.active or user.tenant_id != TENANT_ID:
        raise HTTPException(401, 'Please sign in to your staff account')
    return Actor(user.id, user.tenant_id, user.name, user.role, user.practitioner_id)

def get_staff(request: Request, session: Db):
    # Finish this read transaction before handlers open their write transactions.
    with session.begin(): return lookup_staff(request, session)

Staff = Annotated[Actor, Depends(get_staff)]

def require_role(actor, *roles):
    if actor.role not in roles: raise HTTPException(403, 'Your role does not allow this action')

def patient_scope(actor):
    if actor.role != 'doctor': return Patient.tenant_id == actor.tenant_id
    return exists(select(AppointmentRecord.id).where(AppointmentRecord.tenant_id == actor.tenant_id,
        AppointmentRecord.patient_id == Patient.id, AppointmentRecord.practitioner_id == actor.practitioner_id))

def ensure_patient_access(session, actor, patient_id, clinical=False):
    if clinical: require_role(actor, 'doctor', 'nurse')
    patient = session.scalar(select(Patient).where(Patient.tenant_id == actor.tenant_id, Patient.id == patient_id, patient_scope(actor)))
    if not patient: raise HTTPException(404, 'Patient record not found')
    return patient

def audit(session, actor, action, target):
    session.add(StaffAudit(id=uuid4().hex, tenant_id=actor.tenant_id, user_id=actor.id, action=action, target_id=target))

class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)

def web_write(request):
    if request.headers.get('x-practice-client') != 'portal': raise HTTPException(403, 'Please use the practice portal')

@router.post('/login')
def login(payload: LoginInput, request: Request, response: Response, session: Db):
    web_write(request)
    token = None
    with session.begin():
        user = session.scalar(select(StaffUser).where(StaffUser.tenant_id == TENANT_ID,
            StaffUser.username == payload.username.strip().lower()).with_for_update())
        if user and user.active and (not user.locked_until or user.locked_until <= now()):
            if password_matches(payload.password, user.password_hash):
                user.failed_logins, user.locked_until = 0, None
                token = secrets.token_urlsafe(32)
                session.execute(delete(StaffSession).where(StaffSession.expires_at <= now()))
                session.add(StaffSession(token_hash=digest(token), user_id=user.id, expires_at=now()+timedelta(hours=8)))
                result = asdict(Actor(user.id,user.tenant_id,user.name,user.role,user.practitioner_id))
            else:
                user.failed_logins += 1
                if user.failed_logins >= 5:
                    user.locked_until = now()+timedelta(minutes=15)
                    user.failed_logins = 0
        else:
            # Keep unknown/locked usernames on a password-hash work path too.
            hash_password(payload.password, '00'*16)
    if not token: raise HTTPException(401, 'Sign-in failed. Check your credentials or wait 15 minutes after repeated attempts.')
    response.set_cookie(COOKIE,token,httponly=True,secure=os.environ.get('DEMO_SECURE_COOKIES')=='1',samesite='lax',max_age=28800,path='/api')
    response.headers['Cache-Control']='no-store'
    return result

@router.get('/me')
def me(actor: Staff): return asdict(actor)

@router.post('/logout')
def logout(request: Request, response: Response, session: Db):
    web_write(request)
    token=request.cookies.get(COOKIE)
    with session.begin():
        if token: session.execute(delete(StaffSession).where(StaffSession.token_hash==digest(token)))
    response.delete_cookie(COOKIE,path='/api')
    return {'status':'signed_out'}
