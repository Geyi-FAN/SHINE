"""Only the explicitly configured private loopback port is added to the guard."""

import os
import sys
import types
import unittest
import urllib.request
from unittest.mock import Mock, patch

from private_transport import install


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.local = types.ModuleType("local_transport")
        self.text = types.ModuleType("text_transport")
        for module in (self.local, self.text):
            setattr(
                module,
                "connection",
                lambda role: (
                    {
                        "chat_url": "http://127.0.0.1:18084/v1/chat/completions",
                        "model": "test",
                    },
                    "unit-test-only",
                ),
            )
        self.modules = patch.dict(
            sys.modules, local_transport=self.local, text_transport=self.text
        )
        self.modules.start()
        self.env = patch.dict(
            os.environ, T7_LATENCY_MODEL_URL="http://127.0.0.1:18687/v1"
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.modules.stop()

    def test_role_configuration_preserves_model_and_key(self):
        install()
        for module in (self.local, self.text):
            config, key = module.connection("recovery")
            self.assertEqual(config["model"], "test")
            self.assertEqual(key, "unit-test-only")
            self.assertEqual(
                config["chat_url"], "http://127.0.0.1:18687/v1/chat/completions"
            )

    def test_other_hosts_ports_and_credential_urls_are_rejected(self):
        for url in (
            "http://example.com:18687/v1",
            "http://127.0.0.1:18083/v1",
            "https://127.0.0.1:18687/v1",
            "http://x:y@127.0.0.1:18687/v1",
            "http://127.0.0.1:18687/v1?route=other",
        ):
            with (
                self.subTest(url=url),
                patch.dict(os.environ, T7_LATENCY_MODEL_URL=url),
            ):
                with self.assertRaises(ValueError):
                    install()

    def test_network_guard_forbids_cloud_and_unlisted_loopback(self):
        forwarded = Mock(return_value="fake-response")
        with patch.object(urllib.request.OpenerDirector, "open", forwarded):
            install()
            self.text.install_network_guard()
            opener = urllib.request.OpenerDirector()
            result = opener.open("http://127.0.0.1:18687/v1/chat/completions")
            self.assertEqual(result, "fake-response")
            for url in ("https://example.com/v1", "http://127.0.0.1:18688/v1"):
                with self.assertRaises(RuntimeError):
                    opener.open(url)
            self.assertEqual(forwarded.call_count, 1)


if __name__ == "__main__":
    unittest.main()
