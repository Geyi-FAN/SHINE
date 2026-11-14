"""F03: explicit current answers ground both roles without authorizing guesses."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names

class TwoSlotClarificationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle';self.seq=0
  self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def cmd(self,name,text,input_id,**kwargs):
  self.seq+=1;self.s.record_interaction(dict(episode_id=self.s.episode,input_id=input_id,text=text,task_version=self.s.version))
  return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,user_utterance=text,voice_input_id=input_id,source='qwen_realtime_current_user',**kwargs),str(self.seq))
 def begin(self,text='Put it over there.',question='Which object should I put where?',missing_slot='object'):
  return self.cmd('robot_begin_clarification',text,'u1',question=question,missing_slot=missing_slot)['pending_clarification']
 def answer(self,p,text='Put the cream cheese in the bowl.',instruction='put the cream cheese in the bowl',question=None,**kwargs):
  row=self.s.dialogue_transactions.get(p['clarification_id']);return self.cmd('robot_answer_clarification',text,'a'+str(self.seq),clarification_id=p['clarification_id'],transaction_id=p['clarification_id'],expected_transaction_revision=row['revision'],**({'question':question}if question else{'instruction':instruction}),**kwargs)
 def test_original_full_answer_roles_and_provenance(self):
  p=self.begin();r=self.answer(p);self.assertEqual(r['status'],'accepted');e=self.s.task_record['clarification_evidence']
  self.assertEqual(e['source_utterances'][0]['text'],'Put it over there.');self.assertEqual(e['source_utterances'][1]['text'],'Put the cream cheese in the bowl.')
  t=e['active_source_utterances'][0];self.assertEqual(t['text'].strip(),'Put the cream cheese in the bowl.')
  b={x['slot']:x for x in t['slot_bindings']};self.assertEqual(b['object']['bound_entity'],'cheese');self.assertEqual(b['destination']['bound_entity'],'bowl');self.assertEqual(b['destination']['relation'],'in')
  self.assertEqual(b['object']['answer_input_id'],e['source_utterances'][1]['input_id']);self.assertEqual(b['destination']['answer_input_id'],b['object']['answer_input_id']);self.assertEqual(self.s.action_steps,0)
 def test_object_then_destination(self):
  p=self.begin(question='Which object should I move?');r=self.answer(p,text='The cream cheese.',question='Where should I put it?');self.assertEqual(r['status'],'needs_clarification');self.assertIsNone(self.s.task_id)
  p=r['pending_clarification'];r=self.answer(p,text='In the bowl.');self.assertEqual(r['status'],'accepted');e=self.s.task_record['clarification_evidence'];b={x['slot']:x for x in e['active_source_utterances'][0]['slot_bindings']};self.assertNotEqual(b['object']['answer_input_id'],b['destination']['answer_input_id'])
 def test_destination_then_object(self):
  p=self.begin(question='Where should I put it?',missing_slot='destination');r=self.answer(p,text='In the bowl.',question='Which object should I put in the bowl?');self.assertIsNone(self.s.task_id)
  self.assertEqual(self.answer(r['pending_clarification'],text='The cream cheese.')['status'],'accepted')
 def test_a_different_explicit_task_is_not_hardcoded(self):
  p=self.begin();self.assertEqual(self.answer(p,text='Put the wine bottle on top of the cabinet.',instruction='put the wine bottle on top of the cabinet')['status'],'accepted')
 def test_only_object_cannot_authorize_guessed_destination(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,text='The cream cheese.')
  self.assertIsNone(self.s.task_id)
 def test_only_destination_cannot_authorize_guessed_object(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,text='In the bowl.')
  self.assertIsNone(self.s.task_id)
 def test_unknown_deictic_answer_does_not_fill_slots(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,text='Put it over there.')
  self.assertIsNone(self.s.task_id)
 def test_no_answer_never_allows_a_guessed_task(self):
  with self.assertRaises(TaskError):self.cmd('robot_start_task','Put it over there.','u1',instruction='put the cream cheese in the bowl')
  self.assertIsNone(self.s.task_id)
 def test_yes_is_not_a_two_slot_answer(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,text='Yes.')
  self.assertIsNone(self.s.task_id)
 def test_generated_destination_cannot_change(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,instruction='put the cream cheese on the stove')
  self.assertIsNone(self.s.task_id)
 def test_source_destination_cannot_swap(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.answer(p,instruction='put the bowl in the cream cheese')
  self.assertIsNone(self.s.task_id)
 def test_containment_cannot_become_surface(self):
  p=self.begin()
  with self.assertRaisesRegex(TaskError,'clarification_destination_relation_mismatch'):self.answer(p,instruction='put the cream cheese on the bowl')
  self.assertIsNone(self.s.task_id)
 def test_explicit_confirmation_still_required(self):
  p=self.begin('Put it over there, but ask me before starting.');self.assertEqual(self.answer(p)['status'],'needs_confirmation');self.assertIsNone(self.s.task_id);self.assertEqual(self.s.action_steps,0)
 def test_original_persistent_constraint_is_not_dropped(self):
  p=self.begin('Put it over there, and keep the stove in its current state.')
  with self.assertRaises(TaskError):self.answer(p)
  self.assertIsNone(self.s.task_id)
 def test_two_deictic_placements_need_more_information(self):
  p=self.begin('Put it over there, then put it over there.')
  with self.assertRaises(TaskError):self.answer(p)
  self.assertIsNone(self.s.task_id)
 def test_expired_transaction_is_rejected(self):
  p=self.begin();self.s.pending_clarification['expires_at']=0
  with self.assertRaises(TaskError):self.answer(p)
  self.assertIsNone(self.s.task_id)
 def test_wrong_transaction_revision_is_rejected(self):
  p=self.begin()
  with self.assertRaises(TaskError):self.cmd('robot_answer_clarification','Put the cream cheese in the bowl.','a1',clarification_id=p['clarification_id'],transaction_id=p['clarification_id'],expected_transaction_revision=999,instruction='put the cream cheese in the bowl')
  self.assertIsNone(self.s.task_id)

if __name__=='__main__':unittest.main()
