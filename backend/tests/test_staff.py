from datetime import date, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from backend.main import app
from backend.models import AppointmentRecord, StaffUser, StaffSession, StaffAudit, Patient, PatientAccount
from backend.staff import digest, now
from backend.tests.client import TEST_PASSWORD
from backend.tests.test_database import PostgresTestCase

H={'X-Practice-Client':'portal'}

class StaffTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        with self.sessions.begin() as session:
            session.execute(delete(StaffSession))
            session.execute(update(StaffUser).values(failed_logins=0,locked_until=None,active=True))

    def login(self,client,username):
        r=client.post('/api/staff/login',headers=H,json={'username':username,'password':TEST_PASSWORD})
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def test_login_logout_expiry_and_lockout(self):
        with TestClient(app) as client:
            for path in ('/api/dashboard','/api/records/patients','/api/records/patients/patient-a4/attachments'):
                self.assertEqual(client.get(path).status_code,401)
            self.assertEqual(client.post('/api/staff/login',json={'username':'admin','password':TEST_PASSWORD}).status_code,403)
            user=self.login(client,'admin')
            self.assertEqual(user['role'],'medical_admin')
            self.assertNotIn('password_hash',user)
            token=client.cookies.get('practice_staff')
            with self.sessions() as session:
                self.assertIsNotNone(session.get(StaffSession,digest(token)))
                self.assertIsNone(session.get(StaffSession,token))
            self.assertEqual(client.post('/api/staff/logout',headers=H).status_code,200)
            self.assertEqual(client.get('/api/staff/me').status_code,401)
            client.cookies.set('practice_staff',token)
            self.assertEqual(client.get('/api/staff/me').status_code,401)
            client.cookies.clear()
            self.login(client,'admin')
            with self.sessions.begin() as session:
                session.execute(update(StaffSession).values(expires_at=now()-timedelta(seconds=1)))
            self.assertEqual(client.get('/api/staff/me').status_code,401)
            for _ in range(5):
                self.assertEqual(client.post('/api/staff/login',headers=H,json={'username':'admin','password':'incorrect'}).status_code,401)
            self.assertEqual(client.post('/api/staff/login',headers=H,json={'username':'admin','password':TEST_PASSWORD}).status_code,401)

    def test_doctor_assignment_and_admin_clinical_restrictions(self):
        with self.sessions.begin() as session:
            session.get(AppointmentRecord,('demo-practice','a4')).practitioner_id='demo-doctor-2'
        with TestClient(app,headers=H) as client:
            self.login(client,'dr.asha')
            self.assertEqual(len(client.get('/api/dashboard').json()['appointments']),5)
            self.assertEqual(len(client.get('/api/dashboard?practitioner_id=demo-doctor-2').json()['appointments']),5)
            self.assertEqual(client.get('/api/records/patients/patient-a4').status_code,404)
            self.assertEqual(client.get('/api/records/patients/patient-a4/attachments').status_code,404)
            self.assertEqual(client.post('/api/video/appointments/a4/prepare').status_code,404)
            self.assertEqual(client.post('/api/appointments/a4/check-in').status_code,404)
            self.login(client,'dr.faisal')
            self.assertEqual(len(client.get('/api/dashboard').json()['appointments']),1)
            ids={p['id'] for p in client.get('/api/records/patients').json()['patients']}
            self.assertIn('patient-a4',ids)
            self.assertNotIn('patient-a1',ids)
            room=client.post('/api/video/appointments/a4/prepare').json()
            self.assertIn('token',room)
            self.login(client,'dr.asha')
            self.assertEqual(client.post('/api/video/info',json={'token':room['token']}).status_code,404)
            self.login(client,'admin')
            self.assertEqual(client.get('/api/records/patients/patient-a4/attachments').status_code,403)
            self.assertEqual(client.get('/api/records/patients/patient-a4/attachments/unknown/content').status_code,403)
            self.assertEqual(client.get('/api/records/patients/patient-a4').json()['appointments'][0]['reason'],'Clinical details restricted')
            self.assertEqual(client.post('/api/video/appointments/a4/prepare').status_code,403)
            self.assertEqual(client.post('/api/video/info',json={'token':room['token']}).status_code,403)
            self.login(client,'nurse')
            self.assertEqual(client.get('/api/records/patients/patient-a4/attachments').status_code,200)
            self.assertEqual(client.post('/api/appointments/a4/check-in').status_code,200)
            self.assertEqual(client.post('/api/demo/reset').status_code,403)
            self.assertEqual(client.post('/api/video/appointments/a4/prepare').status_code,403)

    def test_admin_registration_booking_and_patient_mobile_sign_in(self):
        payload={'name':'Demo Hiba Rahman','date_of_birth':'1992-05-10','phone':'9876500099','email':'','language':'Malayalam','accept_privacy':True}
        with TestClient(app,headers=H) as client:
            self.login(client,'nurse')
            self.assertEqual(client.post('/api/admin/patients',json=payload).status_code,403)
            self.login(client,'admin')
            r=client.post('/api/admin/patients',json=payload)
            self.assertEqual(r.status_code,200,r.text)
            patient=r.json()
            self.assertEqual(client.post('/api/admin/patients',json=payload).status_code,409)
            self.assertEqual(client.patch('/api/admin/patients/'+patient['id'],json={**payload,'email':'shared@example.test'}).status_code,200)
            settings=client.get('/api/patient/config').json()
            day=date.fromisoformat(settings['today'])+timedelta(days=1)
            while day.weekday()==6:day+=timedelta(days=1)
            booking={'patient_id':patient['id'],'practitioner_id':'demo-doctor-2','day':day.isoformat(),'start_time':'09:00','visit_type':'First visit','reason':'Fictional demo booking'}
            booked=client.post('/api/admin/appointments',json=booking)
            self.assertEqual(booked.status_code,200,booked.text)
            self.assertEqual(booked.json()['doctor'],'Dr Faisal Rahman')
            self.assertEqual(client.post('/api/admin/appointments',json=booking).status_code,409)
            # Different doctors can have the same time, while each doctor's slot stays unique.
            self.assertEqual(client.post('/api/admin/appointments',json={**booking,'practitioner_id':'demo-doctor'}).status_code,200)
            self.login(client,'dr.faisal')
            self.assertEqual(client.get('/api/records/patients/'+patient['id']).status_code,200)
            self.assertEqual(client.patch('/api/admin/patients/'+patient['id'],json=payload).status_code,403)
            otp=client.post('/api/patient/otp/challenges',json={'phone':payload['phone']}).json()
            r=client.post('/api/patient/otp/verify',json={'challenge_id':otp['challenge_id'],'code':otp['demo_code']})
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['profile']['id'],patient['id'])
            with self.sessions() as session:
                actions=list(session.scalars(select(StaffAudit.action).where(StaffAudit.target_id==patient['id'])))
                self.assertIn('patient.register',actions)
                self.assertIn('patient.demographics.update',actions)

    def test_patient_self_booking_selects_doctor(self):
        # Exercise actual OTP/profile APIs, without a staff session.
        with TestClient(app,headers=H) as client:
            otp=client.post('/api/patient/otp/challenges',json={'phone':'9876500088'}).json()
            client.post('/api/patient/otp/verify',json={'challenge_id':otp['challenge_id'],'code':otp['demo_code']})
            p=client.post('/api/patient/profile',json={'name':'Demo Patient','date_of_birth':'1990-01-01','language':'English','accept_privacy':True})
            self.assertEqual(p.status_code,200,p.text)
            settings=client.get('/api/patient/config').json()
            day=date.fromisoformat(settings['today'])+timedelta(days=2)
            while day.weekday()==6:day+=timedelta(days=1)
            hold=client.post('/api/patient/holds',json={'practitioner_id':'demo-doctor-2','day':str(day),'start_time':'10:00','visit_type':'First visit','reason':'Fictional test visit'})
            self.assertEqual(hold.status_code,200,hold.text)
            result=client.post('/api/patient/holds/'+hold.json()['hold_id']+'/confirm',json={'accept_terms':True})
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['practitioner_id'],'demo-doctor-2')
            self.assertEqual(client.get('/api/dashboard').status_code,401)
