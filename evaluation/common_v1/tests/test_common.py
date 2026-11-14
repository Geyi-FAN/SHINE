import unittest,sys,tempfile,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'common'))
from score import canonical_score
from controlled import adapt_source_check
from scoring_v3.attribution import causal_ids
from scoring_v4.score import persistent_scope
class CommonRules(unittest.TestCase):
 def test_t7_primary_45_not10(self):
  x=canonical_score(dict(interaction='fail',interaction45='pass',instruction='pass'),'T7');self.assertEqual(x['interaction'],'pass')
 def test_instruction_independent(self):
  x=canonical_score(dict(interaction='fail',target='pass',instruction='pass'),'T2');self.assertEqual(x['instruction'],'pass');self.assertEqual(x['joint_interaction_and_instruction'],'fail')
 def test_unknown_not_pass(self):self.assertEqual(canonical_score(dict(target='unknown'),'T4')['target'],'unknown')
 def test_t2_row_wrapper(self):self.assertEqual(canonical_score(dict(schema='t2_portable_judge_output_v1',rows=[dict(target='pass')]),'T2')['target'],'pass')
 def test_missing_t7_45_rejected(self):
  with self.assertRaises(AssertionError):canonical_score(dict(interaction='pass'),'T7')
 def test_authorization_requires_actual_audio(self):self.assertFalse(causal_ids('T1',dict(turns=[]),{},[],[])['valid'])
 def test_paused_task_metadata_not_new_goal(self):
  r=dict(turns=[dict(audio_started_wall=10,audio_ended_wall=11)],finished=dict(time=30),episode_id='E');ts=[dict(time=12,episode_id='E',task_id='old',policy_action=True),dict(time=20,episode_id='E',task_id='new',policy_action=True),dict(time=20,episode_id='OTHER',task_id='other',policy_action=True)]
  self.assertEqual(persistent_scope('T2',r,{},ts)['ids'],['new','old'])
 def test_no_retroactive_authorization(self):
  r=dict(turns=[dict(audio_started_wall=10,audio_ended_wall=11)],finished=dict(time=30),episode_id='E');es=[dict(time=15,kind='task_instruction',task_id='A')];ts=[dict(time=12,episode_id='E',task_id='A',policy_action=True)]
  self.assertEqual(causal_ids('T1',r,{},es,ts)['ids'],[])
 def test_reference_never_policy(self):
  a=dict(interaction='fail',target='fail',instruction='fail',checks=[dict(name='source_trigger_reached',status='fail')]);b=adapt_source_check(a,dict(status='fail'),dict(turns=[]));self.assertEqual(b['target'],'fail')
if __name__=='__main__':unittest.main()
