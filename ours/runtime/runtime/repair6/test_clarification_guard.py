import sys,tempfile,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'freeze/voice/robot_gateway'))
from core import RobotState,TaskError
from grounding import ENTITIES,inventory_from_names
from repair6.clarification_guard import install
install(RobotState)
class IncompleteDestination(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=RobotState(self.tmp.name);self.s.ready=True;self.s.mode='idle';self.i=0;self.s.scene_inventory=inventory_from_names(v[0]for v in ENTITIES.values())
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def cmd(self,name,**args):
  self.i+=1;return self.s.command(name,dict(episode_id=self.s.episode,expected_task_version=self.s.version,**args),str(self.i))
 def begin(self,text='Please move it.'):
  return self.cmd('robot_begin_clarification',user_utterance=text,voice_input_id='u1',question='Which object do you want to move?',missing_slot='object')['pending_clarification']
 def test_incomplete_resolution_then_model_followup_preserves_answer(self):
  p=self.begin()
  with self.assertRaises(TaskError)as error:self.cmd('robot_answer_clarification',clarification_id=p['clarification_id'],user_utterance='The cream cheese.',voice_input_id='u2',instruction='Move the cream cheese.')
  self.assertIn('clarification_missing_destination',str(error.exception));self.assertIsNone(self.s.task_id)
  r=self.cmd('robot_answer_clarification',clarification_id=p['clarification_id'],user_utterance='The cream cheese.',voice_input_id='u2',question='Where should I put it?')
  self.assertEqual(r['status'],'needs_clarification');self.assertEqual(len(self.s.pending_clarification['source_utterances']),2)
  r=self.cmd('robot_answer_clarification',clarification_id=p['clarification_id'],user_utterance='Into the bowl.',voice_input_id='u3',instruction='put the cream cheese in the bowl')
  self.assertEqual(r['status'],'accepted');self.assertEqual(self.s.instruction,'put the cream cheese in the bowl')
 def test_known_destination_does_not_require_repeated_question(self):
  p=self.begin('Please move it into the bowl.')
  r=self.cmd('robot_answer_clarification',clarification_id=p['clarification_id'],user_utterance='The cream cheese.',voice_input_id='u2',instruction='put the cream cheese in the bowl')
  self.assertEqual(r['status'],'accepted')
if __name__=='__main__':unittest.main()
