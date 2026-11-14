"""Exercise integration hooks and real image/worker protocol, without a GPU."""
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace, ModuleType
from unittest.mock import patch
import numpy as np

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B/'freeze/f28d/source'))
sys.path.insert(0, str(B/'repair6/reference'))
from t3repair import memory
memory.install()
import points
from scene_memory import SceneMemory


class CropProtocol(unittest.TestCase):
    def observe(self, returned_key='K1', confidence=.8):
        with tempfile.TemporaryDirectory() as d:
            p = points.Points.__new__(points.Points)
            p.folder = Path(d); p.camera_id = 'c'; p.episode_frame_at_takeover = 0
            p.timings = []; p.memory = {}; p.history_camera = {}; p.current = {}; p.frame = None
            p.required_reference = dict(time_source='current', entity='bowl', keypoint='K1')
            old = dict(entity='bowl', keypoint='K1', yx224=[100, 110], frame=0)
            p.last_image_points = {('bowl','K1'):old}
            p.scene = SceneMemory(Path(d)/'events.jsonl', episode_id='e')
            p.scene.evidence(4, {'bowl':dict(static=True, cache_reusable=True, pose=[0,0,0,1,0,0,0])}, 'c')
            found = dict(entity='bowl', keypoint=returned_key, yx224=[101,111], det_confidence=confidence, keypoint_confidence=.9)
            p.proc = SimpleNamespace(stdin=io.StringIO(), stdout=io.StringIO('\n'.join([
                json.dumps(dict(frame=4, points=[], seconds=.01)),
                json.dumps(dict(frame=4, points=[found], seconds=.01))])+'\n'))
            with patch.dict(os.environ, REPAIR_ROI_YOLO='1'):
                p.observe(np.zeros((256,256,3), dtype=np.uint8), 4)
            return p.resolve('current','bowl','K1'), [json.loads(l) for l in p.proc.stdin.getvalue().splitlines()]

    def test_missing_k1_is_reacquired_from_image(self):
        (p,status), requests = self.observe()
        self.assertEqual(status,'fresh');self.assertTrue(p['roi_reacquisition'])
        self.assertEqual(len(requests),2);self.assertEqual(requests[1]['entity'],'bowl')
        self.assertNotIn('pose',requests[1])

    def test_another_k_does_not_fill_missing_k1(self):
        (p,status),_ = self.observe('K3');self.assertIsNone(p);self.assertEqual(status,'missing')

    def test_low_confidence_crop_is_rejected(self):
        (p,status),_ = self.observe(confidence=.09);self.assertIsNone(p)


