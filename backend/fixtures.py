"""Fictional sample data for the local demonstration."""
from enum import Enum
from pydantic import BaseModel

DEMO_DATE = "2026-10-19"
TENANT_ID = "demo-practice"
DOCTOR_ID = "demo-doctor"

class Status(str, Enum):
    confirmed = "confirmed"
    waiting = "waiting"
    completed = "completed"


class Appointment(BaseModel):
    id: str
    patient_id: str | None = None
    patient: str
    age: int
    visit_type: str
    time: str
    duration: int = 20
    status: Status
    reason: str
    initials: str
    color: str
    patient_number: str


def fixtures() -> list[Appointment]:
    rows = [
        ("a1", "Anjali Menon", 34, "Follow-up", "09:00", Status.completed, "Review of previous consultation", "AM", "rose"),
        ("a2", "Muhammed Basheer", 58, "Follow-up", "09:30", Status.completed, "Routine follow-up visit", "MB", "sand"),
        ("a3", "Meera Nair", 42, "First visit", "10:00", Status.waiting, "Discuss recent symptoms and uploaded reports", "MN", "lilac"),
        ("a4", "Arjun Pillai", 29, "First visit", "10:30", Status.confirmed, "Initial consultation", "AP", "blue"),
        ("a5", "Ayisha Rahman", 65, "Follow-up", "11:00", Status.confirmed, "Review progress and care plan", "AR", "rose"),
        ("a6", "Fathima Ali", 37, "Follow-up", "11:30", Status.confirmed, "Scheduled follow-up", "FA", "sand"),
    ]
    return [Appointment(id=r[0], patient=r[1], age=r[2], visit_type=r[3], time=r[4], status=r[5], reason=r[6], initials=r[7], color=r[8], patient_number=f"DEMO-{i + 1:04}") for i, r in enumerate(rows)]

