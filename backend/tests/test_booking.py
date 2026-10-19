from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from contextlib import ExitStack
import unittest

from backend.tests.client import TestClient
from sqlalchemy import delete, func, select

from backend.main import app
from backend.fixtures import TENANT_ID
from backend.models import AppointmentRecord, ConsentRecord, OtpChallenge, Patient, PatientAccount, PatientSession, SlotHold
from backend.patient_flow import today, now
from backend.tests.test_database import PostgresTestCase

HEADERS = {"X-Practice-Client": "portal"}


class BookingTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        with self.sessions.begin() as session:
            for model in [SlotHold, ConsentRecord, PatientSession, OtpChallenge, PatientAccount]:
                session.execute(delete(model))
            session.execute(delete(AppointmentRecord).where(AppointmentRecord.booking_reference.is_not(None)))
            session.execute(delete(Patient).where(Patient.phone.is_not(None)))
        self.day = today() + timedelta(days=2)
        while self.day.weekday() == 6:
            self.day += timedelta(days=1)

    def login(self, client, phone="9876500001"):
        result = client.post("/api/patient/otp/challenges", json={"phone": phone})
        self.assertEqual(result.status_code, 200, result.text)
        challenge = result.json()
        result = client.post("/api/patient/otp/verify", json={"challenge_id": challenge["challenge_id"], "code": challenge["demo_code"]})
        self.assertEqual(result.status_code, 200, result.text)
        return challenge

    def register(self, client, phone="9876500001", name="Demo Patient"):
        self.login(client, phone)
        payload = {"name": name, "date_of_birth": "1990-01-15", "email": "shared@example.com", "language": "English", "accept_privacy": True}
        result = client.post("/api/patient/profile", json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json(), payload

    def hold(self, client, time="09:00"):
        return client.post("/api/patient/holds", json={"day": self.day.isoformat(), "start_time": time, "visit_type": "First visit", "reason": "Fictional routine consultation"})

    def test_registration_booking_persistence_and_retry(self):
        with TestClient(app, headers=HEADERS) as client:
            profile, payload = self.register(client)
            self.assertNotEqual(profile["id"], payload["email"])
            self.assertTrue(profile["patient_number"].startswith("PT-"))
            self.assertEqual(client.post("/api/patient/profile", json=payload).json()["id"], profile["id"])
            available = client.get(f"/api/patient/availability?day={self.day}").json()
            self.assertEqual(len(available["slots"]), 8)
            hold = self.hold(client).json()
            self.assertEqual(self.hold(client).json()["hold_id"], hold["hold_id"])
            self.assertEqual(client.post(f'/api/patient/holds/{hold["hold_id"]}/confirm', json={"accept_terms": False}).status_code, 422)
            result = client.post(f'/api/patient/holds/{hold["hold_id"]}/confirm', json={"accept_terms": True})
            self.assertEqual(result.status_code, 200, result.text)
            booking = result.json()
            self.assertEqual(booking["payment_status"], "not_collected_demo")
            retry = client.post(f'/api/patient/holds/{hold["hold_id"]}/confirm', json={"accept_terms": True}).json()
            self.assertEqual(retry["id"], booking["id"])
            self.assertEqual(client.get("/api/patient/me").json()["bookings"][0]["reference"], booking["reference"])
            self.assertEqual(client.get(f"/api/dashboard?day={self.day}").json()["appointments"][0]["patient"], profile["name"])
            cookie = client.cookies.get("practice_patient")
        with TestClient(app, headers=HEADERS) as client:
            client.cookies.set("practice_patient", cookie, path="/api/patient")
            self.assertEqual(client.get("/api/patient/me").json()["profile"]["id"], profile["id"])
            self.assertEqual(client.get("/api/patient/me").json()["bookings"][0]["id"], booking["id"])
            client.post("/api/demo/reset")
            self.assertEqual(client.get("/api/patient/me").json()["bookings"][0]["id"], booking["id"])
            self.assertEqual(self.hold(client).status_code, 409)
            self.assertEqual(client.post("/api/patient/logout").status_code, 200)
            self.assertEqual(client.get("/api/patient/me").status_code, 401)
        with self.sessions() as session:
            self.assertEqual(session.scalar(select(func.count()).select_from(ConsentRecord)), 2)
            self.assertEqual(session.scalar(select(func.count()).select_from(AppointmentRecord).where(AppointmentRecord.booking_reference.is_not(None))), 1)

    def test_verification_and_profile_validation(self):
        with TestClient(app, headers=HEADERS) as client:
            self.assertEqual(client.get("/api/patient/me").status_code, 401)
            self.assertEqual(client.post("/api/patient/otp/challenges", json={"phone":"123"}).status_code, 422)
            challenge = client.post("/api/patient/otp/challenges", json={"phone":"9876500001"}).json()
            self.assertEqual(client.post("/api/patient/otp/challenges", json={"phone":"9876500001"}).status_code, 429)
            wrong = "000000" if challenge["demo_code"] != "000000" else "111111"
            for _ in range(5):
                self.assertEqual(client.post("/api/patient/otp/verify", json={"challenge_id":challenge["challenge_id"],"code":wrong}).status_code, 400)
            self.assertEqual(client.post("/api/patient/otp/verify", json={"challenge_id":challenge["challenge_id"],"code":challenge["demo_code"]}).status_code, 400)
            used = self.login(client, "9876500002")
            self.assertEqual(client.post("/api/patient/otp/verify",json={"challenge_id":used["challenge_id"],"code":used["demo_code"]}).status_code,400)
            expired = client.post("/api/patient/otp/challenges",json={"phone":"9876500004"}).json()
            with self.sessions.begin() as session:
                session.get(OtpChallenge, expired["challenge_id"]).expires_at = now() - timedelta(seconds=1)
            self.assertEqual(client.post("/api/patient/otp/verify",json={"challenge_id":expired["challenge_id"],"code":expired["demo_code"]}).status_code,400)
            payload = {"name":"Test Adult","date_of_birth":"1990-01-01","accept_privacy":False}
            self.assertEqual(client.post("/api/patient/profile",json=payload).status_code,422)
            payload["accept_privacy"] = True
            payload["date_of_birth"] = today().isoformat()
            self.assertEqual(client.post("/api/patient/profile",json=payload).status_code,422)
            payload["date_of_birth"] = "1990-01-01"
            payload["email"] = "bad-email"
            self.assertEqual(client.post("/api/patient/profile",json=payload).status_code,422)
            payload["email"] = ""
            self.assertEqual(client.post("/api/patient/profile",json=payload).status_code,200)
            payload["name"] = "Different person"
            self.assertEqual(client.post("/api/patient/profile",json=payload).status_code,409)
        with TestClient(app) as client:
            self.assertEqual(client.post("/api/patient/otp/challenges",json={"phone":"9876500003"},headers={"X-Practice-Client":""}).status_code,403)

    def test_expiry_reclaim_and_ownership(self):
        with TestClient(app, headers=HEADERS) as first, TestClient(app, headers=HEADERS) as second:
            p1, _ = self.register(first)
            p2, _ = self.register(second, "9876500002", "Second Patient")
            self.assertNotEqual(p1["id"],p2["id"])  # Sharing optional email never merges identities.
            hold = self.hold(first).json()
            self.assertEqual(self.hold(second).status_code,409)
            self.assertEqual(second.post(f'/api/patient/holds/{hold["hold_id"]}/confirm',json={"accept_terms":True}).status_code,404)
            self.assertEqual(second.get("/api/patient/me").json()["bookings"],[])
            with self.sessions.begin() as session:
                item = session.scalar(select(SlotHold).where(SlotHold.token == hold["hold_id"]))
                item.expires_at = now() - timedelta(seconds=1)
            self.assertEqual(first.post(f'/api/patient/holds/{hold["hold_id"]}/confirm',json={"accept_terms":True}).status_code,409)
            new_hold = self.hold(second).json()
            self.assertNotEqual(new_hold["hold_id"],hold["hold_id"])
            self.assertEqual(first.post(f'/api/patient/holds/{hold["hold_id"]}/confirm',json={"accept_terms":True}).status_code,404)
            self.assertEqual(second.delete(f'/api/patient/holds/{new_hold["hold_id"]}').status_code,200)
            self.assertEqual(self.hold(first).status_code,200)
            self.assertEqual(first.post('/api/patient/holds',json={"day":self.day.isoformat(),"start_time":"13:00","visit_type":"First visit","reason":"Test"}).status_code,422)

    def test_competing_holds_and_parallel_confirmation(self):
        with ExitStack() as stack:
            clients = [stack.enter_context(TestClient(app,headers=HEADERS)) for _ in range(4)]
            for i, client in enumerate(clients):
                self.register(client, f"987650000{i+1}", f"Demo Person {i}")
            with ThreadPoolExecutor(max_workers=4) as executor:
                results = list(executor.map(self.hold,clients))
            self.assertEqual(sorted(r.status_code for r in results), [200,409,409,409])
            winner = next(i for i,r in enumerate(results) if r.status_code == 200)
            token = results[winner].json()["hold_id"]
            def confirm(_):
                return clients[winner].post(f"/api/patient/holds/{token}/confirm",json={"accept_terms":True})
            with ThreadPoolExecutor(max_workers=4) as executor:
                confirmations = list(executor.map(confirm,range(4)))
            self.assertEqual([r.status_code for r in confirmations],[200]*4)
            self.assertEqual(len({r.json()["id"] for r in confirmations}),1)


if __name__ == '__main__':
    unittest.main()
