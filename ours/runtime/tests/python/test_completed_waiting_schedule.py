import sys,tempfile,time,types,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[2]/'runtime'),str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway')]
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names
from g22.completion_race import bind
class CompletedWaitingSchedule(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle'
  self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
  self.s.command('robot_start_task',dict(episode_id=self.s.episode,expected_task_version=self.s.version,instruction='put the bowl on the plate'),'source')
  self.source=self.s.task_id;self.version=self.s.version;self.s._hold('completed','test_automatic_completion');self.s.completion_status='verified';self.s.agent_execution={'completion_current_verified':True}
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def request(self,version=None,text='After the current task is finished, put the bowl on top of the cabinet.'):
  self.s.record_interaction(dict(episode_id=self.s.episode,input_id='wait',text=text,task_version=self.s.version))
  return dict(episode_id=self.s.episode,expected_task_version=self.s.version if version is None else version,user_utterance=text,voice_input_id='wait',source='qwen_realtime_current_user',instruction='put the bowl on top of the cabinet')
 def test_verified_predecessor_can_take_explicit_waiting_request(self):
  r=self.s.command('robot_schedule_task',self.request(),'queue');self.assertEqual(r['status'],'accepted');self.assertNotEqual(self.s.task_id,self.source)
  count=self.s.db.execute("SELECT count(*) FROM events WHERE kind='deferred_scheduled'").fetchone()[0];self.assertEqual(count,1)
 def test_completion_race_refreshes_only_same_recorded_input(self):
  a=self.request(self.version);record=dict(episode_id=self.s.episode,task_id=self.source,semantic_revision=self.s.task_intent_revision,version=self.version,mode='running',text=a['user_utterance'],monotonic=time.monotonic())
  b=types.SimpleNamespace(state=self.s,acceptance_decision=dict(accepted=True,subject=[self.s.episode,self.source,self.s.task_intent_revision]),token=lambda:(self.s.episode,self.s.task_id,self.s.task_intent_revision,self.s.version),log=lambda *a,**k:None)
  fixed=bind(b,'robot_schedule_task',a,{'wait':record});self.assertEqual(fixed['expected_task_version'],self.s.version);self.assertEqual(self.s.command('robot_schedule_task',fixed,'queue')['status'],'accepted')
 def test_changed_identity_cannot_refresh_old_request(self):
  a=self.request(self.version);record=dict(episode_id=self.s.episode,task_id='other-task',semantic_revision=self.s.task_intent_revision,version=self.version,mode='running',text=a['user_utterance'],monotonic=time.monotonic())
  b=types.SimpleNamespace(state=self.s,acceptance_decision={'accepted':True},token=lambda:(),log=lambda *a,**k:None)
  self.assertIs(bind(b,'robot_schedule_task',a,{'wait':record}),a)
 def test_unverified_completed_or_paused_task_does_not_dispatch(self):
  self.s.agent_execution['completion_current_verified']=False
  with self.assertRaises(TaskError):self.s.command('robot_schedule_task',self.request(),'queue')
  self.assertEqual(self.s.task_id,self.source)
 def test_nonwaiting_text_does_not_gain_scheduling_authority(self):
  with self.assertRaises(TaskError):self.s.command('robot_schedule_task',self.request(text='Put the bowl on top of the cabinet.'),'queue')
  self.assertEqual(self.s.task_id,self.source)
 def test_validated_request_is_deduplicated(self):
  a=self.request();r=self.s.command('robot_schedule_task',a,'same');again=self.s.command('robot_schedule_task',a,'same');self.assertEqual(r,again)
  self.assertEqual(self.s.db.execute("SELECT count(*) FROM events WHERE kind='deferred_scheduled'").fetchone()[0],1)
if __name__=='__main__':unittest.main()
