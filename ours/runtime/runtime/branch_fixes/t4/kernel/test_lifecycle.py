import copy
import gzip
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
sys.path[:0]=[str(B),str(B/'freeze/authority_src')]
from repair6.completion import CompletionGate
from t09_lifecycle import install_completion,install_hold

class NativeCompletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path('/mnt/disk_4/geyi/t4_T09_diagnostic_20261104/baseline_v1/cases/T4E10_T09_I00')
        import json
        result=json.loads((p/'result.json').read_text())
        with gzip.open(p/'tasks'/result['accepted_task_id']/'trace.json.gz','rt')as f:trace=json.load(f)
        cls.record=next(r for r in reversed(trace['measurements']) if r['adjusted_goal'] is True)
        from benchmark_metrics.config import load_rules
        cls.rules=load_rules()
    def gate(self,fixed=True):
        class Local(CompletionGate):pass
        if fixed:install_completion(SimpleNamespace(CompletionGate=Local))
        return Local(('e','task',2),self.rules)
    def step(self,g,row,subject=('e','task',2)):
        return g.observe(row,subject,9,full_contract=True)
    def test_actual_recording_reproduces_old_adjusted_only_acceptance(self):
        self.assertFalse(self.record['goal_frame']['goal']);self.assertTrue(self.record['adjusted_goal'])
        g=self.gate(False)
        self.assertTrue(any(self.step(g,copy.deepcopy(self.record))for _ in range(55)))
    def test_same_actual_recording_cannot_finish_native_protocol(self):
        g=self.gate();self.assertFalse(any(self.step(g,copy.deepcopy(self.record))for _ in range(55)))
        self.assertFalse(g.holding)
    def test_current_native_and_original_physical_windows_can_finish(self):
        g=self.gate();row=copy.deepcopy(self.record);row['goal_frame']['goal']=True
        self.assertTrue(any(self.step(g,row)for _ in range(55)))
    def test_unknown_native_cannot_finish(self):
        g=self.gate();row=copy.deepcopy(self.record);row['goal_frame'].pop('goal')
        self.assertFalse(any(self.step(g,row)for _ in range(55)))
    def test_native_loss_clears_hold(self):
        g=self.gate();row=copy.deepcopy(self.record);row['goal_frame']['goal']=True
        for _ in range(15):self.step(g,row)
        self.assertTrue(g.holding);row['goal_frame']['goal']=False
        self.assertFalse(self.step(g,row));self.assertFalse(g.holding);self.assertEqual(g.hold_seen,0)
    def test_current_native_does_not_bypass_release(self):
        g=self.gate();row=copy.deepcopy(self.record);row['goal_frame']['goal']=True;row['target']['target_contact']=True
        self.assertFalse(any(self.step(g,row)for _ in range(55)))
    def test_wrong_task_not_accepted(self):
        g=self.gate();row=copy.deepcopy(self.record);row['goal_frame']['goal']=True
        self.assertFalse(any(self.step(g,row,('e','other',2))for _ in range(55)))
    def test_raw_evidence_not_rewritten(self):
        g=self.gate();row=copy.deepcopy(self.record);saved=copy.deepcopy(row)
        self.step(g,row);self.assertEqual(row,saved)

class PausedHold(unittest.TestCase):
    def bridge(self):
        class Bridge:
            def __init__(self):self.state=SimpleNamespace(mode='running');self.physics_steps=20;self.log_records=[];self.applied=[]
            def log(self,*a,**kw):self.log_records.append((a,kw))
            def apply(self,action,phase):
                if self.state.mode=='paused':raise AssertionError('Hard pause cannot env.step')
                self.physics_steps+=1;self.applied.append((action,phase));return 'applied'
        install_hold(Bridge);return Bridge()
    def test_pause_race_drops_hold_and_keeps_process_alive(self):
        b=self.bridge();was_running=b.state.mode=='running';self.assertTrue(was_running)
        b.state.mode='paused';self.assertIsNone(b.apply([0.]*7,'async_wait_hold'))
        self.assertEqual(b.physics_steps,20);self.assertEqual(b.applied,[])
        self.assertFalse(b.log_records[-1][1]['action_applied'])
    def test_actual_cached_logger_can_record_pause_race(self):
        import json,tempfile,threading
        from repair6.cached_logging import install as install_cached_logger
        b=self.bridge();b.state.mode='paused'
        with tempfile.TemporaryDirectory(dir='/mnt/disk_4/geyi/t4_T01_latency_regrasp_20261104')as d:
            b.root=Path(d);b.log_lock=threading.RLock();b.audit=SimpleNamespace(last={'step':20,'policy_actions':0,'simulation_time':1.,'sample':40})
            install_cached_logger(b);self.assertIsNone(b.apply([0.]*7,'async_wait_hold'))
            record=json.loads((b.root/'gateway.jsonl').read_text());self.assertEqual(record['physics_step'],20)
            self.assertEqual(record['dropped_at_physics_step'],20);self.assertFalse(record['action_applied'])
            self.assertEqual(b.physics_steps,20);self.assertFalse(b.applied)
    def test_direct_policy_in_pause_still_raises(self):
        b=self.bridge();b.state.mode='paused'
        with self.assertRaises(AssertionError):b.apply([0.]*7,'authorized_kernel_control')
    def test_resume_real_action_applies_once(self):
        b=self.bridge();b.state.mode='paused';b.apply([0.]*7,'async_wait_hold');b.state.mode='running'
        self.assertEqual(b.apply([0.]*7,'authorized_kernel_control'),'applied');self.assertEqual(b.physics_steps,21)
    def test_completed_hold_for_independent_terminal_check_still_runs(self):
        b=self.bridge();b.state.mode='completed';b.apply([0.]*7,'async_wait_hold');self.assertEqual(b.physics_steps,21)
    def test_install_idempotent(self):
        b=self.bridge();old=b.__class__.apply;install_hold(b.__class__);self.assertIs(b.__class__.apply,old)

if __name__=='__main__':unittest.main(verbosity=2)
