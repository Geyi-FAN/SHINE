"""Destination answers replace only a current open validation slot, preserving meaning."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names

class DestinationPlaceholderTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle';self.seq=0
  self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def cmd(self,name,text,identifier,**args):
  self.seq+=1;self.s.record_interaction(dict(episode_id=self.s.episode,input_id=identifier,text=text,task_version=self.s.version))
  return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,user_utterance=text,voice_input_id=identifier,source='qwen_realtime_current_user',**args),str(self.seq))
 def begin(self,text='Please put the bowl in a different place.'):
  return self.cmd('robot_begin_clarification',text,'u1',question='Where should I put the bowl?',missing_slot='destination')['pending_clarification']
 def answer(self,p,text='Put it on the stove, please.',instruction='put the bowl on the stove'):
  row=self.s.dialogue_transactions.get(p['clarification_id'])
  return self.cmd('robot_answer_clarification',text,'u2',clarification_id=p['clarification_id'],transaction_id=p['clarification_id'],expected_transaction_revision=row['revision'],instruction=instruction)
 def test_original_f02_destination_only_answer(self):
  p=self.begin();r=self.answer(p);self.assertEqual(r['status'],'accepted');e=self.s.task_record['clarification_evidence']
  self.assertEqual(e['source_utterances'][0]['text'],'Please put the bowl in a different place.')
  self.assertEqual(e['source_utterances'][1]['text'],'Put it on the stove, please.')
  self.assertEqual(e['active_source_utterances'][0]['text'].strip(),'Please put the bowl on the stove.')
  b=e['active_source_utterances'][0]['slot_bindings'][0];self.assertEqual((b['slot'],b['bound_entity'],b['answer_input_id'],b['relation']),('destination','stove','u2','on'))
  self.assertEqual(self.s.action_steps,0)
 def test_original_full_answer_branch(self):self.assertEqual(self.answer(self.begin(),text='Please put the bowl on the stove.')['status'],'accepted')
 def test_bare_destination_phrase(self):self.assertEqual(self.answer(self.begin(),text='On the stove, please.')['status'],'accepted')
 def test_another_location_and_different_valid_target(self):
  p=self.begin('Please put the bowl to another location.');self.assertEqual(self.answer(p,text='On the plate.',instruction='put the bowl on the plate')['status'],'accepted')
 def test_no_guess_before_answer(self):
  with self.assertRaisesRegex(TaskError,'destination_reference_unresolved'):self.cmd('robot_start_task','Please put the bowl in a different place.','u1',instruction='put the bowl on the stove')
  self.assertIsNone(self.s.task_id)
 def test_unresolved_answer_still_rejected(self):
  p=self.begin()
  with self.assertRaisesRegex(TaskError,'clarification_invented_entity'):self.answer(p,text='Somewhere else.')
  self.assertIsNone(self.s.task_id)
 def test_alternatives_are_not_a_selected_destination(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,text='On the stove or the plate.')
  self.assertIsNone(self.s.task_id)
 def test_agent_cannot_change_answer_destination(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,instruction='put the bowl on the plate')
  self.assertIsNone(self.s.task_id)
 def test_agent_cannot_change_named_original_object(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,instruction='put the wine bottle on the stove')
  self.assertIsNone(self.s.task_id)
 def test_answer_cannot_silently_replace_named_object(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,text='Put the cheese on the stove.',instruction='put the cheese on the stove')
  self.assertIsNone(self.s.task_id)
 def test_relation_cannot_change_surface_to_containment(self):
  p=self.begin()
  with self.assertRaisesRegex(TaskError,'clarification_destination_relation_mismatch'):self.answer(p,instruction='put the bowl in the stove')
  self.assertIsNone(self.s.task_id)
 def test_confirmation_permission_preserved(self):
  p=self.begin('Please put the bowl in a different place, but ask me before starting.')
  self.assertEqual(self.answer(p)['status'],'needs_confirmation');self.assertIsNone(self.s.task_id)
 def test_named_destination_is_not_an_open_placeholder(self):
  p=self.begin('Please put the bowl on the plate.')
  with self.assertRaises(TaskError):self.answer(p)
  self.assertIsNone(self.s.task_id)
 def test_two_open_destinations_need_more_information(self):
  p=self.begin('Put the bowl in a different place, then put the cheese in another place.')
  with self.assertRaises(TaskError):self.answer(p)
  self.assertIsNone(self.s.task_id)
 def test_expired_answer_still_rejected(self):
  p=self.begin();self.s.pending_clarification['expires_at']=0
  with self.assertRaises(TaskError):self.answer(p)
  self.assertIsNone(self.s.task_id)

if __name__=='__main__':unittest.main()
