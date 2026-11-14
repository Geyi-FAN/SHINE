import importlib.util,sys,unittest
from pathlib import Path
P=Path(__file__).with_name('score.py');s=importlib.util.spec_from_file_location('v4score_tested',P);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Scope(unittest.TestCase):
 def fixture(self):
  return dict(episode_id='e',turns=[dict(audio_started_wall=10,audio_ended_wall=12)],finished=dict(time=80)),[dict(episode_id='e',time=13,task_id='old',policy_action=True),dict(episode_id='e',time=30,task_id='new_after_pause',policy_action=True)]
 def test_pause_does_not_erase_source_goal_authorization(self):
  r,t=self.fixture();p=m.persistent_scope('T2',r,{},t);self.assertEqual(p['ids'],['new_after_pause','old'])
 def test_goal_scope_is_invariant_to_task_id_renaming(self):
  r,t=self.fixture();p=m.persistent_scope('T2',r,{},t);[x.update(task_id='one_logical_task')for x in t];q=m.persistent_scope('T2',r,{},t);self.assertEqual(p['window'],q['window']);self.assertTrue(p['valid']and q['valid'])
 def test_foreign_episode_is_rejected(self):
  r,t=self.fixture();t[1]['episode_id']='foreign';self.assertEqual(m.persistent_scope('T2',r,{},t)['ids'],['old'])
 def test_no_real_source_audio_no_credit(self):
  r,t=self.fixture();r['turns']=[];self.assertFalse(m.persistent_scope('T2',r,{},t)['valid'])
 def test_no_t8_core_audio_no_robustness_credit(self):
  r,t=self.fixture();r['turns'][0]['prelude']=True;self.assertFalse(m.persistent_scope('T8',r,{},t)['valid'])
 def test_original_600s_scoring_window_is_retained(self):
  r,t=self.fixture();r['finished']['time']=900;t.append(dict(episode_id='e',time=700,policy_action=True,task_id='too_late'));p=m.persistent_scope('T2',r,{},t);self.assertEqual(p['window']['deadline'],612);self.assertNotIn('too_late',p['ids'])
if __name__=='__main__':unittest.main(verbosity=2)
