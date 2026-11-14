"""Test failure-preserving dispatch and conservative network admission."""
import importlib.util
import json
import socket
import tempfile
import types
import unittest
from unittest.mock import patch
from pathlib import Path

spec = importlib.util.spec_from_file_location('admission_checked', Path(__file__).with_name('coordinator.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.case = Path(self.tmp.name)
        self.value = dict(branch='T2', scoring_returncode=0, audio_quality_passed=True,
                          final_status=dict(last_error=None))

    def tearDown(self):
        self.tmp.cleanup()

    def kind(self, text):
        self.value['final_status']['last_error'] = text
        return module.fault_kind(self.value, self.case)

    def test_neither_success_nor_failure_is_replayed(self):
        registered = [dict(trial_uid=x) for x in ['success', 'failure', 'new']]
        result = module.todo(registered, {'success', 'failure'}, {'success', 'failure'})
        self.assertEqual(result, [dict(trial_uid='new')])

    def test_partial_started_trial_blocks_continuation(self):
        with self.assertRaises(AssertionError):
            module.todo([dict(trial_uid='pending')], set(), {'pending'})

    def test_duplicate_registration_is_rejected(self):
        with self.assertRaises(AssertionError):
            module.todo([dict(trial_uid='x'), dict(trial_uid='x')], set(), set())

    def test_upstream500_eligible_for_health_check_not_replay(self):
        self.assertEqual(self.kind('cloud01 HTTP 500'), 'upstream_http_error')

    def test_dns_eligible_for_health_check(self):
        self.assertEqual(self.kind('Temporary failure in name resolution'), 'dns_failure')

    def test_observed_read_timeout_is_recognized(self):
        self.assertEqual(self.kind('The read operation timed out'), 'upstream_timeout')

    def test_generic_timeout_is_not_automatically_waived(self):
        self.assertIsNone(self.kind('TimeoutError in an unknown robot component'))

    def test_account_denial_stops_instead_of_looping(self):
        self.assertIsNone(self.kind('1007 Access denied'))
        self.assertIsNone(self.kind('cloud01 HTTP 403'))

    def test_scoring_failure_stops_even_when_network_also_failed(self):
        self.value['scoring_returncode'] = 1
        self.assertIsNone(self.kind('cloud01 HTTP 500'))

    def test_qa_reference_alignment_failure_is_not_a_network_fault(self):
        self.value.update(branch='T6', audit=dict(frame_offsets_passed=False))
        self.assertIsNone(self.kind('The read operation timed out'))

    def test_t5_pending_request_requires_the_observed_evidence(self):
        self.value.update(branch='T5', audio_played=True,
                          client_errors=['dialogue:timeout:actual_useful_question'])
        self.value['final_status']['agent_execution'] = dict(phase='planning')
        p = self.case / 'agent_calls/request1'
        p.mkdir(parents=True)
        (p / 'request.json').write_text('{}')
        self.assertEqual(module.fault_kind(self.value, self.case), 'unfinished_planning_at_client_timeout')
        (self.case / 'ENGINE_FINISHED.json').write_text('{}')
        self.assertIsNone(module.fault_kind(self.value, self.case))

    def test_other_engine_errors_require_review(self):
        self.assertIsNone(self.kind('IndexError: missing state entry'))

    def test_closed_connection_does_not_look_like_a_live_gateway(self):
        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', 0))
        port = server.getsockname()[1]
        server.listen()
        client = socket.create_connection(('127.0.0.1', port))
        accepted, _ = server.accept()
        accepted.shutdown(socket.SHUT_WR)
        self.assertEqual(client.recv(1), b'')
        client.close()
        accepted.close()
        server.close()
        # A bare bind reproduces the previous false positive in TIME_WAIT.
        with socket.socket() as bare:
            with self.assertRaises(OSError):
                bare.bind(('127.0.0.1', port))
        module.ensure_ports_reusable([port], timeout=.1)

    def test_live_listener_is_still_rejected(self):
        with socket.socket() as server:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', 0))
            server.listen()
            with self.assertRaises(OSError):
                module.ensure_ports_reusable([server.getsockname()[1]], timeout=0)

    def test_full_cohort_continues_after_a_timeout_without_replaying_the_failure(self):
        q = self.case / 'deployment'
        r = q / 'recovery/admission'
        run = q / 'runs/formal1770_v1'
        for p in [r, q / 'plans', q / 'scale', run / 'cases', run / 'outcomes', run / 'items', run / 'scale_logs']:
            p.mkdir(parents=True, exist_ok=True)
        def save(p, v):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(v))
        registered = [dict(trial_uid='trial%04d' % i, method='B1' if i % 2 else 'B0',
                           branch='T2', public_case_id=str(i)) for i in range(1770)]
        save(run / 'REGISTERED.json', registered)
        save(q / 'plans/FROZEN.json', dict(unchanged=True))
        save(q / 'scale/GPU_MAP7.json', dict(lanes=7))
        (q / 'scale/one_case_scaled.py').write_text('# Unchanged model runner')
        save(q / 'scale/AMENDMENT.json', dict(
            scale_scripts_sha256={'one_case_scaled.py': module.sha(q / 'scale/one_case_scaled.py')},
            gpu_map_sha256=module.sha(q / 'scale/GPU_MAP7.json')))
        manifest = {}
        for item in registered[:304]:
            uid = item['trial_uid']
            (run / 'cases' / uid).mkdir()
            p = run / 'outcomes' / (uid + '.json')
            save(p, dict(item, engine_error=False))
            manifest[p.name] = module.sha(p)
        save(r / 'RETAINED304_SHA.json', manifest)
        save(r / 'APPROVED304.json', dict(reviewed_faults=[],
            registered_sha256=module.sha(run / 'REGISTERED.json'),
            source_freeze_sha256=module.sha(q / 'plans/FROZEN.json')))
        save(r / 'DNS_PATCH.json', dict(containers={}))
        calls, health_calls = [], []
        failed_uid = 'trial0305'
        def run_case(argv, **kwargs):
            item = json.loads(Path(argv[argv.index('--item') + 1]).read_text())
            uid = item['trial_uid']
            calls.append(uid)
            (run / 'cases' / uid).mkdir()
            save(run / 'outcomes' / (uid + '.json'), dict(item, engine_error=uid == failed_uid,
                 audio_quality_passed=True, audio_played=True, scoring_returncode=0,
                 final_status=dict(last_error='The read operation timed out' if uid == failed_uid else None)))
            return types.SimpleNamespace(returncode=0)
        def health():
            health_calls.append(len(calls))
            return dict(passed=True, fatal=False)
        def start_service(argv, **kwargs):
            group = argv[-1]
            save(r / (group.upper() + '_READY.json'), dict(ready=True))
            return types.SimpleNamespace(poll=lambda: None, wait=lambda **kwargs: 0)
        def summarize(run, rows, phase):
            return dict(phase=phase, completed=len(list((run / 'outcomes').glob('*.json'))), planned=len(rows), rows=[])
        fake = types.SimpleNamespace(verify=lambda: None, write=save,
                    defect=lambda v: v.get('engine_error', False), summarize=summarize)
        with patch.multiple(module, Q=q, R=r, RUN=run, frozen=fake), \
             patch.object(module, 'network_check', health), \
             patch.object(module.subprocess, 'Popen', start_service), \
             patch.object(module.subprocess, 'run', run_case), \
             patch.object(module.socket, 'socket'), \
             patch.object(module.time, 'sleep'):
            module.main()
        self.assertEqual(len(calls), 1466)
        self.assertEqual(len(set(calls)), 1466)
        self.assertEqual(calls.count(failed_uid), 1)
        self.assertEqual(len(health_calls), 2)
        self.assertGreater(health_calls[1], 0)
        self.assertTrue(json.loads((run / 'outcomes' / (failed_uid + '.json')).read_text())['engine_error'])
        self.assertEqual(json.loads((run / 'COMPLETED.json').read_text())['completed'], 1770)
        self.assertTrue(all(module.sha(run / 'outcomes' / n) == h for n, h in manifest.items()))

if __name__ == '__main__':
    unittest.main(verbosity=2)
