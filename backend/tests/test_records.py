from datetime import date, datetime, time, timedelta, timezone
from backend.tests.client import TestClient

from backend.main import app
from backend.fixtures import TENANT_ID, DOCTOR_ID
from backend.models import AppointmentRecord, ConsentRecord, Patient, PatientAccount, Practice, Practitioner
from backend.tests.test_database import PostgresTestCase


class PatientRecordsTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        with self.sessions.begin() as session:
            if not session.get(Patient, (TENANT_ID, 'rtest-patient')):
                session.add(Patient(tenant_id=TENANT_ID,id='rtest-patient',patient_number='PT-RECORD',name='Demo Record Patient',demo_age=36,date_of_birth=date(1990,1,15),phone='+919876500099',email='optional@example.com',language='Malayalam',initials='DR',color='blue'))
                session.flush()
                session.add(PatientAccount(id='rtest-account',tenant_id=TENANT_ID,patient_id='rtest-patient',phone='+919876500099'))
                session.flush()
                session.add(ConsentRecord(id='rtest-consent',tenant_id=TENANT_ID,patient_id='rtest-patient',account_id='rtest-account',purpose='demo_registration',version='demo-v1',wording='Test agreement',accepted_at=datetime(2026,10,18,21,tzinfo=timezone.utc)))
                for i in range(12):
                    session.add(AppointmentRecord(tenant_id=TENANT_ID,id=f'rtest-visit-{i}',patient_id='rtest-patient',practitioner_id=DOCTOR_ID,day=date(2026,11,1)+timedelta(days=i),start_time=time(9),duration=20,visit_type='First visit',reason=f'Fictional visit {i}',status='completed' if i<2 else 'confirmed'))
                session.add(Practice(id='other-practice',name='Other practice',timezone='Asia/Kolkata'))
                session.flush()
                session.add(Practitioner(tenant_id='other-practice',id=DOCTOR_ID,name='Other doctor'))
                session.add(Patient(tenant_id='other-practice',id='patient-a1',patient_number='OTHER-1',name='Hidden Other Patient',demo_age=50,initials='HO',color='rose'))
                session.add(Patient(tenant_id='other-practice',id='outside-only',patient_number='OTHER-2',name='Outside Only',demo_age=50,initials='OO',color='rose'))
                session.flush()
                session.add(AppointmentRecord(tenant_id='other-practice',id='rtest-other-visit',patient_id='patient-a1',practitioner_id=DOCTOR_ID,day=date(2026,11,1),start_time=time(9),duration=20,visit_type='First visit',reason='Should not leak',status='completed'))

    def test_directory_search_filters_and_pagination(self):
        with TestClient(app, role='nurse') as client:
            result=client.get('/api/records/patients').json()
            self.assertEqual((result['total'],result['registered_count'],result['sample_count']),(7,1,6))
            first=client.get('/api/records/patients?limit=2').json()
            second=client.get('/api/records/patients?limit=2&offset=2').json()
            self.assertFalse(set(p['id'] for p in first['patients']) & set(p['id'] for p in second['patients']))
            for query in ['record patient','PT-RECORD','9876500099']:
                found=client.get('/api/records/patients',params={'q':query}).json()
                self.assertEqual(found['total'],1)
                self.assertEqual(found['patients'][0]['id'],'rtest-patient')
                self.assertEqual(found['patients'][0]['appointment_count'],12)
            self.assertEqual(client.get('/api/records/patients?source=registered').json()['total'],1)
            self.assertEqual(client.get('/api/records/patients?source=sample').json()['total'],6)
            self.assertEqual(client.get('/api/records/patients?q=Hidden').json()['total'],0)
            self.assertEqual(client.get('/api/records/patients',params={'q':'%'}).json()['total'],0)
            self.assertEqual(client.get('/api/records/patients?limit=51').status_code,422)
            self.assertEqual(client.get('/api/records/patients?offset=-1').status_code,422)
            self.assertEqual(client.get('/api/records/patients?source=unknown').status_code,422)

    def test_detail_history_and_tenant_boundaries(self):
        with TestClient(app, role='nurse') as client:
            result=client.get('/api/records/patients/rtest-patient').json()
            self.assertEqual(result['patient']['email'],'optional@example.com')
            self.assertEqual(result['patient']['source'],'registered')
            self.assertEqual(result['registration_recorded_on'],'2026-10-19')
            self.assertEqual((result['appointment_count'],result['completed_count']),(12,2))
            self.assertEqual(len(result['appointments']),10)
            self.assertEqual(result['appointments'][0]['day'],'2026-11-12')
            older=client.get('/api/records/patients/rtest-patient?history_offset=10').json()
            self.assertEqual(len(older['appointments']),2)
            self.assertFalse(set(a['id'] for a in result['appointments']) & set(a['id'] for a in older['appointments']))
            sample=client.get('/api/records/patients/patient-a1').json()
            self.assertEqual(sample['patient']['name'],'Anjali Menon')
            self.assertIsNone(sample['patient']['date_of_birth'])
            self.assertIsNone(sample['registration_recorded_on'])
            self.assertEqual(sample['appointment_count'],1)
            self.assertNotIn('Should not leak',str(sample))
            self.assertEqual(client.get('/api/records/patients/outside-only').status_code,404)
            self.assertEqual(client.get('/api/records/patients/not-a-patient').status_code,404)
