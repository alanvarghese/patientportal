from backend.tests.client import TestClient
from backend.main import app
from backend.encounters import CONSENT_VERSION
from backend.tests.test_database import PostgresTestCase
from backend.video import hub
from unittest.mock import patch

H={'X-Practice-Client':'portal'}
class VideoTests(PostgresTestCase):
    def setUp(self):
        super().setUp()
        provider = patch('backend.video.cloudflare_servers', return_value=None)
        provider.start()
        self.addCleanup(provider.stop)

    def test_managed_turn_requires_valid_invitation(self):
        servers = [{'urls': ['turns:turn.cloudflare.com:443?transport=tcp'], 'username': 'temporary', 'credential': 'temporary'}]
        with TestClient(app, headers=H) as client, patch('backend.video.cloudflare_servers', return_value=servers) as provider:
            self.assertEqual(client.post('/api/video/info', json={'token': 'bad'}).status_code, 401)
            provider.assert_not_called()
            room = client.post('/api/video/appointments/a4/prepare').json()
            result = client.post('/api/video/info', json={'token': room['token']})
            self.assertEqual(result.status_code, 200)
            self.assertTrue(result.json()['turn_configured'])
            self.assertEqual(result.json()['ice_servers'], servers)
            provider.assert_called_once_with(room['room_id'], 'doctor')
            hub.end(room['room_id'])

    def test_two_roles_signaling_and_end(self):
        with TestClient(app,headers=H) as client:
            self.assertEqual(client.post('/api/video/appointments/a1/prepare').status_code,409)
            self.assertEqual(client.post('/api/video/appointments/unknown/prepare').status_code,404)
            room=client.post('/api/video/appointments/a4/prepare').json()
            again=client.post('/api/video/appointments/a4/prepare').json()
            self.assertEqual(room['room_id'],again['room_id'])
            d={'token':room['token'],'connection_id':'d'*32};p={'token':room['guest_token'],'connection_id':'e'*32}
            self.assertEqual(client.post('/api/video/info',json={'token':room['token']+'bad'}).status_code,401)
            self.assertEqual(client.post('/api/video/info',json={'token':room['token']}).json()['role'],'doctor')
            self.assertEqual(client.post('/api/video/connect',json=d).status_code,200)
            self.assertEqual(client.post('/api/video/connect',json={**d,'connection_id':'f'*32}).status_code,409)
            client.post('/api/video/consent',json={'token':room['guest_token'],'accepted':True,'notice_version':CONSENT_VERSION})
            self.assertEqual(client.post('/api/video/connect',json=p).status_code,200)
            self.assertEqual(client.post('/api/video/signal',json={**p,'type':'offer','call_id':'a'*32,'data':{}}).status_code,403)
            self.assertEqual(client.post('/api/video/signal',json={**d,'type':'offer','call_id':'a'*32,'data':{'type':'offer','sdp':'demo'}}).status_code,200)
            messages=client.post('/api/video/poll',json=p).json()['messages']
            self.assertEqual(messages[-1]['data']['sdp'],'demo')
            self.assertEqual(client.post('/api/video/end',json={'token':room['guest_token']}).status_code,403)
            self.assertEqual(client.post('/api/video/leave',json=p).status_code,200)
            self.assertEqual(client.post('/api/video/poll',json=d).json()['messages'][-1]['type'],'peer-left')
            self.assertEqual(client.post('/api/video/end',json={'token':room['token']}).status_code,200)
            self.assertEqual(client.post('/api/video/info',json={'token':room['guest_token']}).status_code,410)
            new=client.post('/api/video/appointments/a4/prepare').json()
            self.assertNotEqual(new['room_id'],room['room_id'])
            hub.end(new['room_id'])
    def test_patient_cannot_join_by_guessing_appointment(self):
        with TestClient(app,headers=H) as client:
            self.assertEqual(client.post('/api/patient/appointments/a4/video').status_code,401)
            self.assertEqual(client.post('/api/video/connect',json={'token':'bad','connection_id':'a'*32}).status_code,401)
