"""Input-start/ASR races, including negative and stale-session cases."""
import sys,tempfile,unittest
from pathlib import Path
R=Path(__file__).resolve().parents[1];sys.path[:0]=[str(R/'robot_gateway'),str(R)]
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names
class SpeechGuards(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle';self.seq=0
  self.s.scene_inventory=inventory_from_names(v[0] for v in ENTITIES.values())
  self.cmd('robot_start_task',instruction='open the middle drawer')
  self.cmd('robot_schedule_task',instruction='put the cream cheese in the bowl',source='qwen_realtime_current_user',user_utterance='After this task finishes, put the cheese in the bowl.',voice_input_id='old')
  self.old=self.s.task_id;self.slot=self.s.deferred_task['deferred_id']
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def cmd(self,name,**kw):
  self.seq+=1;return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,**kw),str(self.seq))
 def speech(self,phase,lease='a',**kw):return self.s.record_speech_activity(dict(phase=phase,episode_id=self.s.episode,deferred_id=self.slot,lease_id=lease,**kw))
 def record(self,text,id='text'):self.s.record_interaction(dict(episode_id=self.s.episode,input_id=id,text=text))
 def done(self):self.s._hold('completed','fixture_complete');self.s.completion_status='verified';self.s._run_deferred()
 def test_audio_defers_handoff_without_pausing_predecessor(self):
  self.speech('started');self.assertEqual(self.s.mode,'running');self.done();self.assertEqual(self.s.task_id,self.old)
 def test_replacement_after_delayed_asr_cannot_execute_old_successor(self):
  self.speech('started');self.done();raw='Replace the cute task with putting the wine bottle on the cabinet. Continue the current task first.'
  self.record(raw);self.speech('transcribed',input_id='text');self.s._run_deferred();self.assertEqual(self.s.task_id,self.old)
  self.cmd('robot_replace_deferred',deferred_id=self.slot,instruction='put the wine bottle on top of the cabinet',source='qwen_realtime_current_user',user_utterance=raw,voice_input_id='text')
  self.assertIn('wine bottle',self.s.instruction);self.s._run_deferred();self.assertEqual(sum(e['kind']=='deferred_started' for e in self.s.timeline(limit=200)['events']),1)
 def test_question_releases_only_after_recorded_final_text(self):
  self.speech('started');self.done();self.record('Where is the bowl?');self.speech('transcribed',input_id='text');self.s._run_deferred();self.assertNotEqual(self.s.task_id,self.old)
 def test_backchannel_releases_handoff(self):
  self.speech('started');self.done();self.record('Thank you.');self.speech('transcribed',input_id='text');self.s._run_deferred();self.assertNotEqual(self.s.task_id,self.old)
 def test_rejected_noise_allows_handoff(self):
  self.speech('started');self.done();self.speech('rejected',reason='semantic_vad_rejected');self.s._run_deferred();self.assertNotEqual(self.s.task_id,self.old)
 def test_old_replay_cannot_clear_new_or_other_unresolved_input(self):
  self.speech('started','a');self.speech('started','b');self.done();self.record('Where is the bowl?');self.speech('transcribed','a',input_id='text');self.speech('transcribed','a',input_id='text');self.s._run_deferred();self.assertEqual(self.s.task_id,self.old)
  self.assertIn('b',self.s.deferred_task['speech_input_guards']);self.speech('rejected','b',reason='semantic_vad_rejected');self.s._run_deferred();self.assertNotEqual(self.s.task_id,self.old)
 def test_expired_or_reconnected_unresolved_audio_never_auto_starts(self):
  self.speech('started');self.s.deferred_task['speech_input_guards']['a']['expires_at']=0;self.done();self.s._run_deferred();self.assertEqual(self.s.task_id,self.old);self.assertEqual(self.s.deferred_task['speech_input_guards']['a']['phase'],'needs_input')
  self.assertEqual(sum(e['kind']=='deferred_audio_guard_expired' for e in self.s.timeline(limit=200)['events']),1)
 def test_unrecorded_transcript_cannot_release(self):
  self.speech('started');self.done()
  with self.assertRaises(TaskError):self.speech('transcribed',input_id='not-recorded')
  self.s._run_deferred();self.assertEqual(self.s.task_id,self.old)
 def test_unknown_new_command_is_not_permission_for_old_queue(self):
  self.speech('started');self.done();self.record('Do something different now.');result=self.speech('transcribed',input_id='text');self.assertEqual(result['status'],'awaiting_decision');self.s._run_deferred();self.assertEqual(self.s.task_id,self.old)
 def test_stale_episode_and_slot_cannot_modify_guard(self):
  self.speech('started')
  for patch in [dict(episode_id='old'),dict(deferred_id='old')]:
   with self.assertRaises(TaskError):self.s.record_speech_activity(dict(dict(phase='rejected',reason='semantic_vad_rejected',episode_id=self.s.episode,deferred_id=self.slot,lease_id='a'),**patch))
 def test_duplicate_start_is_idempotent(self):
  self.speech('started');guard=dict(self.s.deferred_task['speech_input_guards']['a']);self.speech('started');self.assertEqual(self.s.deferred_task['speech_input_guards']['a'],guard)
 def test_pause_then_resume_keeps_queue_and_resolves_only_committed_resume_input(self):
  self.speech('started','pause');self.record('Pause, but keep the queued task.','pause-text')
  self.speech('transcribed','pause',input_id='pause-text')
  self.cmd('robot_pause',user_utterance='Pause, but keep the queued task.',voice_input_id='pause-text')
  self.assertEqual(self.s.deferred_task['deferred_id'],self.slot)
  self.speech('started','resume');self.record('Resume the original task.','resume-text');self.speech('transcribed','resume',input_id='resume-text')
  self.cmd('robot_resume',voice_input_id='resume-text',user_utterance='Resume the original task.')
  self.assertFalse(self.s.deferred_task['speech_input_guards']);self.assertEqual(self.s.deferred_task['deferred_id'],self.slot)
  self.done();self.assertNotEqual(self.s.task_id,self.old)
if __name__=='__main__':unittest.main(verbosity=2)
