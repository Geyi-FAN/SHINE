from types import SimpleNamespace
from unittest.mock import patch
import unittest
import t06_recovery_transport as transport


class RecoveryAffinity(unittest.TestCase):
    def module(self):
        return SimpleNamespace(connection=lambda role: (dict(model='Qwen3.8-27B-FP8',chat_url='http://127.0.0.1:18084/v1/chat/completions'), 'test-key'))

    def test_recovery_changes_only_endpoint(self):
        m=self.module();transport.install(m);config,key=m.connection('recovery')
        self.assertEqual(config['chat_url'],transport.ENDPOINT)
        self.assertEqual(config['model'],'Qwen3.8-27B-FP8');self.assertEqual(key,'test-key')

    def test_verifier_unchanged(self):
        m=self.module();old=m.connection('verifier');transport.install(m)
        self.assertEqual(m.connection('verifier'),old)

    def test_install_idempotent(self):
        m=self.module();transport.install(m);old=m.connection;transport.install(m)
        self.assertIs(m.connection,old)

    def test_unexpected_model_rejected(self):
        m=SimpleNamespace(connection=lambda role:(dict(model='different',chat_url='http://127.0.0.1:18084/v1/chat/completions'),'k'))
        transport.install(m)
        with self.assertRaises(ValueError):m.connection('recovery')

    def test_unexpected_parent_rejected(self):
        m=SimpleNamespace(connection=lambda role:(dict(model='Qwen3.8-27B-FP8',chat_url='https://external.invalid'),'k'))
        transport.install(m)
        with self.assertRaises(ValueError):m.connection('recovery')

    def test_unexpected_branch_rejected(self):
        m=self.module();transport.install(m)
        with patch.object(transport,'ENDPOINT','https://external.invalid'):
            with self.assertRaises(ValueError):m.connection('recovery')


if __name__=='__main__':unittest.main(verbosity=2)
