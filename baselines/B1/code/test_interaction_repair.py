"""Real controller interfaces with synthetic states; no robot/model requests."""
import time, unittest
import test_tool_contract as fixture
from agent_gateway import normalize_decision_typography

class InteractionRepair(unittest.TestCase):
 def engine(self):
  e=fixture.Contract().engine('task');e.speech_jobs=[];e.playing_speech=set();e.speech_idle_since=time.monotonic()-2;e.user_speaking=False;e.input_ended_at=0;e.last_task_authorization_revision=-1
  return e
 def test_live_input_defers_finalization_without_changing_goal(self):
  e=self.engine();e.user_speaking=True
  self.assertFalse(e.completion_dialogue_ready());self.assertEqual(e.state.mode,'running')
 def test_pending_real_synthesis_blocks_next_stage_notification(self):
  e=self.engine();e.speech_jobs=[{'id':1}];self.assertFalse(e.completion_dialogue_ready())
 def test_real_playback_must_finish_before_finalization(self):
  e=self.engine();e.playing_speech.add(1);self.assertFalse(e.completion_dialogue_ready())
 def test_quiet_completed_turn_allows_finalization(self):
  self.assertTrue(self.engine().completion_dialogue_ready())
 def test_internal_stage_change_does_not_invalidate_same_task_ack(self):
  e=self.engine();job=dict(kind='execute',identity=dict(task_id='task',version=2,user_revision=e.user_revision,task_intent_revision=1))
  self.assertTrue(e.speech_identity_is_current(job))
 def test_new_user_revision_invalidates_even_same_version_speech(self):
  e=self.engine();job=dict(kind='execute',identity=dict(task_id='task',version=3,user_revision=e.user_revision-1,task_intent_revision=1))
  self.assertFalse(e.speech_identity_is_current(job))
 def test_hard_pause_disallows_stage_changed_ack(self):
  e=self.engine();e.physics_pause_latch=True;job=dict(kind='execute',identity=dict(task_id='task',version=2,user_revision=e.user_revision,task_intent_revision=1))
  self.assertFalse(e.speech_identity_is_current(job))
 def test_proposal_emits_real_public_identity(self):
  e=self.engine();e.commit_agent(dict(intent='propose',complete_task='Put the bowl on the stove',say='Please confirm.'))
  self.assertEqual(e.events[-1]['kind'],'proposal_created');self.assertEqual(e.events[-1]['proposal_id'],e.proposal['proposal_id'])
 def test_wrong_confirmation_cannot_mutate_active_stage(self):
  e=self.engine();e.proposal=dict(id='latest',proposal_id='latest');e.stage_monitor.active={'kept':True}
  with self.assertRaisesRegex(ValueError,'confirm_proposal_id'):
   e.commit_agent(dict(intent='execute',complete_task='Put the bowl on the stove.',route='native',native_skill='bowl_stove',policy_prompt_template='Put the bowl on the stove.',confirm_proposal_id='old'))
  self.assertEqual(e.stage_monitor.active,{'kept':True})
 def test_cancel_waiting_emits_real_invalidation_without_touching_source(self):
  e=self.engine();e.deferred=dict(deferred_id='q',instruction='future',predecessor_task_id='task')
  e.commit_agent(dict(intent='cancel_deferred',say='Cancelled.'))
  self.assertIsNone(e.deferred);self.assertEqual(e.events[-1],dict(kind='deferred_invalidated',deferred_id='q',reason='user_cancelled'));self.assertEqual(e.state.mode,'running');self.assertEqual(e.state.task_id,'task')
 def test_cannot_claim_nonexistent_waiting_was_cancelled(self):
  e=self.engine()
  with self.assertRaisesRegex(ValueError,'no_pending'):e.commit_agent(dict(intent='cancel_deferred'))
  self.assertEqual(e.events,[])
 def test_temporal_authorization_cannot_execute_before_source_finalized(self):
  e=self.engine();e.history=[dict(role='user',text='After this is done, put the bowl on the stove.')]
  with self.assertRaisesRegex(ValueError,'temporal authorization'):
   e.commit_agent(dict(intent='execute',complete_task='Put the bowl on the stove.',route='native',native_skill='bowl_stove',policy_prompt_template='Put the bowl on the stove.'))
  self.assertEqual(e.state.task_id,'task')
 def test_trailing_period_does_not_require_double_punctuation(self):
  d=dict(route='symbolic',complete_task='Close the drawer.',policy_prompt_template='Task: Close the drawer.\n',reference=None,current_subgoal_template='close the middle drawer using its handle')
  out=normalize_decision_typography(d);self.assertEqual(out['complete_task'],'Close the drawer');self.assertEqual(out['policy_prompt_template'],d['policy_prompt_template']);self.assertEqual(d['complete_task'],'Close the drawer.')
 def test_native_text_and_subgoal_are_not_rewritten(self):
  d=dict(route='native',complete_task='Put it there.',policy_prompt_template='Put it there.');self.assertEqual(normalize_decision_typography(d),d)
 def test_fulfilled_safety_pause_does_not_queue_redundant_model_request(self):
  e=self.engine();e.voice_log=lambda *a,**k:None;e.speech_cancel_id=0;e.speech_events=[];calls=[];e.request_agent=lambda reason:calls.append(reason)
  r=e.receive_asr(dict(text='Stop.',asr_segment=2));self.assertEqual(r['handled_by'],'exact_safety_controller');self.assertEqual(calls,[]);self.assertEqual(e.state.mode,'paused');self.assertTrue(any(x.get('role')=='user'and x.get('text')=='Stop.'for x in e.history))

if __name__=='__main__':unittest.main(verbosity=2)
