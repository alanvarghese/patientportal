"""Run with the project's venv after migrations. Writes private login details."""
import json
from datetime import date, time
from pathlib import Path
import secrets
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.database import SessionLocal
from backend.staff_seed import DEMO_STAFF, seed_staff
from backend.seed import seed_demo
from backend.fixtures import DEMO_DATE, TENANT_ID
from backend.models import AppointmentRecord

path=ROOT/'.local/staff-demo-accounts.json'
path.parent.mkdir(parents=True,exist_ok=True)
if not path.exists():
    accounts=[dict(username=u,name=n,role=r,practitioner_id=p,password=secrets.token_urlsafe(15)) for u,n,r,p in DEMO_STAFF]
    path.write_text(json.dumps(accounts,indent=2));path.chmod(0o600)
accounts=json.loads(path.read_text())
with SessionLocal.begin() as session:
    seed_demo(session)
    seed_staff(session,accounts)
    if not session.get(AppointmentRecord,(TENANT_ID,'demo-faisal-first')):
        session.add(AppointmentRecord(id='demo-faisal-first',tenant_id=TENANT_ID,patient_id='patient-a6',practitioner_id='demo-doctor-2',day=date.fromisoformat(DEMO_DATE),start_time=time(12,0),duration=20,visit_type='Follow-up',reason='Fictional follow-up appointment',status='confirmed'))
details=ROOT/'.local/staff-logins.txt'
details.write_text('Fictional staff demo accounts\nSign in: https://patientportal.lemmanet.com/login\nThe existing shared site password is still required first.\n\n'+'\n\n'.join(f"{a['name']} ({a['role']})\nUsername: {a['username']}\nPassword: {a['password']}" for a in accounts))
details.chmod(0o600)
print('Demo staff provisioned. Credentials saved privately in .local/staff-logins.txt.')
