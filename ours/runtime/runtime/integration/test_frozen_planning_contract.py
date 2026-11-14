"""Synthetic counterexamples of the actual frozen validator, not model accuracy."""
import copy,json,os,sys,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.dont_write_bytecode=True
os.environ['HYBRID_EXECUTOR']='smolvla_e3_v4';os.environ['PLANNING_HANDOFF_REPAIR']='1';os.environ['PLANNING_RELATION_REPAIR']='1'
sys.path.insert(0,str(B/'freeze/f28d/source'))
from planner import CATALOG,validate
from execution_profile import policy_template

class FrozenPlanningTests(unittest.TestCase):
 def setUp(self):
  self.inp=dict(user_message='Return the bowl to its episode-start position and release it stably, then open the middle drawer',physical_state=dict(source='s1_rgb_proprio_estimates',observed_step=0,held_object='bowl',objects={},drawers={},robot={}),completed_events=[],reference_availability=[],episode_id='synthetic',task_version=1,frame=0,mode='validation_counterexample')
 def stage(self,name):
  op=CATALOG[name];return dict(operation=name,kind=op['kind'],object=op['object'],goal='return the bowl and release it stably'if op['kind']=='return'else'achieve requested physical state')
 def ready(self,name):
  op=CATALOG[name];return dict(status='plan_ready',complete_task=self.inp['user_message'],remaining_plan=[self.stage(name)],reference=op['reference'],current_subgoal_template=op['template'],policy_prompt_template=policy_template(self.inp['user_message'],op),request=None)
 def available(self,name,available=True):
  ref=CATALOG[name]['reference']
  if ref:self.inp['reference_availability'].append(dict(ref,available=available))
 def test_missing_current_blocks_ready(self):
  errors=validate(self.inp,self.ready('return_bowl'));self.assertTrue(any('current reference unavailable'in e for e in errors))
 def test_missing_future_does_not_block_current(self):
  self.available('return_bowl');self.inp['reference_availability'].append(dict(time_source='current',entity='middle_handle',keypoint='K1',available=False));self.assertEqual(validate(self.inp,self.ready('return_bowl')),[])
 def test_wrong_time_source_rejected(self):
  self.available('return_bowl');out=self.ready('return_bowl');out['reference']=dict(out['reference'],time_source='instruction_takeover');self.assertTrue(any('reference does not match'in e for e in validate(self.inp,out)))
 def test_wrong_subgoal_text_rejected(self):
  self.available('return_bowl');out=self.ready('return_bowl');out['current_subgoal_template']='release at takeover';self.assertTrue(any('exact training template'in e for e in validate(self.inp,out)))
 def test_stable_release_omission_rejected(self):
  self.available('return_bowl');out=self.ready('return_bowl');out['remaining_plan'][0]['goal']='return the bowl';self.assertTrue(any('stable release'in e for e in validate(self.inp,out)))
 def test_hold_has_no_executable_prompt(self):
  out=self.ready('return_bowl');out['status']='hold';self.assertTrue(any('must not execute'in e for e in validate(self.inp,out)))
 def test_hold_requires_no_pending_plan(self):
  out=self.ready('return_bowl');out.update(status='hold',reference=None,current_subgoal_template=None,policy_prompt_template=None);self.assertTrue(any('empty plan'in e for e in validate(self.inp,out)))
 def test_object_type_mismatch_rejected(self):
  self.available('return_bowl');out=self.ready('return_bowl');out['remaining_plan'][0]['object']='cheese';self.assertTrue(any('kind/object mismatch'in e for e in validate(self.inp,out)))
 def test_no_numeric_prompt_invention(self):
  self.available('return_bowl');out=self.ready('return_bowl');out['policy_prompt_template']=out['policy_prompt_template'].replace('{episode_start.bowl.K2}','<1,2>');self.assertTrue(any('prompt envelope inconsistent'in e for e in validate(self.inp,out)))
 def test_clarification_never_executes(self):
  out=self.ready('return_bowl');out['status']='need_clarification';out['request']='Which object?';self.assertTrue(any('must not execute'in e for e in validate(self.inp,out)))
 def test_supported_drawer_does_not_require_handle_coordinate(self):
  self.assertIsNone(CATALOG['open_middle']['reference']);self.assertIsNone(CATALOG['close_top']['reference'])
 def test_catalog_exact22(self):self.assertEqual(len(CATALOG),22)

if __name__=='__main__':unittest.main(verbosity=2)
