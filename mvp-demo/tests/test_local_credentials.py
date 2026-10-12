import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_credentials import protect_secret, unprotect_secret, CredentialError
from model_gateway import load_config, ModelError, ENDPOINT
from budget_store import MODEL, VERSION


@unittest.skipUnless(os.name == 'nt', 'Windows DPAPI only')
class LocalCredentialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'PaperAudit' / 'DeepSeek' / 'model.json'
        self.path.parent.mkdir(parents=True)
        self.secret = 'SYNTHETIC-SECRET-NOT-A-KEY'
        self.config = {'endpoint': ENDPOINT, 'verified_model_name': 'DeepSeek-V4.1-Flash',
                       'valid_until': time.time() + 300, 'protected_secret': protect_secret(self.secret),
                       'price': {'model': MODEL, 'version': VERSION, 'currency': 'USD',
                                 'unit': 'per_million_tokens', 'input': '0.30', 'output': '1.20',
                                 'reference': 'SYNTHETIC TEST ONLY'}}
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.config), encoding='utf-8')

    def test_encrypted_roundtrip_and_local_discovery(self):
        self.assertNotIn(self.secret, self.path.read_text(encoding='utf-8'))
        self.assertEqual(unprotect_secret(self.config['protected_secret']), self.secret)
        loaded = load_config({'LOCALAPPDATA': self.tmp.name})
        self.assertEqual(loaded['secret'], self.secret)
        self.assertNotIn('protected_secret', loaded)

    def test_explicit_path_and_environment_secret_take_precedence(self):
        self.config.pop('protected_secret'); self.save()
        loaded = load_config({'PAPER_AUDIT_MODEL_CONFIG': str(self.path), 'DEEPSEEK_API_KEY': 'TEST-OVERRIDE'})
        self.assertEqual(loaded['secret'], 'TEST-OVERRIDE')
        with self.assertRaises(ModelError):
            load_config({'PAPER_AUDIT_MODEL_CONFIG': str(self.path) + '.missing', 'LOCALAPPDATA': self.tmp.name})

    def test_corrupt_missing_expired_or_wrong_version_fail_closed(self):
        for change in [{'protected_secret': 'not-base64'}, {'protected_secret': None},
                       {'valid_until': 0}, {'verified_model_name': 'OTHER'}]:
            original = dict(self.config)
            self.config.update(change); self.save()
            with self.assertRaises(ModelError) as caught:
                load_config({'LOCALAPPDATA': self.tmp.name})
            self.assertNotIn(self.secret, str(caught.exception))
            self.config = original
        for bad in ['', 'has space', '\n']:
            with self.assertRaises(CredentialError): protect_secret(bad)


if __name__ == '__main__':
    unittest.main()
