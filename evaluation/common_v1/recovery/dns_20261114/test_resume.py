"""Safety checks for resuming a fixed cohort; no network or robot operations."""
import hashlib
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('resume_checked', Path(__file__).with_name('resume.py'))
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class ContinuationSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.q = Path(self.tmp.name)
        self.r = self.q / 'recovery/incident'
        self.run = self.q / 'runs/formal1770_v1'
        for p in [self.r, self.run / 'outcomes', self.run / 'cases', self.q / 'scale', self.q / 'plans']:
            p.mkdir(parents=True, exist_ok=True)
        MODULE.Q, MODULE.R, MODULE.RUN = self.q, self.r, self.run
        MODULE.frozen = types.SimpleNamespace(verify=lambda: None, defect=lambda x: x.get('engine_error', False))
        errors = ['B1:T2:T2COL1_NS_G01:R02', 'B1:T2:T2COL1_NS_G01:R03',
                  'B1:T1:T1COL1_CL_G05_I02:R03', 'B1:T8:T8EN4_CL_N06_I02:R02']
        self.bad_uid = errors[0]
        rows = [dict(trial_uid=errors[i] if i < 4 else 'uid%d' % i, method='B1') for i in range(1770)]
        self.save(self.run / 'REGISTERED.json', rows)
        self.save(self.q / 'plans/FROZEN.json', dict(version='unchanged'))
        manifest = {}
        for i, row in enumerate(rows[:256]):
            value = dict(row, engine_error=i < 4,
                         final_status=dict(last_error='cloud01 HTTP 500' if i < 4 else None))
            f = self.run / 'outcomes' / (row['trial_uid'] + '.json')
            self.save(f, value)
            manifest[f.name] = MODULE.digest(f)
            (self.run / 'cases' / row['trial_uid']).mkdir()
        self.save(self.r / 'RETAINED256_SHA.json', manifest)
        self.save(self.r / 'API_HEALTH.json', dict(passed=True))
        self.save(self.r / 'INCIDENT_AUDIT.json', dict(
            known_infrastructure_trials=errors,
            registered_sha256=MODULE.digest(self.run / 'REGISTERED.json'),
            source_freeze_sha256=MODULE.digest(self.q / 'plans/FROZEN.json')))
        self.save(self.q / 'scale/GPU_MAP7.json', dict(lanes=7))
        self.save(self.q / 'scale/AMENDMENT.json', dict(
            scale_scripts_sha256={}, gpu_map_sha256=MODULE.digest(self.q / 'scale/GPU_MAP7.json')))

    def tearDown(self):
        self.tmp.cleanup()

    def save(self, p, value):
        p.write_text(json.dumps(value))

    def test_preserves_256_and_only_selects_unstarted_1514(self):
        _, retained, uids, known, _, remaining, _ = MODULE.validate()
        self.assertEqual(len(retained), 256)
        self.assertEqual(len(remaining), 1514)
        self.assertFalse(uids & {x['trial_uid'] for x in remaining})
        self.assertEqual(known[0]['trial_uid'], self.bad_uid)

    def test_rejects_overwritten_first_outcome(self):
        (self.run / 'outcomes' / (self.bad_uid + '.json')).write_text('{}')
        with self.assertRaises(AssertionError):
            MODULE.validate()

    def test_rejects_partial_started_case(self):
        (self.run / 'cases/uid256').mkdir()
        with self.assertRaises(AssertionError):
            MODULE.validate()

    def test_rejects_changed_registration(self):
        self.save(self.run / 'REGISTERED.json', [])
        with self.assertRaises(AssertionError):
            MODULE.validate()

    def test_requires_healthy_cloud_before_dispatch(self):
        self.save(self.r / 'API_HEALTH.json', dict(passed=False))
        with self.assertRaises(AssertionError):
            MODULE.validate()

    def test_rejects_changed_gpu_map(self):
        self.save(self.q / 'scale/GPU_MAP7.json', dict(lanes=8))
        with self.assertRaises(AssertionError):
            MODULE.validate()

    def test_rejects_an_unreviewed_error_despite_a_matching_manifest(self):
        p = self.run / 'outcomes' / (self.bad_uid + '.json')
        value = json.loads(p.read_text())
        value['final_status']['last_error'] = 'Different engine failure'
        self.save(p, value)
        m = self.r / 'RETAINED256_SHA.json'
        manifest = json.loads(m.read_text())
        manifest[p.name] = MODULE.digest(p)
        self.save(m, manifest)
        with self.assertRaises(AssertionError):
            MODULE.validate()

if __name__ == '__main__':
    unittest.main(verbosity=2)
