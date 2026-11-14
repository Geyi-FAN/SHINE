import copy
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
sys.path[:0]=[str(B),str(B/'freeze/f28d/source')]
import stage_lifecycle
from observed_completion import DESTINATIONS
from c3r.integration import stage_errors
from t01r_reacquisition import install,bind_logger

PLACE=dict(operation='bowl_stove',kind='target',object='bowl')
GRASP=dict(operation='grasp_bowl',kind='grasp',object='bowl')
RETURN=dict(operation='return_bowl',kind='return',object='bowl')

class Reacquisition(unittest.TestCase):
    def setUp(self):
        self.module=SimpleNamespace(classify=stage_lifecycle.classify)
        self.old=self.module.classify;install(self.module,DESTINATIONS)
        self.visual=dict(frame=100,held_object='none',support_visible={'bowl':True})
        self.plan=[copy.deepcopy(GRASP),copy.deepcopy(PLACE)]
    def classify(self,**changes):
        args=dict(active=PLACE,plan=self.plan,frame=103,width=.075,held='none',visual=self.visual);args.update(changes)
        return self.module.classify(**args)
    def test_actual_prior_c3r_rejects_valid_placement_reacquisition(self):
        r=self.old(PLACE,self.plan,103,.075,'none',self.visual);self.assertEqual(r['mode'],'reject')
    def test_observed_same_object_grasp_preserves_unfinished_target(self):
        r=self.classify();self.assertEqual(r['mode'],'interrupt_for_reacquisition');self.assertTrue(r['unfinished_goal_retained']);self.assertFalse(r['creates_completion'])
    def test_same_stage_keeps_original_clock(self):self.assertEqual(self.classify(plan=[PLACE])['mode'],'keep')
    def test_original_return_reacquisition_unchanged(self):
        r=self.classify(active=RETURN,plan=[GRASP,RETURN]);self.assertEqual(r['mode'],'interrupt_for_reacquisition');self.assertIn('unfinished_return',r['reason'])
    def test_next_goal_must_be_same_unfinished_placement(self):
        self.assertEqual(self.classify(plan=[GRASP,dict(operation='bowl_plate',kind='target',object='bowl')])['mode'],'reject')
    def test_missing_unfinished_goal_rejected(self):self.assertEqual(self.classify(plan=[GRASP])['mode'],'reject')
    def test_wrong_object_rejected(self):
        self.assertEqual(self.classify(plan=[dict(operation='grasp_cheese',kind='grasp',object='cheese'),PLACE])['mode'],'reject')
    def test_unknown_grasp_name_rejected(self):
        self.assertEqual(self.classify(plan=[dict(operation='pick_bowl',kind='grasp',object='bowl'),PLACE])['mode'],'reject')
    def test_unknown_target_not_broadened(self):
        a=dict(operation='stove_on',kind='target',object='bowl');self.assertEqual(self.classify(active=a,plan=[GRASP,a])['mode'],'reject')
    def test_close_operation_not_broadened(self):
        a=dict(operation='close_middle',kind='close',object='bowl');self.assertEqual(self.classify(active=a,plan=[GRASP,a])['mode'],'reject')
    def test_stale_or_future_observation_rejected(self):
        for frame in [99,109]:self.assertEqual(self.classify(frame=frame)['mode'],'reject')
    def test_missing_visual_proof_rejected(self):self.assertEqual(self.classify(visual=None)['mode'],'reject')
    def test_unknown_support_rejected(self):
        v=copy.deepcopy(self.visual);v['support_visible']['bowl']=None;self.assertEqual(self.classify(visual=v)['mode'],'reject')
    def test_unsupported_object_rejected(self):
        v=copy.deepcopy(self.visual);v['support_visible']['bowl']=False;self.assertEqual(self.classify(visual=v)['mode'],'reject')
    def test_currently_held_object_rejected(self):self.assertEqual(self.classify(held='bowl')['mode'],'reject')
    def test_contradictory_visual_held_rejected(self):
        v=copy.deepcopy(self.visual);v['held_object']='bowl';self.assertEqual(self.classify(visual=v)['mode'],'reject')
    def test_closed_unknown_or_nonfinite_fingers_rejected(self):
        for width in [.001,.05,float('nan'),None]:self.assertEqual(self.classify(width=width)['mode'],'reject')
    def test_actual_c3r_validator_preserves_unrelated_validation_errors(self):
        mon=SimpleNamespace(active=PLACE,last=103,samples=[{'width':.075}],held='none')
        bridge=SimpleNamespace(saved_mon=mon,saved_recovery=SimpleNamespace(visual_facts=self.visual),log=lambda *a,**kw:None)
        prior=lambda i,o:['ACTIVE_STAGE_NOT_RETIRED: unfinished','BAD_COORDINATE_REFERENCE']
        with patch.object(stage_lifecycle,'classify',self.module.classify):
            r=stage_errors(bridge,prior,{},dict(status='plan_ready',remaining_plan=self.plan))
        self.assertEqual(r,['BAD_COORDINATE_REFERENCE'])
    def test_actual_stage_apply_does_not_fabricate_completion(self):
        class Mon:
            def __init__(self):self.active=copy.deepcopy(PLACE);self.events=[];self.selections=[]
            def select(self,stage):self.active=copy.deepcopy(stage);self.selections.append(stage)
        mon=Mon();stage_lifecycle.apply(mon,GRASP,self.classify());self.assertEqual(mon.events,[]);self.assertEqual(mon.active,GRASP)
    def test_input_plan_and_visual_not_rewritten(self):
        before=copy.deepcopy([self.plan,self.visual]);self.classify();self.assertEqual([self.plan,self.visual],before)
    def test_idempotent_install_and_evidence_log(self):
        before=self.module.classify;install(self.module,DESTINATIONS);self.assertIs(before,self.module.classify)
        records=[];bind_logger(lambda name,**kw:records.append((name,kw)));self.classify();bind_logger(None)
        self.assertEqual(records[0][0],'t01r_placement_reacquisition_admitted');self.assertFalse(records[0][1]['creates_completion'])

if __name__=='__main__':unittest.main(verbosity=2)
