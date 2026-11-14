import copy,json,sys,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'scoring_v3'))
from oracle_boundary import public_state,assert_clean
from attribution import causal_ids
class Boundaries(unittest.TestCase):
 def test_oracle_cannot_export_global_goals(self):
  x=dict(episode_id='e',robot_state=[0]*8,native_goal_relations={'correct_answer':'SECRET'},private_contract={'next':'SECRET'},all_object_poses={'bowl':[9,9,9]},current_stage=dict(operation='return_bowl',status='completed',next_stage_answer='SECRET'),completed_events=[dict(operation='return_bowl',status='completed',native_goal_relations={'secret':True})])
  clean=public_state(x);text=json.dumps(clean);self.assertNotIn('SECRET',text);self.assertNotIn('native_goal_relations',text);self.assertEqual(clean['current_stage'],dict(operation='return_bowl',status='completed'))
 def test_history_nested_leak_is_rejected(self):
  with self.assertRaises(ValueError):assert_clean(dict(conversation=[dict(role='tool',native_goal_relations={'cheese_bowl':True})]))
 def fixture(self):
  r=dict(episode_id='e',turns=[dict(audio_started_wall=10,audio_ended_wall=12)],finished=dict(time=50));events=[dict(kind='task_instruction',time=13,task_id='new',instruction='Put it there.')];ticks=[dict(episode_id='e',time=14,policy_action=True,task_id='new')];return r,events,ticks
 def test_pronoun_and_canonical_name_same_target_attribution(self):
  r,events,ticks=self.fixture();a=causal_ids('T4',r,{},events,ticks);events[0]['instruction']='Put the bowl on the stove.';b=causal_ids('T4',r,{},events,ticks);self.assertEqual(a,b);self.assertEqual(a['ids'],['new'])
 def test_real_task_update_can_authorize_without_new_id(self):
  r,events,ticks=self.fixture();events[0]['kind']='task_updated';proof=causal_ids('T4',r,{},events,ticks);self.assertEqual(proof['ids'],['new']);self.assertEqual(proof['authorized_after'],{'new':13})
 def test_old_actions_before_same_id_update_not_credited(self):
  r,events,ticks=self.fixture();events[0]['kind']='task_updated';events[0]['time']=15;proof=causal_ids('T4',r,{},events,ticks);self.assertEqual(proof['ids'],[])
 def test_foreign_episode_is_never_credited(self):
  r,events,ticks=self.fixture();ticks[0]['episode_id']='foreign';self.assertEqual(causal_ids('T4',r,{},events,ticks)['ids'],[])
 def test_old_source_actions_are_not_new_task_authorization(self):
  r,events,ticks=self.fixture();events[0]['time']=9;self.assertEqual(causal_ids('T4',r,{},events,ticks)['ids'],[])
 def test_unconfirmed_T5_has_no_physical_authorization(self):
  r,events,ticks=self.fixture();self.assertFalse(causal_ids('T5',r,{},events,ticks)['valid'])
 def test_exactly_fourteen_preregistered_no_T6(self):
  a=json.loads((R/'data/PREFLIGHT14.private.json').read_text());self.assertEqual(len(a),14);self.assertEqual(len({x['case_uid']for x in a}),14)
  from collections import Counter
  self.assertEqual(Counter(x['branch']for x in a),dict(T1=2,T2=2,T3=2,T4=2,T5=2,T7=2,T8=2))
 def test_e3_envelope_matches_frozen_training_profile(self):
  import os,importlib.util
  os.environ['HYBRID_EXECUTOR']='pi05_e3_v4'
  p=Path('/mnt/disk_4/geyi/audio_switch_benchmark/runtimes/c3r_pi05_744_30k_r15_20261108/runtime/freeze/f28d/source/execution_profile.py')
  sp=importlib.util.spec_from_file_location('frozen_e3_profile_for_test',p);module=importlib.util.module_from_spec(sp);sp.loader.exec_module(module)
  trained=module.load_catalog();ours=json.loads((R/'config/OPERATORS.json').read_text());self.assertEqual(trained,ours)
  for op in ours.values():self.assertEqual(module.policy_template('Return the bowl then open the middle drawer',op),'Task: Return the bowl then open the middle drawer.\nCurrent subgoal: '+op['template']+'.\nCoordinates: MAIN, 224x224, <y,x> pixels.\n')
 def test_agent_request_has_no_private_case_id(self):
  p=(R/'code/agent_backend.py').read_text();self.assertNotIn('spec[',p);self.assertNotIn('private_contract',p);self.assertIn('assert_clean(context)',p)
if __name__=='__main__':unittest.main(verbosity=2)
