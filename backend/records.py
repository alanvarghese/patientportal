"""Read-only doctor-side patient directory for the fixed local demo practice."""
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from backend.database import get_session
from backend.fixtures import TENANT_ID
from backend.models import AppointmentRecord, ConsentRecord, Patient, PatientAccount
from backend.patient_flow import today
from backend.staff import Staff, patient_scope, ensure_patient_access

router = APIRouter(prefix="/api/records/patients", tags=["Doctor patient records demo"])
Db = Annotated[Session, Depends(get_session)]


def registered_expression():
    return exists(select(PatientAccount.id).where(PatientAccount.tenant_id == Patient.tenant_id, PatientAccount.patient_id == Patient.id))


def patient_summary(patient: Patient, registered: bool):
    birth = patient.date_of_birth
    current = today()
    age = current.year - birth.year - ((current.month, current.day) < (birth.month, birth.day)) if birth else patient.demo_age
    return {"id": patient.id, "patient_number": patient.patient_number, "name": patient.name,
        "age": age, "date_of_birth": birth, "phone": patient.phone, "email": patient.email,
        "language": patient.language, "initials": patient.initials, "color": patient.color,
        "source": "registered" if registered else "sample"}


@router.get("")
def directory(session: Db, actor: Staff, q: str = Query(default="", max_length=100),
              source: Literal["all", "registered", "sample"] = "all",
              offset: int = Query(default=0, ge=0), limit: int = Query(default=10, ge=1, le=50)):
    registered = registered_expression()
    conditions = [Patient.tenant_id == TENANT_ID, patient_scope(actor)]
    if q.strip():
        # Search text is a literal substring, not an SQL LIKE wildcard expression.
        term = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{term}%"
        conditions.append(or_(Patient.name.ilike(pattern, escape="\\"), Patient.patient_number.ilike(pattern, escape="\\"), Patient.phone.ilike(pattern, escape="\\")))
    if source != "all":
        conditions.append(registered if source == "registered" else ~registered)
    total = session.scalar(select(func.count()).select_from(Patient).where(*conditions))
    practice_total = session.scalar(select(func.count()).select_from(Patient).where(Patient.tenant_id == TENANT_ID, patient_scope(actor)))
    registered_count = session.scalar(select(func.count()).select_from(Patient).where(Patient.tenant_id == TENANT_ID, patient_scope(actor), registered))
    rows = session.execute(select(Patient, registered.label("registered")).where(*conditions).order_by(func.lower(Patient.name), Patient.id).offset(offset).limit(limit)).all()
    ids = [patient.id for patient, _ in rows]
    counts = dict(session.execute(select(AppointmentRecord.patient_id, func.count()).where(AppointmentRecord.tenant_id == TENANT_ID, AppointmentRecord.patient_id.in_(ids), (AppointmentRecord.practitioner_id == actor.practitioner_id) if actor.role == "doctor" else True).group_by(AppointmentRecord.patient_id)).all()) if ids else {}
    return {"patients": [{**patient_summary(patient, is_registered), "appointment_count": counts.get(patient.id, 0)} for patient, is_registered in rows],
        "total": total, "offset": offset, "limit": limit, "practice_total": practice_total,
        "registered_count": registered_count, "sample_count": practice_total - registered_count}


@router.get("/{patient_id}")
def detail(patient_id: str, session: Db, actor: Staff,
           history_offset: int = Query(default=0, ge=0), history_limit: int = Query(default=10, ge=1, le=50)):
    patient = ensure_patient_access(session, actor, patient_id)
    if not patient:
        raise HTTPException(404, "Patient record not found")
    is_registered = session.scalar(select(registered_expression()).select_from(Patient).where(Patient.tenant_id == TENANT_ID, Patient.id == patient_id))
    base = [AppointmentRecord.tenant_id == TENANT_ID, AppointmentRecord.patient_id == patient_id]
    if actor.role == "doctor": base.append(AppointmentRecord.practitioner_id == actor.practitioner_id)
    count = session.scalar(select(func.count()).select_from(AppointmentRecord).where(*base))
    completed = session.scalar(select(func.count()).select_from(AppointmentRecord).where(*base, AppointmentRecord.status == "completed"))
    rows = session.scalars(select(AppointmentRecord).where(*base).order_by(AppointmentRecord.day.desc(), AppointmentRecord.start_time.desc(), AppointmentRecord.id).offset(history_offset).limit(history_limit)).all()
    registration = session.scalar(select(ConsentRecord.accepted_at).where(ConsentRecord.tenant_id == TENANT_ID, ConsentRecord.patient_id == patient_id, ConsentRecord.purpose == "demo_registration").order_by(ConsentRecord.accepted_at).limit(1))
    return {"patient": patient_summary(patient, bool(is_registered)), "registration_recorded_at": registration, "registration_recorded_on": registration.astimezone(ZoneInfo("Asia/Kolkata")).date() if registration else None,
        "appointment_count": count, "completed_count": completed, "history_offset": history_offset,
        "history_limit": history_limit, "appointments": [{"id": a.id, "day": a.day,
            "time": a.start_time.strftime("%H:%M"), "duration": a.duration, "visit_type": a.visit_type,
            "reason": a.reason if actor.role != "medical_admin" else "Clinical details restricted", "status": a.status, "booking_reference": a.booking_reference,
            "fee_paise": a.fee_paise, "payment_status": a.payment_status} for a in rows]}
