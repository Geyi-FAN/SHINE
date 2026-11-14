"""F05: confirmation grammar is not a location; latest proposal alone authorizes."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names,slots,command_content

class ConfirmationObjectCorrectionTests(unittest.TestCase):
 initial='Put the wine bottle on top of the cabinet, but ask me before starting.'
 corrected='Not the wine bottle. Put the bowl on top of the cabinet instead, and ask me to confirm.'
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle';self.seq=0
  self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def cmd(self,name,text,**args):
  self.seq+=1;uid='u'+str(self.seq)
  self.s.record_interaction(dict(episode_id=self.s.episode,input_id=uid,text=text,task_version=self.s.version))
  return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,user_utterance=text,voice_input_id=uid,source='qwen_realtime_current_user',**args),str(self.seq))
 def initial_proposal(self):
  r=self.cmd('robot_propose_task',self.initial,instruction='put the wine bottle on top of the cabinet')
  self.assertEqual(r['status'],'needs_confirmation');self.assertIsNone(self.s.task_id);return r['pending_proposal']
 def corrected_proposal(self):
  r=self.cmd('robot_propose_task',self.corrected,instruction='put the bowl on top of the cabinet')
  self.assertEqual(r['status'],'needs_confirmation');self.assertIsNone(self.s.task_id);return r['pending_proposal']
 def confirm(self,p,**args):
  rev=self.s.dialogue_transactions.get(p['proposal_id'])['revision']
  return self.cmd('robot_resolve_proposal','Yes, do the corrected task.',proposal_id=p['proposal_id'],transaction_id=p['proposal_id'],expected_transaction_revision=rev,decision='confirm',**args)
 def test_original_correction_creates_new_proposal_with_no_motion(self):
  old=self.initial_proposal();new=self.corrected_proposal()
  self.assertNotEqual(old['proposal_id'],new['proposal_id']);self.assertEqual(new['instruction'],'put the bowl on top of the cabinet');self.assertEqual(self.s.action_steps,0)
  self.assertNotEqual(self.s.dialogue_transactions.get(old['proposal_id'])['status'],'awaiting_confirmation')
 def test_actual_yes_consumes_only_corrected_proposal_once(self):
  old=self.initial_proposal();new=self.corrected_proposal();r=self.confirm(new)
  self.assertEqual(r['status'],'accepted');self.assertEqual(self.s.instruction,'put the bowl on top of the cabinet')
  with self.assertRaises(TaskError):self.confirm(new)
  self.assertEqual(self.s.task_id,r['task_id']);self.assertEqual(self.s.action_steps,0)
 def test_old_confirmation_cannot_start_wine_task(self):
  old=self.initial_proposal();self.corrected_proposal()
  with self.assertRaises(TaskError):self.confirm(old)
  self.assertIsNone(self.s.task_id)
 def test_explicit_start_request_still_requires_confirmation(self):
  self.initial_proposal();r=self.cmd('robot_start_task',self.corrected,instruction='put the bowl on top of the cabinet')
  self.assertEqual(r['status'],'needs_confirmation');self.assertIsNone(self.s.task_id)
 def test_source_cannot_remain_old_wine_bottle(self):
  self.initial_proposal()
  with self.assertRaises(TaskError):self.cmd('robot_propose_task',self.corrected,instruction='put the wine bottle on top of the cabinet')
  self.assertIsNone(self.s.task_id)
 def test_unchanged_destination_cannot_be_replaced(self):
  self.initial_proposal()
  with self.assertRaises(TaskError):self.cmd('robot_propose_task',self.corrected,instruction='put the bowl on the stove')
  self.assertIsNone(self.s.task_id)
 def test_confirmation_infinitive_is_not_a_target(self):
  self.assertEqual([n for role,n in slots(self.corrected)if role=='target'],['top of the cabinet'])
 def test_confirmation_words_remain_in_raw_proposal(self):
  self.initial_proposal();new=self.corrected_proposal();self.assertEqual(new['user_utterance'],self.corrected)
  self.assertIn('ask me',command_content(self.corrected).lower())
 def test_real_unknown_target_still_rejected(self):
  with self.assertRaises(TaskError):self.cmd('robot_propose_task','Put the bowl on confirm, and ask me to confirm.',instruction='put the bowl on the plate')
 def test_other_positive_object_not_hardcoded(self):
  r=self.cmd('robot_propose_task','Not the bowl. Put the wine bottle on top of the cabinet instead, and ask me to confirm.',instruction='put the wine bottle on top of the cabinet')
  self.assertEqual(r['status'],'needs_confirmation');self.assertIsNone(self.s.task_id)
 def test_true_action_prohibition_cannot_be_dropped(self):
  with self.assertRaises(TaskError):self.cmd('robot_propose_task','Do not move the wine bottle. Put the bowl on the plate and ask me to confirm.',instruction='put the bowl on the plate')
 def test_wrong_revision_cannot_authorize_corrected_task(self):
  self.initial_proposal();p=self.corrected_proposal()
  with self.assertRaises(TaskError):self.cmd('robot_resolve_proposal','Yes, do the corrected task.',proposal_id=p['proposal_id'],transaction_id=p['proposal_id'],expected_transaction_revision=999,decision='confirm')
  self.assertIsNone(self.s.task_id)
 def test_expired_corrected_proposal_cannot_execute(self):
  self.initial_proposal();p=self.corrected_proposal();self.s.pending_proposal['expires_at']=0
  with self.assertRaises(TaskError):self.confirm(p)
  self.assertIsNone(self.s.task_id)

if __name__=='__main__':unittest.main()