class HookIntegration(unittest.TestCase):
    def setUp(self):
        from t3repair.integration import install
        self.calls=[]; self.logs=[]
        language=ModuleType('task_language');language.SYSTEM='fixed wording'
        def normalize(agent, raw, observed_context=None):
            self.calls.append(raw)
            return dict(seconds=2., output=dict(execution_task=raw,semantic_changes=[]))
        language.normalize=normalize
        planner=ModuleType('planner');planner.validate=lambda *a,**k:[]
        class Planner:
            def __init__(self):self.model='test';self.system='fixed'
            def generate(self, inp):
                self.last_input=copy.deepcopy(inp)
                return language.normalize(self, inp['user_message'], inp['physical_state'].get('observed_scene_context'))
        planner.Planner=Planner
        native=ModuleType('native_execution');native.CATALOG=[dict(canonical_task='put the bowl on the stove')]
        self.modules=patch.dict(sys.modules,planner=planner,task_language=language,native_execution=native)
        self.modules.start();self.addCleanup(self.modules.stop)
        class Bridge:
            def install_hooks(b):pass
            def start(b,client,resume=False):
                return b.planner.generate(dict(user_message='put the bowl on the stove',physical_state={},frame=10))
            def apply(b,action,phase):return True
        install(Bridge)
        b=Bridge();b.saved_mon=None;b.log=lambda name,**kw:self.logs.append((name,kw));b.state=SimpleNamespace()
        b.subject=('ep','task',1,1);b.token=lambda:b.subject
        b.cache_reader=SimpleNamespace(memory_evidence=lambda:{},joints=[],snapshot={})
        def factory():
            if b.saved_mon is None:
                b.saved_mon=SimpleNamespace(active=None,entered=3,last=10,events=[],select=lambda s:None)
            else:b.saved_mon.active=None
            return b.saved_mon
        b.runner=SimpleNamespace(ObservedCompletion=factory);b.ctx=None
        b.authority=SimpleNamespace(extensions=SimpleNamespace(),published=SimpleNamespace())
        b.install_hooks();self.b=b

    def test_same_task_wording_reused_once(self):
        self.b.start(None);r=self.b.start(None,True)
        self.assertEqual(len(self.calls),1);self.assertTrue(r['reused'])

    def test_exact_authorized_training_sentence_skips_duplicate_wording(self):
        self.b.state=SimpleNamespace(instruction='put the bowl on the stove',normalization='exact_training_template',task_record={})
        r=self.b.start(None)
        self.assertFalse(self.calls);self.assertEqual(r['output']['execution_task'],'put the bowl on the stove')
        self.assertFalse(r['wording_agent_called'])

    def test_side_constraint_cannot_be_silently_skipped(self):
        self.b.state=SimpleNamespace(instruction='put the bowl on the stove',instruction_normalization='exact_training_template',task_record={'persistent_constraints':['keep cheese in place']})
        self.b.start(None);self.assertEqual(len(self.calls),1)

    def test_flag_alone_cannot_authorize_noncanonical_task(self):
        from t3repair.wording import exact_authorized_task
        state=SimpleNamespace(instruction='return the bowl then open the drawer',instruction_normalization='exact_training_template',task_record={})
        self.assertFalse(exact_authorized_task(state,state.instruction,[dict(canonical_task='put the bowl on the stove')]))

    def test_new_semantic_revision_recomputes_wording(self):
        self.b.start(None);self.b.subject=('ep','task',2,2);self.b.start(None)
        self.assertEqual(len(self.calls),2)

    def test_control_pause_version_keeps_same_semantic_wording(self):
        self.b.start(None);self.b.subject=('ep','task',1,3);self.b.start(None,True)
        self.assertEqual(len(self.calls),1)

    def test_kernel_recreation_retains_active_window(self):
        mon=self.b.runner.ObservedCompletion();mon.active=dict(operation='grasp_bowl',kind='grasp',object='bowl')
        self.assertIs(mon,self.b.runner.ObservedCompletion());self.assertIsNotNone(mon.active)
        self.assertEqual(mon.entered,3)

    def test_new_task_monitor_has_no_old_active_stage(self):
        mon=self.b.runner.ObservedCompletion();mon.active=dict(operation='grasp_bowl')
        self.b.saved_mon=None
        self.assertIsNone(self.b.runner.ObservedCompletion().active)

    def test_native_action_is_recorded_as_real_vla(self):
        self.b.apply([0]*7,'source_policy')
        _,event=self.logs[-1];self.assertTrue(event['actual_vla_action']);self.assertEqual(event['origin'],'vla_native')

    def test_observation_hold_is_not_a_vla_action(self):
        self.b.ctx=SimpleNamespace(f_locals={'phase':'hold_observe'})
        self.b.apply([0]*7,'authorized_kernel_control')
        _,event=self.logs[-1];self.assertFalse(event['actual_vla_action'])

    def test_symbolic_policy_is_recorded_as_real_vla(self):
        self.b.ctx=SimpleNamespace(f_locals={'phase':'policy'})
        self.b.apply([0]*7,'authorized_kernel_control')
        _,event=self.logs[-1];self.assertTrue(event['actual_vla_action'])


if __name__=='__main__':unittest.main()
