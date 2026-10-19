"""Idempotent sample enrollment and explicit fixture reset, in a transaction."""
from datetime import date, time

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.fixtures import DEMO_DATE, DOCTOR_ID, TENANT_ID, fixtures
from backend.models import AppointmentRecord, Patient, Practice, Practitioner, Encounter


def seed_demo(session: Session, *, reset: bool = False):
    # Serialize startup/reset across API workers. Released automatically on commit/rollback.
    session.execute(text("SELECT pg_advisory_xact_lock(7126041901)"))
    practice = session.get(Practice, TENANT_ID)
    if practice and not reset:
        return
    if not practice:
        session.add(Practice(id=TENANT_ID, name="Your practice", timezone="Asia/Kolkata"))
        session.flush()
    if not session.get(Practitioner, (TENANT_ID, DOCTOR_ID)):
        session.add(Practitioner(tenant_id=TENANT_ID, id=DOCTOR_ID, name="Doctor"))
        session.flush()
    for item in fixtures():
        patient_id = f"patient-{item.id}"
        patient = session.get(Patient, (TENANT_ID, patient_id))
        if not patient:
            patient = Patient(tenant_id=TENANT_ID, id=patient_id)
            session.add(patient)
        patient.name, patient.demo_age = item.patient, item.age
        patient.patient_number, patient.initials, patient.color = item.patient_number, item.initials, item.color
        session.flush()
        appointment = session.get(AppointmentRecord, (TENANT_ID, item.id))
        encounter = session.get(Encounter, (TENANT_ID, item.id))
        if not appointment:
            appointment = AppointmentRecord(tenant_id=TENANT_ID, id=item.id)
            session.add(appointment)
        if encounter and encounter.finalized_at:
            continue  # Demo reset must never reopen a finalized clinical encounter.
        appointment.patient_id, appointment.practitioner_id = patient_id, DOCTOR_ID
        appointment.day, appointment.start_time = date.fromisoformat(DEMO_DATE), time.fromisoformat(item.time)
        appointment.duration, appointment.visit_type = item.duration, item.visit_type
        appointment.reason, appointment.status = item.reason, item.status.value
    session.flush()
