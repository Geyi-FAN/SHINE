"""F10: cancel only the live proposal; late bare assent cannot create a task."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names
from semantics import confirmation_answer

class CancelledProposalTests(unittest.TestCase):
    first='Push the plate to the front of the stove, but wait for my confirmation.'
    cancel='Cancel that request.'
    yes='Yes. Go ahead.'
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle'
        self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
    def tearDown(self):self.s.db.close();self.tmp.cleanup()
    def record(self,uid,text):return self.s.record_interaction(dict(episode_id=self.s.episode,input_id=uid,text=text,task_version=self.s.version))
    def cmd(self,name,text,uid,**kw):return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,user_utterance=text,voice_input_id=uid,source='qwen_realtime_current_user',**kw),uid+':'+name)
    def propose(self,uid='first'):
        self.record(uid,self.first);return self.cmd('robot_propose_task',self.first,uid,instruction='push the plate to the front of the stove')['pending_proposal']
    def reject(self,p):
        self.record('cancel',self.cancel);return self.cmd('robot_resolve_proposal',self.cancel,'cancel',proposal_id=p['proposal_id'],decision='reject')
    def test_exact_request(self):self.assertEqual(confirmation_answer(self.cancel),'reject')
    def test_this_request(self):self.assertEqual(confirmation_answer('Cancel this request.'),'reject')
    def test_the_request(self):self.assertEqual(confirmation_answer('Cancel the request!'),'reject')
    def test_old_proposal_alias_preserved(self):self.assertEqual(confirmation_answer('Cancel that proposal.'),'reject')
    def test_pending_request_is_never_started(self):
        self.propose();self.assertIsNone(self.s.task_id);self.assertEqual(self.s.action_steps,0)
    def test_cancel_record_binds_original_proposal(self):
        p=self.propose();r=self.record('cancel',self.cancel);self.assertEqual(r['confirmation'],dict(proposal_id=p['proposal_id'],decision='reject'));self.assertEqual(self.s.pending_proposal['proposal_id'],p['proposal_id']);self.assertIsNone(self.s.task_id)
    def test_rejection_is_committed_and_not_executed(self):
        p=self.propose();r=self.reject(p);self.assertEqual(r['status'],'proposal_rejected');self.assertFalse(r['executed']);self.assertIsNone(self.s.pending_proposal);self.assertIsNone(self.s.task_id);self.assertEqual(self.s.version,0)
    def test_terminal_transaction_is_formally_rejected(self):
        p=self.propose();self.reject(p);t=self.s.snapshot()['dialogue_transactions']['recent_terminal'][0];self.assertEqual(t['transaction_id'],p['proposal_id']);self.assertEqual(t['status'],'rejected');self.assertIsNone(t['consumed_by_task_id'])
    def test_late_yes_has_no_confirmation_candidate(self):
        self.reject(self.propose());self.assertNotIn('confirmation',self.record('late',self.yes));self.assertIsNone(self.s.task_id)
    def test_late_yes_cannot_directly_start_cancelled_task(self):
        self.reject(self.propose());self.record('late',self.yes)
        with self.assertRaises(TaskError):self.cmd('robot_start_task',self.yes,'late',instruction='push the plate to the front of the stove')
        self.assertIsNone(self.s.task_id);self.assertEqual(self.s.action_steps,0)
    def test_late_yes_cannot_resolve_cancelled_id(self):
        p=self.propose();self.reject(p);self.record('late',self.yes)
        with self.assertRaises(TaskError):self.cmd('robot_resolve_proposal',self.yes,'late',proposal_id=p['proposal_id'],decision='confirm')
        self.assertIsNone(self.s.task_id)
    def test_cancel_does_not_authorize_confirm(self):
        p=self.propose();self.record('cancel',self.cancel)
        with self.assertRaises(TaskError):self.cmd('robot_resolve_proposal',self.cancel,'cancel',proposal_id=p['proposal_id'],decision='confirm')
        self.assertIsNone(self.s.task_id)
    def test_reject_request_idempotent(self):
        p=self.propose();r=self.reject(p);self.assertEqual(r,self.cmd('robot_resolve_proposal',self.cancel,'cancel',proposal_id=p['proposal_id'],decision='reject'))
    def test_new_proposal_can_be_confirmed(self):
        old=self.propose();self.reject(old);new=self.propose('fresh');self.assertNotEqual(new['proposal_id'],old['proposal_id']);self.record('yes2',self.yes);r=self.cmd('robot_resolve_proposal',self.yes,'yes2',proposal_id=new['proposal_id'],decision='confirm');self.assertEqual(r['status'],'accepted');self.assertEqual(r['confirmed_proposal_id'],new['proposal_id'])
    def test_old_id_cannot_confirm_new_proposal(self):
        old=self.propose();self.reject(old);self.propose('fresh');self.record('yes2',self.yes)
        with self.assertRaises(TaskError):self.cmd('robot_resolve_proposal',self.yes,'yes2',proposal_id=old['proposal_id'],decision='confirm')
        self.assertIsNone(self.s.task_id)
    def test_full_new_command_not_blocked_by_cancelled_history(self):
        self.reject(self.propose());text='Turn on the stove.';self.record('fresh',text);r=self.cmd('robot_start_task',text,'fresh',instruction='turn on the stove');self.assertEqual(r['status'],'accepted')
    def test_stale_revision_still_rejected(self):
        p=self.propose();self.record('cancel',self.cancel)
        with self.assertRaises(TaskError):self.cmd('robot_resolve_proposal',self.cancel,'cancel',proposal_id=p['proposal_id'],transaction_id=p['proposal_id'],expected_transaction_revision=999,decision='reject')
    def test_expired_request_not_resolved(self):
        p=self.propose();self.s.pending_proposal['expires_at']=0
        with self.assertRaises(TaskError):self.reject(p)
    def test_cancel_with_no_proposal_creates_no_task(self):
        self.assertNotIn('confirmation',self.record('cancel',self.cancel));self.assertIsNone(self.s.task_id)
    def test_record_cancel_does_not_cancel_running_task(self):
        text='Turn on the stove.';self.record('start',text);self.cmd('robot_start_task',text,'start',instruction='turn on the stove');before=(self.s.task_id,self.s.version,self.s.mode);self.record('cancel',self.cancel);self.assertEqual(before,(self.s.task_id,self.s.version,self.s.mode))
    def test_question_not_decision(self):self.assertIsNone(confirmation_answer('Cancel that request?'))
    def test_quoted_not_decision(self):self.assertIsNone(confirmation_answer('He said "Cancel that request."'))
    def test_negation_not_decision(self):self.assertIsNone(confirmation_answer('Do not cancel that request.'))
    def test_extra_goal_not_silently_cancelled(self):self.assertIsNone(confirmation_answer('Cancel that request, then open the middle drawer.'))
    def test_waiting_cancellation_is_not_proposal_rejection(self):self.assertIsNone(confirmation_answer('Cancel the waiting task.'))
    def test_current_task_cancel_not_proposal_rejection(self):self.assertIsNone(confirmation_answer('Cancel the current task.'))
    def test_other_named_request_needs_interpretation(self):self.assertIsNone(confirmation_answer('Cancel the request to open the middle drawer.'))

if __name__=='__main__':unittest.main()
