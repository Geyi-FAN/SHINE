import ast,copy,unittest
from pathlib import Path
from types import SimpleNamespace
from t06l_observation_handoff import request_context,raise_proof,transform

class ObservationHandoff(unittest.TestCase):
    def fixture(self):
        active=dict(operation='cheese_bowl',kind='target',object='cheese')
        mon=SimpleNamespace(active=active,entered=100,last=120,held='none',samples=[{'width':.078}],diagnostics={})
        event=dict(event='agent_requested_observation',frame=112,request='Locate cream cheese K1.',selected_stage=copy.deepcopy(active),stage_entered=100)
        pred=dict(recovery_request='observe_above',held_object='none',evidence_frames=[120])
        recovery=SimpleNamespace(pending='agent_requested',events=[event],visual_facts=dict(pred,frame=120),grip_release_until=None)
        return mon,recovery,pred
    def test_actual_request_and_selected_stage_forwarded(self):
        mon,r,p=self.fixture();c=request_context(r,mon)
        self.assertEqual(c['planner_request'],'Locate cream cheese K1.');self.assertEqual(c['selected_stage'],mon.active);self.assertFalse(c['completion_created'])
    def test_old_stage_request_cannot_drive_new_stage(self):
        mon,r,p=self.fixture();mon.entered=116;self.assertIsNone(request_context(r,mon))
    def test_expired_request_rejected(self):
        mon,r,p=self.fixture();mon.last=200;self.assertIsNone(request_context(r,mon))
    def test_no_planner_request_no_motion(self):
        mon,r,p=self.fixture();r.events=[];self.assertIsNone(raise_proof(mon,r,p,{},120))
    def test_fresh_empty_open_placement_request_bounded(self):
        mon,r,p=self.fixture();proof=raise_proof(mon,r,p,{},120)
        self.assertEqual(proof['world_z_m'],.03);self.assertEqual(proof['attempt'],1);self.assertFalse(proof['creates_completion'])
    def test_closed_or_invalid_hand_cannot_raise(self):
        for width in [.001,.03,.0649,float('nan')]:
            mon,r,p=self.fixture();mon.samples[-1]['width']=width;self.assertIsNone(raise_proof(mon,r,p,{},120))
    def test_carried_or_unknown_object_cannot_raise(self):
        for held in ['cheese','unknown']:
            mon,r,p=self.fixture();mon.held=held;self.assertIsNone(raise_proof(mon,r,p,{},120))
    def test_other_stage_cannot_use_extension(self):
        mon,r,p=self.fixture();mon.active=dict(operation='open_middle',kind='open',object='middle_drawer');self.assertIsNone(raise_proof(mon,r,p,{},120))
    def test_stale_visual_judgement_cannot_raise(self):
        mon,r,p=self.fixture();r.visual_facts['frame']=116;self.assertIsNone(raise_proof(mon,r,p,{},120))
    def test_uncertain_observer_no_motion(self):
        mon,r,p=self.fixture();p['recovery_request']='observe_only';self.assertIsNone(raise_proof(mon,r,p,{},120))
    def test_cap_two_per_selected_stage(self):
        mon,r,p=self.fixture();self.assertIsNone(raise_proof(mon,r,p,{('cheese_bowl',100):2},120))
    def test_actual_runner_transforms_without_budget_change(self):
        path=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102/freeze/study/compat_source/run.py');src=path.read_text();old=ast.parse(src);new=transform(ast.parse(src))
        ranges=lambda tree:[ast.unparse(n.iter)for n in ast.walk(tree)if isinstance(n,ast.For)and isinstance(n.target,ast.Name)and n.target.id=='step']
        self.assertEqual(ranges(old),ranges(new));compile(new,'guarded-runner','exec')
        text=ast.unparse(new);self.assertIn('agent_requested_empty_hand_camera_raise',text);self.assertIn('stage_entered=mon.entered',text)
