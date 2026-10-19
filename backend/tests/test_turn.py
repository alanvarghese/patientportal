import io
import json
import os
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from backend.turn import _cache, cloudflare_servers


class TurnTests(unittest.TestCase):
    def setUp(self):
        _cache.clear()
        self.environment = patch.dict(os.environ, {'CLOUDFLARE_TURN_KEY_ID': 'test-key', 'CLOUDFLARE_TURN_API_TOKEN': 'server-secret'})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(_cache.clear)

    @patch('backend.turn.urlopen')
    def test_temporary_credentials_cached_per_role(self, open_url):
        servers = [{'urls': ['turns:turn.cloudflare.com:443?transport=tcp'], 'username': 'temporary-user', 'credential': 'temporary-password'}]
        open_url.side_effect = lambda *args, **kwargs: io.BytesIO(json.dumps({'iceServers': servers}).encode())
        self.assertEqual(cloudflare_servers('room', 'doctor'), servers)
        self.assertEqual(cloudflare_servers('room', 'doctor'), servers)
        self.assertEqual(open_url.call_count, 1)
        cloudflare_servers('room', 'patient')
        self.assertEqual(open_url.call_count, 2)
        request = open_url.call_args.args[0]
        self.assertEqual(json.loads(request.data), {'ttl': 7200})
        self.assertNotIn('server-secret', json.dumps(servers))

    @patch('backend.turn.urlopen')
    def test_errors_do_not_leak_provider_secrets(self, open_url):
        open_url.side_effect = RuntimeError('server-secret')
        with self.assertRaises(HTTPException) as raised:
            cloudflare_servers('room', 'doctor')
        self.assertEqual(raised.exception.status_code, 503)
        self.assertNotIn('server-secret', raised.exception.detail)
        open_url.side_effect = lambda *args, **kwargs: io.BytesIO(b'{"iceServers": []}')
        with self.assertRaises(HTTPException):
            cloudflare_servers('room', 'doctor')

    @patch('backend.turn.urlopen')
    def test_unconfigured_and_partial_configuration(self, open_url):
        with patch.dict(os.environ, {'CLOUDFLARE_TURN_KEY_ID': '', 'CLOUDFLARE_TURN_API_TOKEN': ''}):
            self.assertIsNone(cloudflare_servers('room', 'doctor'))
        with patch.dict(os.environ, {'CLOUDFLARE_TURN_API_TOKEN': ''}):
            with self.assertRaises(HTTPException):
                cloudflare_servers('room', 'doctor')
        open_url.assert_not_called()
