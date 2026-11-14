"""Real F02 failure: source acoustic correction was lost at clarification join."""
import sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime/freeze/voice/robot_gateway'))
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names
class ClarificationAcoustics(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle'
  self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values());self.seq=0
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def begin(self,proof=True,primary='Please put the ball in a different place.',alternative='Please put the bowl in a different place.',**changes):
  e=dict(kind='audio_only_grounding.v2',primary=primary,transcript=alternative,reference_sent=False,scene_sent=False);e.update(changes)
  self.s.record_interaction(dict(episode_id=self.s.episode,input_id='original',text=primary,task_version=self.s.version,**({'asr_evidence':e}if proof else{})))
  return self.s.command('robot_begin_clarification',dict(episode_id=self.s.episode,expected_task_version=self.s.version,user_utterance=primary,voice_input_id='original',source='qwen_realtime_current_user',question='Where should I put the bowl?',missing_slot='destination'),'begin')['pending_clarification']
 def answer(self,p,text='Put it on the stove, please.',instruction='Put the bowl on the stove.'):
  self.s.record_interaction(dict(episode_id=self.s.episode,input_id='answer',text=text,task_version=self.s.version));tx=self.s.dialogue_transactions.get(p['clarification_id'])
  return self.s.command('robot_answer_clarification',dict(episode_id=self.s.episode,expected_task_version=self.s.version,user_utterance=text,voice_input_id='answer',source='qwen_realtime_current_user',clarification_id=p['clarification_id'],transaction_id=p['clarification_id'],expected_transaction_revision=tx['revision'],instruction=instruction),'answer')
 def test_audio_supported_source_survives_join_and_raw_is_preserved(self):
  p=self.begin();self.assertEqual(self.answer(p)['status'],'accepted');e=self.s.task_record['clarification_evidence']
  self.assertIn('ball',e['source_utterances'][0]['text']);self.assertIn('bowl',e['active_source_utterances'][0]['text']);self.assertEqual(e['source_utterances'][0]['acoustic_source_evidence']['source_input_id'],'original');self.assertEqual(self.s.action_steps,0)
 def test_no_acoustic_proof_cannot_use_agent_question_as_authority(self):
  with self.assertRaises(TaskError):self.answer(self.begin(proof=False))
 def test_reference_or_scene_assisted_guess_cannot_supply_entity(self):
  for change in[dict(reference_sent=True),dict(scene_sent=True),dict(primary='a different input')]:
   with self.subTest(change=change):
    # Separate states preserve actual transaction/input deduplication semantics.
    self.tearDown();self.setUp()
    with self.assertRaises(TaskError):self.answer(self.begin(**change))
 def test_known_entity_cannot_be_replaced_by_relisten(self):
  with self.assertRaises(TaskError):self.answer(self.begin(primary='Please put the plate in a different place.'))
 def test_acoustic_reconciliation_cannot_change_action(self):
  with self.assertRaises(TaskError):self.answer(self.begin(alternative='Please push the bowl in a different place.'))
 def test_new_answer_destination_still_cannot_be_invented(self):
  with self.assertRaises(TaskError):self.answer(self.begin(),instruction='Put the bowl on the plate.')
 def test_confirmation_requirement_is_not_lost(self):
  p=self.begin(primary='Please put the ball in a different place, but ask me before starting.',alternative='Please put the bowl in a different place, but ask me before starting.')
  self.assertEqual(self.answer(p)['status'],'needs_confirmation');self.assertIsNone(self.s.task_id)
if __name__=='__main__':unittest.main()
