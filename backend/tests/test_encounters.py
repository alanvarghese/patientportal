from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient as RawClient
from sqlalchemy import delete, func, select

from backend.main import app
from backend.encounters import CONSENT_VERSION
from backend.models import ConsultationConsent, Encounter, EncounterRevision, StaffAudit, VideoRoom
from backend.tests.client import TestClient, TEST_PASSWORD
from backend.tests.test_database import PostgresTestCase

H={'X-Practice-Client':'portal'}
NOTE={'presenting_concern':'Fictional demo concern','history':'Fictional history only','assessment':'Demonstration assessment',
      'plan':'Demonstration advice, no real treatment','mode':'video','suitability':'suitable','identity_checked':True}

class EncounterTests(PostgresTestCase):
    def setUp(self):
        with self.sessions.begin() as s:
            for model in (EncounterRevision,Encounter,ConsultationConsent,VideoRoom):s.execute(delete(model))
        super().setUp()

    def consent(self,client):
        room=client.post('/api/video/appointments/a4/prepare').json()
        r=client.post('/api/video/consent',json={'token':room['guest_token'],'accepted':True,'notice_version':CONSENT_VERSION})
        self.assertEqual(r.status_code,200,r.text)
        return room

    def test_guest_consent_is_explicit_versioned_and_required_for_media(self):
        with TestClient(app,headers=H) as client,patch('backend.video.cloudflare_servers',return_value=None):
            room=client.post('/api/video/appointments/a4/prepare').json()
            guest={'token':room['guest_token'],'connection_id':'e'*32}
            self.assertEqual(client.post('/api/video/connect',json=guest).status_code,409)
            self.assertEqual(client.post('/api/video/consent',json={'token':room['token'],'accepted':True,'notice_version':CONSENT_VERSION}).status_code,403)
            for accepted,version in [(False,CONSENT_VERSION),(True,'outdated')]:
                self.assertEqual(client.post('/api/video/consent',json={'token':room['guest_token'],'accepted':accepted,'notice_version':version}).status_code,422)
            for _ in range(2):
                r=client.post('/api/video/consent',json={'token':room['guest_token'],'accepted':True,'notice_version':CONSENT_VERSION})
                self.assertEqual(r.status_code,200,r.text)
                self.assertEqual(r.json()['method'],'demo_guest')
            self.assertEqual(client.post('/api/video/connect',json=guest).status_code,200)
            with self.sessions() as s:self.assertEqual(s.scalar(select(func.count()).select_from(ConsultationConsent)),1)
            client.post('/api/video/end',json={'token':room['token']})
            new=client.post('/api/video/appointments/a4/prepare').json()
            self.assertFalse(client.post('/api/video/info',json={'token':new['guest_token']}).json()['consent']['recorded'])

    def test_draft_conflict_finalization_addendum_and_reset_protection(self):
        path='/api/encounters/appointments/a4'
        with TestClient(app,headers=H) as client:
            self.assertEqual(client.get(path).json()['version'],0)
            r=client.put(path,json={'expected_version':0,'note':NOTE})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['version'],1)
            self.assertEqual(client.put(path,json={'expected_version':0,'note':{**NOTE,'assessment':'Stale content'}}).status_code,409)
            self.assertEqual(client.post(path+'/complete',json={'expected_version':1,'confirm_finalization':True}).status_code,409)
            room=self.consent(client)
            self.assertEqual(client.post(path+'/complete',json={'expected_version':1,'confirm_finalization':False}).status_code,422)
            r=client.post(path+'/complete',json={'expected_version':1,'confirm_finalization':True})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['appointment_status'],'completed')
            self.assertEqual(r.json()['version'],2)
            self.assertEqual(client.post(path+'/complete',json={'expected_version':1,'confirm_finalization':True}).status_code,200)
            self.assertEqual(client.put(path,json={'expected_version':2,'note':NOTE}).status_code,409)
            self.assertEqual(client.post('/api/video/info',json={'token':room['guest_token']}).status_code,410)
            r=client.post(path+'/addenda',json={'expected_version':2,'reason':'Demo clarification','text':'Additional fictional detail'})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['version'],3)
            self.assertEqual(r.json()['note'],NOTE)
            self.assertEqual(client.post(path+'/addenda',json={'expected_version':2,'reason':'Stale addendum','text':'Stale content'}).status_code,409)
            client.post('/api/staff/login',json={'username':'admin','password':TEST_PASSWORD})
            self.assertEqual(client.post('/api/demo/reset').status_code,200)
            client.post('/api/staff/login',json={'username':'dr.asha','password':TEST_PASSWORD})
            self.assertEqual(client.get(path).json()['appointment_status'],'completed')
            with self.sessions() as s:
                snapshots=s.scalars(select(EncounterRevision).where(EncounterRevision.appointment_id=='a4').order_by(EncounterRevision.version)).all()
                self.assertEqual([v.kind for v in snapshots],['draft','finalized','addendum'])
                self.assertEqual(snapshots[1].data['note'],NOTE)
                self.assertIn('consent_id',snapshots[1].data)
                self.assertIsNotNone(s.scalar(select(StaffAudit.id).where(StaffAudit.action=='encounter.finalize')))

    def test_roles_assignment_and_completion_requirements(self):
        path='/api/encounters/appointments/a4'
        with RawClient(app,headers=H) as anonymous:
            self.assertEqual(anonymous.get(path).status_code,401)
        for role in ('medical_admin','nurse'):
            with TestClient(app,headers=H,role=role) as c:
                self.assertEqual(c.get(path).status_code,403)
                self.assertEqual(c.put(path,json={'expected_version':0,'note':NOTE}).status_code,403)
                self.assertEqual(c.post(path+'/complete',json={'expected_version':1,'confirm_finalization':True}).status_code,403)
        with TestClient(app,headers=H) as client:
            client.post('/api/staff/login',json={'username':'dr.faisal','password':TEST_PASSWORD})
            self.assertEqual(client.get(path).status_code,404)
            client.post('/api/staff/login',json={'username':'dr.asha','password':TEST_PASSWORD})
            self.consent(client)
            self.assertEqual(client.put(path,json={'expected_version':0,'note':{}}).status_code,200)
            self.assertEqual(client.post(path+'/complete',json={'expected_version':1,'confirm_finalization':True}).status_code,422)
            self.assertEqual(client.post('/api/encounters/appointments/a1/addenda',json={'expected_version':1,'reason':'Demo reason','text':'Demo text'}).status_code,409)

    def test_concurrent_edits_keep_one_version_and_persist(self):
        path='/api/encounters/appointments/a4'
        with TestClient(app,headers=H) as first, TestClient(app,headers=H) as second:
            def save(item):
                c,assessment=item
                return c.put(path,json={'expected_version':0,'note':{**NOTE,'assessment':assessment}}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(save,[(first,'First tab assessment'),(second,'Second tab assessment')]))
            self.assertEqual(sorted(results),[200,409])
        with TestClient(app,headers=H) as restarted:
            result=restarted.get(path).json()
            self.assertEqual(result['version'],1)
            self.assertEqual(len(result['revisions']),1)

    def test_patient_session_consent_is_owned_and_distinct_from_guest(self):
        with RawClient(app,headers=H) as client:
            otp=client.post('/api/patient/otp/challenges',json={'phone':'9876500187'}).json()
            client.post('/api/patient/otp/verify',json={'challenge_id':otp['challenge_id'],'code':otp['demo_code']})
            client.post('/api/patient/profile',json={'name':'Demo Patient Consent','date_of_birth':'1990-01-01','accept_privacy':True})
            settings=client.get('/api/patient/config').json();day=date.fromisoformat(settings['today'])+timedelta(days=1)
            while day.weekday()==6:day+=timedelta(days=1)
            held=client.post('/api/patient/holds',json={'day':str(day),'start_time':'11:00','visit_type':'First visit','reason':'Fictional consent test'}).json()
            booked=client.post('/api/patient/holds/'+held['hold_id']+'/confirm',json={'accept_terms':True}).json()
            payload={'accepted':True,'notice_version':CONSENT_VERSION}
            self.assertEqual(client.post('/api/patient/appointments/a4/consent',json=payload).status_code,404)
            r=client.post('/api/patient/appointments/'+booked['id']+'/consent',json=payload)
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['method'],'patient_session')
            self.assertEqual(client.get('/api/encounters/appointments/'+booked['id']).status_code,401)
