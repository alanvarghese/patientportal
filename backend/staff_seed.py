"""Explicit provisioning for fictional demo staff; never a public signup route."""
from uuid import uuid4
from sqlalchemy import select
from backend.fixtures import DOCTOR_ID, TENANT_ID
from backend.models import Practitioner, StaffUser
from backend.staff import hash_password

DEMO_STAFF = [
    ('dr.asha', 'Dr Asha Menon', 'doctor', DOCTOR_ID),
    ('dr.faisal', 'Dr Faisal Rahman', 'doctor', 'demo-doctor-2'),
    ('admin', 'Safiya Ahmed', 'medical_admin', None),
    ('nurse', 'Nurse Maria Thomas', 'nurse', None),
]

def seed_staff(session, accounts):
    for item in accounts:
        if item['practitioner_id']:
            doctor = session.get(Practitioner, (TENANT_ID,item['practitioner_id']))
            if not doctor:
                doctor = Practitioner(tenant_id=TENANT_ID,id=item['practitioner_id'],name=item['name'])
                session.add(doctor)
            doctor.name=item['name']
            session.flush()
        user=session.scalar(select(StaffUser).where(StaffUser.tenant_id==TENANT_ID,StaffUser.username==item['username']))
        if not user:
            session.add(StaffUser(id=uuid4().hex,tenant_id=TENANT_ID,username=item['username'],name=item['name'],
                role=item['role'],practitioner_id=item['practitioner_id'],password_hash=hash_password(item['password'])))
    session.flush()
