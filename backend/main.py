"""Persistent local demo API. Synthetic data only; authentication is a later section."""
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.database import SessionLocal, engine, get_session
from backend.fixtures import Appointment, DEMO_DATE, DOCTOR_ID, TENANT_ID, Status
from backend.models import AppointmentRecord, Patient, Practice, Practitioner
from backend.seed import seed_demo
from backend.patient_flow import router as patient_router, today
from backend.records import router as records_router
from backend.attachments import router as attachments_router
from backend.video import router as video_router
from backend.staff import router as staff_router, Staff, require_role, audit, web_write
from backend.admin import router as admin_router
from backend.encounters import router as encounter_router
from backend.models import StaffUser


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migrations are explicit: run `alembic upgrade head` before starting the API.
    with SessionLocal.begin() as session:
        seed_demo(session)
    yield
    engine.dispose()


app = FastAPI(title="Kerala Telemedicine Demo", version="0.7.0", lifespan=lifespan)
app.include_router(patient_router)
app.include_router(records_router)
app.include_router(attachments_router)
app.include_router(video_router)
app.include_router(staff_router)
app.include_router(admin_router)
app.include_router(encounter_router)
Db = Annotated[Session, Depends(get_session)]


@app.middleware('http')
async def private_api_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    # Never return connection URLs, SQL parameters or patient data in API errors.
    return JSONResponse(status_code=503, content={"detail": "The practice database is temporarily unavailable. Please retry."})


def serialize(record: AppointmentRecord, patient: Patient) -> Appointment:
    current = today()
    birth = patient.date_of_birth
    age = current.year - birth.year - ((current.month, current.day) < (birth.month, birth.day)) if birth else patient.demo_age
    return Appointment(id=record.id, patient_id=record.patient_id, patient=patient.name, age=age,
        visit_type=record.visit_type, time=record.start_time.strftime("%H:%M"),
        duration=record.duration, status=Status(record.status), reason=record.reason,
        initials=patient.initials, color=patient.color, patient_number=patient.patient_number)


@app.get("/api/health")
def health(session: Db):
    session.execute(text("SELECT 1"))
    return {"status": "ok", "mode": "demo", "database": "postgresql"}


@app.get("/api/dashboard")
def dashboard(session: Db, actor: Staff, day: date = date(2026, 10, 19), practitioner_id: str | None = None):
    practice = session.get(Practice, TENANT_ID)
    doctor_id = actor.practitioner_id if actor.role == "doctor" else practitioner_id
    doctor = session.get(Practitioner, (TENANT_ID, doctor_id)) if doctor_id else None
    doctors = session.scalars(select(Practitioner).join(StaffUser, (StaffUser.tenant_id == Practitioner.tenant_id) & (StaffUser.practitioner_id == Practitioner.id)).where(Practitioner.tenant_id == TENANT_ID, StaffUser.active.is_(True))).all()
    if not practice or (doctor_id and not doctor):
        raise HTTPException(503, "Demo setup is incomplete")
    conditions = [AppointmentRecord.tenant_id == TENANT_ID, AppointmentRecord.day == day]
    if doctor_id: conditions.append(AppointmentRecord.practitioner_id == doctor_id)
    rows = session.execute(select(AppointmentRecord, Patient).join(Patient,
        (AppointmentRecord.tenant_id == Patient.tenant_id) & (AppointmentRecord.patient_id == Patient.id))
        .where(*conditions)
        .order_by(AppointmentRecord.start_time, AppointmentRecord.id)).all()
    return {"practice": practice.name, "doctor": doctor.name if doctor else "All doctors", "user": {"name": actor.name, "role": actor.role}, "doctors": [{"id": d.id, "name": d.name} for d in doctors], "date": day,
        "demo_date": DEMO_DATE, "timezone": practice.timezone,
        "appointments": [{**serialize(record, patient).model_dump(), "reason": record.reason if actor.role != "medical_admin" else "Clinical details restricted", "practitioner_id": record.practitioner_id, "doctor": next((d.name for d in doctors if d.id == record.practitioner_id), "Doctor")} for record, patient in rows]}


@app.post("/api/appointments/{appointment_id}/check-in", response_model=Appointment)
def check_in(appointment_id: str, session: Db, actor: Staff, request: Request = None):
    if request is not None: web_write(request)
    # Row locking keeps concurrent check-ins and demo resets serialized.
    with session.begin():
        record = session.scalar(select(AppointmentRecord).where(
            AppointmentRecord.tenant_id == TENANT_ID,
            (AppointmentRecord.practitioner_id == actor.practitioner_id) if actor.role == "doctor" else True,
            AppointmentRecord.id == appointment_id).with_for_update())
        if record is None:
            raise HTTPException(404, "Appointment not found")
        if record.status == Status.completed.value:
            raise HTTPException(409, "A completed appointment cannot be checked in")
        if record.status != Status.waiting.value:
            record.status = Status.waiting.value
        patient = session.get(Patient, (TENANT_ID, record.patient_id))
        audit(session, actor, "appointment.check_in", record.id)
        result = serialize(record, patient)
        if actor.role == "medical_admin": result.reason = "Clinical details restricted"
    return result


@app.post("/api/demo/reset")
def reset_demo(session: Db, actor: Staff, request: Request):
    web_write(request)
    require_role(actor, "medical_admin")
    # Only the six fictional fixture records in this practice are restored.
    with session.begin():
        seed_demo(session, reset=True)
    return {"status": "reset"}
