"""Tool-state tests without simulator/model calls; never benchmark rollouts."""
import json,unittest
from types import SimpleNamespace
from pathlib import Path
from agent_gateway import Engine,CATALOG
class Contract(unittest.TestCase):
 def engine(self,task=None):
  e=Engine.__new__(Engine);e.state=SimpleNamespace(task_id=task,version=3,mode='running'if task else'idle',instruction='old',episode='episode',task_intent_revision=1);e.agent_memory={};e.history=[];e.proposal=None;e.clarification=None;e.deferred=None;e.stage=None;e.tasks=[];e.hold_remaining=30;e.terminal_hold_ticks=10;e.fixture_hold=True;e.stage_monitor=SimpleNamespace(active={});e.log=lambda *a,**k:None;e.events=[];e.event=lambda kind,**k:e.events.append(dict(kind=kind,**k));e.say=lambda *a,**k:None;e.set_stage=lambda out:None;e.task_started=12;e.task_start_control=5;e.control_steps=91;e.user_revision=3;e.last_continuation_notice=None;e.physics_pause_latch=False;e.fixture_pause_active=False;return e
 def test_cancel_pending_proposal_really_clears_it(self):
  e=self.engine();e.proposal=dict(id='p',proposal_id='p',instruction='x');r=e.commit_agent(dict(intent='cancel',task_id=None,say='Cancelled.'));self.assertTrue(r['accepted']);self.assertIsNone(e.proposal);self.assertEqual(e.state.mode,'idle');self.assertEqual(e.events[-1]['kind'],'proposal_cancelled')
 def test_symbolic_amend_releases_fixture_without_resetting_budget(self):
  e=self.engine('task');op=CATALOG['open_middle'];task='Open the middle drawer';out=dict(intent='amend',task_id='task',complete_task=task,route='symbolic',remaining_plan=[dict(operation='open_middle')],current_subgoal_template=op['template'],reference=op['reference'],policy_prompt_template='Task: '+task+'.\nCurrent subgoal: '+op['template']+'.\nCoordinates: MAIN, 224x224, <y,x> pixels.\n');e.commit_agent(out);self.assertFalse(e.fixture_hold);self.assertEqual(e.task_started,12);self.assertEqual(e.task_start_control,5);self.assertEqual(e.state.task_id,'task');self.assertEqual(e.state.version,4)
 def test_native_tool_rejects_return_outside_its_declared_capability(self):
  e=self.engine('old');out=dict(intent='execute',complete_task='Return the bottle to its initial position',route='native',native_skill='bottle_rack',policy_prompt_template='Return the bottle to its initial position')
  with self.assertRaisesRegex(ValueError,'Native route'):e.commit_agent(out)
  self.assertEqual(e.state.version,3)
 def test_resume_redelivers_completed_stage_without_selecting_next(self):
  e=self.engine('task');e.state.mode='paused';e.stage=dict(status='completed',operation='bowl_stove',entered_step=10);e.buffer=[];e.commit_agent(dict(intent='resume',task_id='task',say='Resuming.'));self.assertTrue(e.agent_queued);self.assertIn('completed_stage',e.agent_pending);self.assertEqual(e.stage['operation'],'bowl_stove');self.assertEqual(e.task_start_control,5)
 def test_pause_clears_old_completion_queue_and_latches_physics(self):
  e=self.engine('task');e.agent_queued=True;e.agent_pending='your_selected_current_stage_verdict';e.buffer=[1];e.commit_agent(dict(intent='pause',task_id='task'));self.assertFalse(e.agent_queued);self.assertTrue(e.physics_pause_latch);self.assertEqual(e.state.mode,'paused');self.assertEqual(e.buffer,[])
 def test_finish_cannot_unpause(self):
  e=self.engine('task');e.state.mode='paused';e.physics_pause_latch=True;e.stage=dict(status='completed')
  with self.assertRaisesRegex(ValueError,'hard_paused'):e.commit_agent(dict(intent='finish',task_id='task'))
  self.assertEqual(e.state.mode,'paused');self.assertTrue(e.physics_pause_latch)
 def test_stale_agent_response_after_control_mode_change_is_rejected(self):
  e=self.engine('task');e.pending_agent_revision=e.user_revision;e.pending_agent_subject=(*e.token(),e.state.mode);self.assertTrue(e.agent_response_is_current());e.state.mode='paused';self.assertFalse(e.agent_response_is_current())
 def test_common_fixture_pause_retains_real_acceptance_speech(self):
  e=self.engine('task');e.state.mode='paused';e.fixture_pause_active=True;self.assertTrue(e.speech_mode_allows(dict(kind='execute',mode='running')));e.fixture_pause_active=False;self.assertFalse(e.speech_mode_allows(dict(kind='execute',mode='running')))
 def test_finish_cannot_claim_an_unverified_stage(self):
  e=self.engine('task');e.stage=dict(status='running')
  with self.assertRaisesRegex(ValueError,'unverified'):e.commit_agent(dict(intent='finish',task_id='task',say='Done.'))
 def test_wrong_task_identity_cannot_pause_current_task(self):
  e=self.engine('task')
  with self.assertRaisesRegex(ValueError,'identity'):e.commit_agent(dict(intent='pause',task_id='foreign'))
  self.assertEqual(e.state.mode,'running')
if __name__=='__main__':unittest.main(verbosity=2)
