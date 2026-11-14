import sys,unittest
from pathlib import Path
from types import SimpleNamespace
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'freeze/voice/robot_gateway')]
from control_semantics import control_intent
from interaction import classify_utterance,allowed_voice_action
from continuation.live.objectives import compile_objective,UnsupportedObjective
from entryfix.literal import literal_task
XYZ={k:[0,0,1]for k in('akita_black_bowl_1','wine_bottle_1','cream_cheese_1','plate_1')}
class Entry(unittest.TestCase):
 def test_punctuation_does_not_change_task_admission(self):
  for p in('.',',',';',':'):
   s=f'Stop{p} put the bowl on the stove. Keep the top drawer at its instruction switch opening until this instruction is complete.'
   self.assertEqual(classify_utterance(s),'cloud_decision');self.assertTrue(allowed_voice_action(classify_utterance(s),'robot_revise_task'))
 def test_real_deferred_negation_and_question_remain_blocked(self):
  for s in('Stop after this task is finished.','Stop when the bowl is released.',"Do not stop, put the bowl on the stove.",'What if I say stop, put it on the stove?'):
   self.assertFalse(allowed_voice_action(classify_utterance(s),'robot_revise_task'))
 def test_current_stove_state_is_not_forced_on(self):
  for word in('keeping','keep','leaving','maintaining','preserving'):
   o=compile_objective('put the cream cheese in the bowl, '+word+' the stove in its current state',XYZ,XYZ,{},current_binary_state={'turn_on_stove':False})
   self.assertEqual(o.target_task,6);self.assertIs(next(c['reference_value']for c in o.clauses if c['kind']=='preserve_predicate_state'),False)
 def test_spoken_on_or_off_is_the_same_preserved_binary_state(self):
  for scope in('instruction switch on or off','instruction-switch on/off','instruction switch on-off','instruction-switch on off','current on or off','same on/off'):
   o=compile_objective('Put the cream cheese in the bowl. Keep the stove in its '+scope+' state until this instruction is complete.',XYZ,XYZ,{},current_binary_state={'turn_on_stove':False})
   self.assertIs(next(c['reference_value']for c in o.clauses if c['kind']=='preserve_predicate_state'),False)
 def test_current_drawer_opening_remains_zero(self):
  o=compile_objective('put the bowl on the stove. Keep the top drawer at its current opening',XYZ,XYZ,{'top':0})
  self.assertEqual(o.target_task,1);self.assertEqual(next(c['reference_q']for c in o.clauses if c['kind']=='preserve_articulation_state'),0)
 def test_plain_same_object_position_aliases_share_current_reference(self):
  for scope in('at its position until this instruction is complete','at its current position','in the same position','in place','where it is','unchanged'):
   o=compile_objective('put the bowl on the plate. Keep the wine bottle '+scope,XYZ,XYZ,{})
   self.assertEqual(next(c['reference_position']for c in o.clauses if c['kind']=='preserve_position'),XYZ['wine_bottle_1'])
 def test_unsupported_physical_scope_is_not_silently_discarded(self):
  for s in('put the cheese in the bowl, keeping the stove very hot','put the bowl on the stove, keep the top drawer open'):
   with self.assertRaises(UnsupportedObjective):compile_objective(s,XYZ,XYZ,{'top':0},current_binary_state={'turn_on_stove':False})
 def test_literal_wording_reuse_requires_actual_authorization_and_no_side_contract(self):
  s=SimpleNamespace(instruction='Put the bowl on the stove.',task_record={});c={'clauses':[{'source':'case.instruction.live_selected_public_task'}]}
  self.assertTrue(literal_task(s,s.instruction,c));self.assertFalse(literal_task(s,'Put the bowl on the plate.',c));s.task_record={'persistent_constraints':['keep bowl']};self.assertFalse(literal_task(s,s.instruction,c))
 def test_checked_memory_ids_are_retained_without_an_extra_wording_call(self):
  raw='Put the bowl on the plate. Keep the bottle where it is.';ids=['actual-record'];s=SimpleNamespace(instruction=raw,task_record={'complete_instruction':raw,'reference_memory_ids':ids,'candidate_contract':{'instruction':raw,'reference_memory_ids':ids,'unresolved':[],'semantic_check':{'decision':'checked'}}});c={'clauses':[{'source':'case.instruction.live_selected_public_task'}]}
  self.assertTrue(literal_task(s,raw,c));self.assertEqual(s.task_record['reference_memory_ids'],ids);s.task_record['candidate_contract']['semantic_check']['decision']='uncertain';self.assertFalse(literal_task(s,raw,c))
if __name__=='__main__':unittest.main()
