"""Offline tests: route selection, exact forwarding, and capacity protection."""
import importlib.util
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
import urllib.request
from unittest.mock import patch

import t02_transport
from planning_pool import original, backend_specs


class Routing(unittest.TestCase):
    def module(self, config=None):
        base = config or dict(model='Qwen3.8-27B-FP8', chat_url='http://127.0.0.1:18084/v1/chat/completions')
        return types.SimpleNamespace(connection=lambda role: (base, 'test-private-key'))

    def test_planning_endpoint_only(self):
        module = self.module(); t02_transport.install(module)
        config, key = module.connection('planning')
        self.assertEqual(config['chat_url'], t02_transport.ENDPOINT)
        self.assertEqual(key, 'test-private-key')
        self.assertEqual(config['model'], 'Qwen3.8-27B-FP8')

    def test_wording_unchanged(self):
        module = self.module(); before = module.connection('wording'); t02_transport.install(module)
        self.assertEqual(module.connection('wording'), before)

    def test_idempotent(self):
        module = self.module(); t02_transport.install(module); f = module.connection
        t02_transport.install(module); self.assertIs(module.connection, f)

    def test_unexpected_parent_rejected(self):
        module = self.module(dict(model='Qwen3.8-27B-FP8', chat_url='https://external.invalid/v1/chat/completions'))
        t02_transport.install(module)
        with self.assertRaises(ValueError): module.connection('planning')

    def test_changed_model_rejected(self):
        module = self.module(dict(model='different', chat_url='http://127.0.0.1:18084/v1/chat/completions'))
        t02_transport.install(module)
        with self.assertRaises(ValueError): module.connection('planning')

    def test_invalid_branch_endpoint_rejected(self):
        module = self.module(); t02_transport.install(module)
        with patch.object(t02_transport, 'ENDPOINT', 'https://external.invalid/v1/chat/completions'):
            with self.assertRaises(ValueError): module.connection('planning')

    def test_backends_are_planning_only(self):
        backends = backend_specs('test-key')
        self.assertEqual([b['id'] for b in backends], ['fp8-174-0', 'fp8-174-1'])
        self.assertTrue(all(b['roles'] == ['planning'] and b['max_backend_load'] == 2 for b in backends))


class CapacityAndForwarding(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.backends = backend_specs('test-key')
        self.pool = original.Pool(self.backends, 'test-client-key', Path(self.folder.name) / 'requests.jsonl')
        for backend in self.backends:
            backend.update(healthy=True, observed_load=0, checked=time.monotonic())

    def tearDown(self): self.folder.cleanup()

    def test_shared_upstream_load_is_respected(self):
        self.backends[0]['observed_load'] = 2
        backend = self.pool.acquire(0, 'planning')
        self.assertEqual(backend['id'], 'fp8-174-1'); self.pool.release(backend)

    def test_full_capacity_does_not_send_elsewhere(self):
        for backend in self.backends: backend['observed_load'] = 2
        with self.assertRaises(TimeoutError): self.pool.acquire(0, 'planning')
        self.assertTrue(all(b['assigned'] == 0 for b in self.backends))

    def test_other_roles_cannot_use_branch_pool(self):
        for role in ['wording', 'verifier', 'recovery', 'unspecified']:
            with self.assertRaises(TimeoutError): self.pool.acquire(0, role)

    def test_stale_load_evidence_rejected(self):
        for backend in self.backends: backend['checked'] = time.monotonic() - 10
        with self.assertRaises(TimeoutError): self.pool.acquire(0, 'planning')

    def test_http_exact_bytes_once(self):
        received = []
        logged = threading.Event()
        original_record = self.pool.record
        def record(item):
            original_record(item)
            logged.set()
        self.pool.record = record
        answer = b'{"model":"Qwen3.8-27B-FP8","choices":[{"message":{"content":"test"}}]}'
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                received.append(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200); self.send_header('Content-Length', str(len(answer)))
                self.end_headers(); self.wfile.write(answer)
        upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        backend = self.backends[0]; backend['base'] = 'http://127.0.0.1:%d/v1' % upstream.server_port
        self.backends[1]['healthy'] = False
        proxy = ThreadingHTTPServer(('127.0.0.1', 0), original.handler(self.pool))
        threading.Thread(target=proxy.serve_forever, daemon=True).start()
        try:
            payload = b'{ "model": "Qwen3.8-27B-FP8", "messages": [{"role":"user", "content":"test unrelated generic instruction"}], "temperature":0.0 }'
            request = urllib.request.Request('http://127.0.0.1:%d/v1/chat/completions' % proxy.server_port, data=payload,
                headers={'Authorization':'Bearer test-client-key', 'Content-Type':'application/json', 'X-Agent-Role':'planning'})
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5) as response:
                self.assertEqual(response.read(), answer)
                self.assertEqual(response.headers['X-Local-Upstream-Id'], 'fp8-174-0')
            self.assertEqual(received, [payload])
            self.assertTrue(logged.wait(2), 'Wait for the actual post-response audit write')
            records = [json.loads(s) for s in self.pool.log.read_text().splitlines()]
            self.assertEqual(len(records), 1)
            self.assertFalse(records[0]['prompt_rewritten']); self.assertEqual(records[0]['retries'], 0)
        finally:
            proxy.shutdown(); proxy.server_close(); upstream.shutdown(); upstream.server_close()


if __name__ == '__main__': unittest.main(verbosity=2)
