"""Run against an isolated temporary schema in the local PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time
from pathlib import Path
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from alembic.config import Config
from backend.tests.client import TestClient, TEST_PASSWORD
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

import backend.main as main
from backend.database import database_url, engine, get_session
from backend.fixtures import DOCTOR_ID, TENANT_ID
from backend.models import AppointmentRecord, Patient, Practice, Practitioner
from backend.seed import seed_demo
from backend.staff_seed import DEMO_STAFF, seed_staff
from backend.staff import Actor
from backend.models import StaffUser


class PostgresTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = "test_" + uuid4().hex
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{cls.schema}"'))
        cls.test_engine = create_engine(database_url, connect_args={"options": f"-csearch_path={cls.schema}"})
        cls.sessions = sessionmaker(cls.test_engine, expire_on_commit=False)
        config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
        with cls.test_engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "head")
        cls.session_patch = patch.object(main, "SessionLocal", cls.sessions)
        cls.engine_patch = patch.object(main, "engine", cls.test_engine)
        cls.session_patch.start()
        cls.engine_patch.start()
        def test_session():
            with cls.sessions() as session:
                yield session
        main.app.dependency_overrides[get_session] = test_session

    @classmethod
    def tearDownClass(cls):
        main.app.dependency_overrides.clear()
        cls.session_patch.stop()
        cls.engine_patch.stop()
        cls.test_engine.dispose()
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{cls.schema}" CASCADE'))

    def setUp(self):
        with self.sessions.begin() as session:
            seed_demo(session, reset=True)
            seed_staff(session,[dict(username=u,name=n,role=r,practitioner_id=p,password=TEST_PASSWORD) for u,n,r,p in DEMO_STAFF])
            user=session.scalar(select(StaffUser).where(StaffUser.username=='dr.asha'))
            self.actor=Actor(user.id,user.tenant_id,user.name,user.role,user.practitioner_id)


class DatabaseTests(PostgresTestCase):
    def test_api_and_restart_persistence(self):
        with TestClient(main.app) as client:
            self.assertEqual(client.get("/api/health").json()["database"], "postgresql")
            self.assertEqual(len(client.get("/api/dashboard").json()["appointments"]), 6)
            self.assertEqual(client.get("/api/dashboard?day=2026-10-20").json()["appointments"], [])
            self.assertEqual(client.get("/api/dashboard?day=invalid").status_code, 422)
            self.assertEqual(client.post("/api/appointments/a4/check-in").json()["status"], "waiting")
            self.assertEqual(client.post("/api/appointments/a4/check-in").json()["status"], "waiting")
            self.assertEqual(client.post("/api/appointments/a1/check-in").status_code, 409)
            self.assertEqual(client.post("/api/appointments/missing/check-in").status_code, 404)
        # A new API lifespan/connection pool must not overwrite persisted state.
        with TestClient(main.app) as client:
            item = next(a for a in client.get("/api/dashboard").json()["appointments"] if a["id"] == "a4")
            self.assertEqual(item["status"], "waiting")
            client.post('/api/staff/login',json={'username':'admin','password':TEST_PASSWORD})
            self.assertEqual(client.post("/api/demo/reset").status_code, 200)
            item = next(a for a in client.get("/api/dashboard").json()["appointments"] if a["id"] == "a4")
            self.assertEqual(item["status"], "confirmed")

    def test_concurrent_check_ins(self):
        def check_in(_):
            with self.sessions() as session:
                return main.check_in("a4", session, self.actor).status.value
        with ThreadPoolExecutor(max_workers=6) as executor:
            self.assertEqual(list(executor.map(check_in, range(12))), ["waiting"] * 12)
        with self.sessions() as session:
            count = session.scalar(select(func.count()).select_from(AppointmentRecord).where(AppointmentRecord.tenant_id == TENANT_ID))
            self.assertEqual(count, 6)

    def test_constraints_and_tenant_scoping(self):
        with self.sessions.begin() as session:
            if not session.get(Practice, "other-practice"):
                session.add(Practice(id="other-practice", name="Other", timezone="Asia/Kolkata"))
                session.flush()
                session.add(Practitioner(tenant_id="other-practice", id=DOCTOR_ID, name="Other doctor"))
                session.add(Patient(tenant_id="other-practice", id="other-patient", patient_number="OTHER-1", name="Other patient", demo_age=40, initials="OP", color="blue"))
                session.flush()
                session.add(AppointmentRecord(tenant_id="other-practice", id="a4", patient_id="other-patient", practitioner_id=DOCTOR_ID, day=date(2026,10,19), start_time=time(10,30), duration=20, visit_type="First visit", reason="Test", status="confirmed"))
        with self.sessions() as session:
            main.check_in("a4", session, self.actor)
        with self.sessions() as session:
            self.assertEqual(session.get(AppointmentRecord, ("other-practice", "a4")).status, "confirmed")
        with TestClient(main.app) as client:
            self.assertEqual(len(client.get("/api/dashboard").json()["appointments"]), 6)
        with self.assertRaises(IntegrityError), self.sessions.begin() as session:
            session.add(AppointmentRecord(tenant_id=TENANT_ID, id="bad-reference", patient_id="other-patient", practitioner_id=DOCTOR_ID, day=date(2026,10,19), start_time=time(13), duration=20, visit_type="First visit", reason="Test", status="confirmed"))
        with self.assertRaises(IntegrityError), self.sessions.begin() as session:
            session.add(AppointmentRecord(tenant_id=TENANT_ID, id="duplicate-slot", patient_id="patient-a4", practitioner_id=DOCTOR_ID, day=date(2026,10,19), start_time=time(10,30), duration=20, visit_type="First visit", reason="Test", status="confirmed"))
        with self.assertRaises(IntegrityError), self.sessions.begin() as session:
            item = session.get(AppointmentRecord, (TENANT_ID,"a4"))
            item.status = "invalid"


if __name__ == "__main__":
    unittest.main()
