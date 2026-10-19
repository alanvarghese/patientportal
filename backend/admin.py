"""Medical-admin demographic registration and appointment coordination."""
from datetime import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import field_validator
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.fixtures import TENANT_ID
from backend.models import AppointmentRecord, Patient, PatientAccount, SlotHold, StaffUser
from backend.patient_flow import ProfileInput, PhoneInput, HoldInput, FEE, booking_view, lock_slot, now, slot_times, today
from backend.staff import Staff, audit, ensure_patient_access, require_role, web_write

router=APIRouter(prefix='/api/admin',tags=['Medical administration'])
Db=Annotated[Session,Depends(get_session)]

class Registration(ProfileInput):
    phone: str

    # Reuse the exact mobile validation used by patient sign-in.
    @field_validator('phone')
    @classmethod
    def phone_check(cls,value): return PhoneInput.normalize_phone(value)

class AdminBooking(HoldInput):
    patient_id: str

def active_doctor(session, doctor_id):
    if not session.scalar(select(StaffUser.id).where(StaffUser.tenant_id==TENANT_ID,StaffUser.practitioner_id==doctor_id,StaffUser.active.is_(True),StaffUser.role=='doctor')):
        raise HTTPException(422,'Choose an active doctor')

@router.post('/patients')
def register(payload: Registration, request: Request, session: Db, actor: Staff):
    require_role(actor,'medical_admin');web_write(request)
    if not payload.accept_privacy: raise HTTPException(422,'Confirm the patient agreed to this fictional demo registration')
    with session.begin():
        session.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':'registration:'+payload.phone})
        account=session.scalar(select(PatientAccount).where(PatientAccount.tenant_id==TENANT_ID,PatientAccount.phone==payload.phone).with_for_update())
        if account and account.patient_id: raise HTTPException(409,'This sign-in mobile already has a patient profile. Open that record instead.')
        current=today();birth=payload.date_of_birth
        patient=Patient(id=uuid4().hex,tenant_id=TENANT_ID,patient_number=f"PT-{session.scalar(text("SELECT nextval('patient_number_seq')")):06d}",
            name=payload.name,date_of_birth=birth,demo_age=current.year-birth.year-((current.month,current.day)<(birth.month,birth.day)),phone=payload.phone,email=payload.email or None,
            language=payload.language,initials=''.join(p[0] for p in payload.name.split()[:2]).upper(),color='sand')
        session.add(patient);session.flush()
        if not account:
            account=PatientAccount(id=uuid4().hex,tenant_id=TENANT_ID,phone=payload.phone)
            session.add(account)
        account.patient_id=patient.id
        audit(session,actor,'patient.register',patient.id)
        result={'id':patient.id,'name':patient.name,'patient_number':patient.patient_number}
    return result

@router.patch('/patients/{patient_id}')
def update(patient_id: str, payload: Registration, request: Request, session: Db, actor: Staff):
    require_role(actor,'medical_admin');web_write(request)
    with session.begin():
        patient=ensure_patient_access(session,actor,patient_id)
        patient.name=payload.name;patient.date_of_birth=payload.date_of_birth
        patient.phone=payload.phone;patient.email=payload.email or None;patient.language=payload.language
        patient.initials=''.join(p[0] for p in payload.name.split()[:2]).upper()
        audit(session,actor,'patient.demographics.update',patient.id)
    return {'id':patient_id,'status':'updated'}

@router.post('/appointments')
def book(payload: AdminBooking, request: Request, session: Db, actor: Staff):
    require_role(actor,'medical_admin');web_write(request)
    try: start=time.fromisoformat(payload.start_time)
    except ValueError: raise HTTPException(422,'Choose a valid appointment time')
    if start not in slot_times(payload.day): raise HTTPException(422,'Choose a future practice slot within 30 days')
    with session.begin():
        ensure_patient_access(session,actor,payload.patient_id);active_doctor(session,payload.practitioner_id)
        lock_slot(session,payload.day,start,payload.practitioner_id)
        if session.scalar(select(AppointmentRecord.id).where(AppointmentRecord.tenant_id==TENANT_ID,AppointmentRecord.practitioner_id==payload.practitioner_id,AppointmentRecord.day==payload.day,AppointmentRecord.start_time==start)):
            raise HTTPException(409,'That doctor is already booked at this time')
        if session.scalar(select(SlotHold.id).where(SlotHold.tenant_id==TENANT_ID,SlotHold.practitioner_id==payload.practitioner_id,SlotHold.day==payload.day,SlotHold.start_time==start,SlotHold.expires_at>now(),SlotHold.appointment_id.is_(None))):
            raise HTTPException(409,'A patient is currently holding that time')
        record=AppointmentRecord(id=uuid4().hex,tenant_id=TENANT_ID,patient_id=payload.patient_id,practitioner_id=payload.practitioner_id,day=payload.day,start_time=start,duration=20,
            visit_type=payload.visit_type,reason=payload.reason,status='confirmed',fee_paise=FEE,payment_status='not_collected_demo',
            booking_reference=f"BK-{payload.day:%Y%m%d}-{session.scalar(text("SELECT nextval('booking_number_seq')")):06d}")
        session.add(record);session.flush();audit(session,actor,'appointment.book',record.id)
        result=booking_view(record,session)
    return result
