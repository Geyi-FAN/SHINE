"""Account switches must include all cloud roles and use a distinct lease."""

import json
import tempfile
import unittest
from pathlib import Path

from voice_account import VoiceAccount


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.key = self.root / "account_b.key"
        self.key.write_text("unit-test-fake-key")
        self.key.chmod(0o600)
        self.config = dict(
            schema="t7_voice_account_v1",
            label="account-b",
            credential_file=str(self.key),
            lease_file=str(self.root / "account_b.lock"),
            independence="user_reported_independent_account",
            model="qwen3.8-omni-flash-realtime",
            voice="Tina",
            max_simultaneous_sessions=1,
        )
        self.path = self.root / "account.json"
        self.path.write_text(json.dumps(self.config))

    def tearDown(self):
        self.temporary.cleanup()

    def test_all_cloud_roles_switch_without_modifying_base_or_model(self):
        account = VoiceAccount.load(self.path)
        base = dict(
            providers={
                role: dict(
                    provider="qwen-realtime",
                    apiKeyFile="/old.key",
                    endpoint="https://dashscope.aliyuncs.com",
                    model="frozen-model",
                )
                for role in ("dialogue", "visual_qa", "speech")
            }
        )
        changed = account.configure_providers(base)
        for role in base["providers"]:
            self.assertEqual(base["providers"][role]["apiKeyFile"], "/old.key")
            self.assertEqual(changed["providers"][role]["apiKeyFile"], str(self.key))
            self.assertEqual(changed["providers"][role]["model"], "frozen-model")
        self.assertNotIn("unit-test-fake-key", json.dumps(account.public_metadata()))
        self.assertEqual(account.lease_file.stat().st_mode & 0o777, 0o600)

    def test_missing_publicly_readable_or_empty_key_is_rejected(self):
        for condition in ("missing", "public", "empty"):
            with self.subTest(condition=condition):
                if condition == "missing":
                    self.key.unlink()
                else:
                    self.key.write_text(
                        "" if condition == "empty" else "unit-test-fake-key"
                    )
                    self.key.chmod(0o644 if condition == "public" else 0o600)
                with self.assertRaises(
                    (FileNotFoundError, PermissionError, ValueError)
                ):
                    VoiceAccount.load(self.path)

    def test_concurrency_model_or_voice_cannot_change_implicitly(self):
        for field, value in (
            ("max_simultaneous_sessions", 2),
            ("model", "other-model"),
            ("voice", "other-voice"),
        ):
            with self.subTest(field=field):
                self.path.write_text(json.dumps(dict(self.config, **{field: value})))
                with self.assertRaises(ValueError):
                    VoiceAccount.load(self.path)


if __name__ == "__main__":
    unittest.main()
