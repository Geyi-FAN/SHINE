import copy,time,unittest
from types import SimpleNamespace as N
from g22.completion_race import bind
class RaceTests(unittest.TestCase):
 def setUp(self):
  s=N(episode='e',task_id='t',task_intent_revision=2,version=4,mode='completed',completion_status='verified');self.b=N(state=s,acceptance_decision=dict(accepted=True,subject=['e','t',2]),token=lambda:('e',self.b.state.task_id,self.b.state.task_intent_revision,self.b.state.version),log=lambda *a,**kw:None)
  self.args=dict(episode_id='e',expected_task_version=3,user_utterance='Put the bowl on the plate instead.',voice_input_id='i',source='qwen_realtime_current_user');self.intake={'i':dict(episode_id='e',task_id='t',semantic_revision=2,version=3,mode='running',text=self.args['user_utterance'],monotonic=time.monotonic())}
 def test_only_auto_complete_rebinds_version(self):
  updated=bind(self.b,'robot_revise_task',self.args,self.intake);self.assertEqual(updated['expected_task_version'],4);self.assertEqual(self.args['expected_task_version'],3)
 def test_missing_record_rejected(self):self.assertIs(bind(self.b,'robot_revise_task',self.args,{}),self.args)
 def test_new_task_rejected(self):self.b.state.task_id='other';self.assertIs(bind(self.b,'robot_revise_task',self.args,self.intake),self.args)
 def test_pause_is_not_completion(self):self.b.state.mode='paused';self.assertIs(bind(self.b,'robot_revise_task',self.args,self.intake),self.args)
 def test_changed_intent_rejected(self):self.b.state.task_intent_revision=3;self.assertIs(bind(self.b,'robot_revise_task',self.args,self.intake),self.args)
 def test_mismatched_text_rejected(self):self.args['user_utterance']='different';self.assertIs(bind(self.b,'robot_revise_task',self.args,self.intake),self.args)
 def test_unverified_terminal_rejected(self):self.b.acceptance_decision['accepted']=False;self.assertIs(bind(self.b,'robot_revise_task',self.args,self.intake),self.args)
 def test_multiple_version_changes_rejected(self):self.b.state.version=5;self.assertIs(bind(self.b,'robot_revise_task',self.args,self.intake),self.args)
 def test_old_audio_rejected(self):self.intake['i']['monotonic']-=31;self.assertIs(bind(self.b,'robot_revise_task',self.args,self.intake),self.args)
 def test_other_tool_not_rebound(self):self.assertIs(bind(self.b,'robot_resume',self.args,self.intake),self.args)
if __name__=='__main__':unittest.main()
