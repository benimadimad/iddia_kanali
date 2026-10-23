"""Regression tests for Vercel FIREBASE_SERVICE_ACCOUNT configuration.

No real Google credential or private key is stored in this test module.
"""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from league.firestore_repository import _load_service_account


class FirebaseCredentialConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.example = {
            'type': 'service_account',
            'project_id': 'dummy-project',
            'client_email': 'dummy@example.invalid',
            'private_key': 'FAKE-TEST-KEY-' * 300,
        }

    def test_raw_json(self):
        result = _load_service_account(json.dumps(self.example))
        self.assertEqual(result, self.example)

    def test_base64_long_value_is_decoded_not_opened_as_filename(self):
        raw = json.dumps(self.example).encode('utf-8')
        value = base64.b64encode(raw).decode('ascii')
        self.assertGreater(len(value), 255)
        result = _load_service_account(value)
        self.assertEqual(result, self.example)

    def test_existing_file_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'credentials.json'
            path.write_text(json.dumps(self.example), encoding='utf-8')
            self.assertEqual(_load_service_account(str(path)), self.example)

    def test_invalid_value_returns_generic_error_without_echoing_input(self):
        secret = 'not a valid encoded credential ' * 200
        with self.assertRaises(RuntimeError) as raised:
            _load_service_account(secret)
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn('FIREBASE_SERVICE_ACCOUNT', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
