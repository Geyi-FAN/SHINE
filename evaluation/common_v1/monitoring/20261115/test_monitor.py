import unittest
import tempfile
import json
import time
import types
import socket
from unittest.mock import patch
from pathlib import Path
import watchdog
from eta import forecast, remaining_minutes
from watchdog import decision, clean, update_ledger, command_matches

class MonitorTests(unittest.TestCase):
    def test_four_primary_lanes_help_raw_asr_only_after_agent_finishes(self):
        self.assertAlmostEqual(remaining_minutes(60, 20, 3, 4), 5 + 45 / 7)

    def test_raw_asr_finished_does_not_create_extra_speech_accounts(self):
        self.assertEqual(remaining_minutes(0, 40, 0, 4), 10)

    def test_agent_finished_does_not_boost_the_already_observed_seven_lane_rate(self):
        self.assertEqual(remaining_minutes(60, 0, 6, 0), 10)

    def test_missing_recent_method_sample_cannot_make_up_an_eta(self):
        self.assertIsNone(remaining_minutes(10, 10, 3, 0))

    def test_failures_are_included_in_actual_throughput(self):
        registered = [dict(method=m) for m in ['B0']*10 + ['B1']*10]
        observed = [(1900+i, dict(method=m, engine_error=True)) for i,m in enumerate(['B0']*3+['B1']*3)]
        x = forecast(registered, observed, 2000, 1000, 'running_auto_network_admission')
        self.assertEqual(x['observed'], 6)
        self.assertEqual(x['done_by_method'], dict(B0=3, B1=3))
        self.assertEqual(x['state'], 'estimated')

    def test_stopped_cohort_does_not_publish_a_committed_finish_time(self):
        x = forecast([dict(method='B1')], [], 2000, 1000, 'stopped')
        self.assertEqual(x['state'], 'blocked_no_committed_finish_time')
        self.assertNotIn('collection_finish_earliest', x)

    def test_known_network_stop_can_resume_only_when_no_process_or_partial_trial(self):
        self.assertEqual(decision(False, False, False, False, False, False,
                         'Independent network health did not recover', False), 'resume_verified_unstarted_only')

    def test_partial_trial_is_never_replayed_by_watchdog(self):
        self.assertEqual(decision(False, False, False, False, True, False,
                         'Independent network health did not recover', False), 'manual_partial_trial')

    def test_user_stop_always_takes_precedence(self):
        self.assertEqual(decision(True, True, False, False, False, False, '', False), 'user_stopped')

    def test_unknown_error_is_not_blindly_patched(self):
        self.assertEqual(decision(False, False, False, False, False, False,
                         'Unclassified defect: no automatic continuation', False), 'manual_unknown_error')

    def test_account_or_model_identity_error_cannot_trigger_restart_loop(self):
        self.assertEqual(decision(False, False, False, False, False, False,
                         'Independent network health did not recover', True), 'manual_account_or_model_identity')

    def test_existing_dispatcher_prevents_a_duplicate_launch(self):
        self.assertEqual(decision(False, False, True, False, False, False, '', False), 'observe')

    def test_only_owned_service_cleanup_when_no_case_is_in_flight(self):
        self.assertEqual(decision(False, False, False, False, False, True, '', False), 'stop_owned_orphan_services')

    def test_credential_shaped_strings_are_redacted_from_diagnostics(self):
        self.assertEqual(clean('Authorization Bearer fake-example-secret'), 'Authorization [REDACTED]')

    def test_a_published_first_result_cannot_be_replaced_at_operational_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'failed_first_trial.json'
            p.write_text('{"success":false}')
            ledger = update_ledger([p], {})
            p.write_text('{"success":true}')
            with self.assertRaises(AssertionError):
                update_ledger([p], ledger)

    def test_process_matching_resolves_the_deployment_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'real/coordinator.py'
            p.parent.mkdir()
            p.write_text('# real source')
            alias = Path(tmp) / 'alias'
            alias.symlink_to(p.parent, target_is_directory=True)
            self.assertTrue(command_matches(['/usr/bin/python3', str(alias/'coordinator.py')], p))
            self.assertFalse(command_matches(['/usr/bin/python3', '-c', 'print("'+str(p)+'")'], p))

    def test_operational_bootstrap_waits_for_an_occupied_model_port(self):
        with socket.socket() as server:
            server.bind(('127.0.0.1',0))
            server.listen()
            port=server.getsockname()[1]
            self.assertEqual(watchdog.blocked_startup_ports([port]),[port])
        self.assertEqual(watchdog.blocked_startup_ports([port]),[])

    def test_operational_restart_copies_verified_source_without_replaying_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            q = Path(tmp)
            m, template, run = q/'monitoring/test', q/'recovery/template', q/'runs/formal1770_v1'
            for p in [m, template, q/'plans', run/'outcomes', run/'cases']:
                p.mkdir(parents=True, exist_ok=True)
            def save(p, value):
                p.write_text(json.dumps(value))
            save(q/'plans/FROZEN.json', dict(actors='unchanged'))
            save(run/'REGISTERED.json', [dict(trial_uid='trial%04d' % i) for i in range(1770)])
            observed = []
            for i in range(2):
                value = dict(trial_uid='trial%04d' % i, engine_error=i==0)
                p = run/'outcomes'/(value['trial_uid']+'.json')
                save(p, value)
                (run/'cases'/value['trial_uid']).mkdir()
                observed.append((time.time(), value))
            original = {p.name: watchdog.sha(p) for p in (run/'outcomes').iterdir()}
            save(template/'RETAINED_SHA.json', original)
            save(m/'FIRST_SEEN_SHA.json', original)
            save(template/'DNS_PATCH.json', dict(host_changed=False))
            (template/'services.py').write_text('# unchanged service implementation')
            (template/'coordinator.py').write_text('''from types import SimpleNamespace
frozen=SimpleNamespace(verify=lambda:None,defect=lambda x:x['engine_error'])
def todo(registered,completed,started):
 assert completed==started
 return [x for x in registered if x['trial_uid']not in completed]
def fault_kind(value,case):return 'upstream_http_error'
def network_check():return {'passed':True,'fatal':False}
''')
            cfg=dict(template=str(template), template_sources={p.name:watchdog.sha(p) for p in template.glob('*.py')},
                frozen_sha256=watchdog.sha(q/'plans/FROZEN.json'), registered_sha256=watchdog.sha(run/'REGISTERED.json'),
                initial_manifest_sha256=watchdog.sha(template/'RETAINED_SHA.json'), dns_patch_sha256=watchdog.sha(template/'DNS_PATCH.json'))
            control=dict(active_deployment=str(template), relaunches=[])
            with patch.multiple(watchdog, M=m, Q=q, RUN=run), \
                 patch.object(watchdog,'lock_busy',return_value=False), \
                 patch.object(watchdog,'pids',return_value=[]), \
                 patch.object(watchdog,'blocked_startup_ports',return_value=[]), \
                 patch.object(watchdog.subprocess,'Popen',return_value=types.SimpleNamespace(pid=12345)) as launch:
                view={}
                watchdog.relaunch(cfg,control,template,observed,view)
                self.assertEqual(launch.call_count,1)
                self.assertEqual(view['action'],'restarted_verified_coordinator')
                dst=Path(control['active_deployment'])
                self.assertEqual(json.loads((dst/'APPROVED.json').read_text())['completed'],2)
                self.assertEqual(json.loads((dst/'RETAINED_SHA.json').read_text()),original)
                self.assertEqual({p.name:watchdog.sha(p) for p in(run/'outcomes').iterdir()},original)
                self.assertEqual(len(list((run/'cases').iterdir())),2)
                self.assertEqual(watchdog.sha(dst/'coordinator.py'),cfg['template_sources']['coordinator.py'])
                control['relaunches'] += [dict(at=time.time()),dict(at=time.time())]
                with self.assertRaises(AssertionError):
                    watchdog.relaunch(cfg,control,template,observed,{})
                self.assertEqual(launch.call_count,1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
