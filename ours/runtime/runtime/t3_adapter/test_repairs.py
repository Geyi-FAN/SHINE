import importlib
import sys
import unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(B),str(B/'freeze/voice/robot_gateway')]
import core,grounding,interaction,semantics
from t3_adapter.runtime_repairs import install,historical_location,canonical_objective_text
from continuation.live.objectives import UnsupportedObjective
install(core)
from continuation.live.objectives import compile_objective
XYZ={k:[0,0,1]for k in ['akita_black_bowl_1','cream_cheese_1','wine_bottle_1','plate_1']}
INVENTORY=grounding.inventory_from_names(XYZ.keys()|{'wooden_cabinet_1','flat_stove_1','wine_rack_1','main_table'})
class Repairs(unittest.TestCase):
 def test_historical_location_is_not_an_object(self):
  raw='停一下。先把 cheese 放回场景最开始时的位置，并松开夹爪，再把酒瓶放到柜顶。'
  self.assertIn(('target','原位'),grounding.slots(raw))
  grounding.validate_grounding(raw,'Return the cream cheese to its episode-start position and release it, then put the wine bottle on top of the cabinet.',INVENTORY)
 def test_unsupported_source_and_target_still_rejected(self):
  for raw in ['把苹果放回场景最开始时的位置。','把cheese放到紫色盒子里。','把cheese放回神秘位置。']:
   with self.assertRaises(ValueError):grounding.validate_grounding(raw,'Put the cream cheese in the bowl.',INVENTORY)
 def test_ambiguity_still_requires_memory(self):
  with self.assertRaises(ValueError):grounding.validate_grounding('把它放到盘子上。','Put the bowl on the plate.',INVENTORY)
 def test_same_utterance_explicit_open_container_binds_inside(self):
  raw='停一下，打开顶层抽屉，把碗放进去，在完成这个任务前，让plate一直留在收到指令时的位置。'
  self.assertIn(('target','顶层抽屉'),grounding.slots(raw))
  grounding.validate_grounding(raw,'Open the top drawer and put the bowl inside. Keep the plate at its current position.',INVENTORY)
 def test_inside_without_unique_open_container_still_rejected(self):
  for raw in ['把碗放进去。','打开顶层抽屉和打开中间抽屉，把碗放进去。']:
   with self.assertRaises(ValueError):grounding.validate_grounding(raw,'Open the top drawer and put the bowl inside.',INVENTORY)
 def test_unique_inside_is_checked_by_both_semantic_and_object_guards(self):
  raw='停一下，打开顶层抽屉，把碗放进去，在完成这个新任务前，让plate一直留在收到这条新指令时的位置。'
  task='Open the top drawer and put the bowl inside. Keep the plate at its current position until this new task is completed.'
  r=core.inspect_semantics(raw,task,INVENTORY)
  self.assertEqual(r['decision'],'checked');self.assertEqual(r['user_utterance'],raw)
  with self.assertRaises(ValueError):core.inspect_semantics(raw,task.replace('top drawer','middle drawer'),INVENTORY)
 def test_unique_container_does_not_resolve_other_ambiguity(self):
  for raw in ['打开顶层抽屉，把它放进去。','打开顶层抽屉，把碗放进去，再把酒瓶放到那个地方。']:
   with self.assertRaises(ValueError):core.inspect_semantics(raw,'Open the top drawer and put the bowl inside, then put the wine bottle on the cabinet.',INVENTORY)
 def test_unique_container_preserves_explicit_confirmation_request(self):
  raw='请先确认再执行：打开顶层抽屉，把碗放进去。'
  r=core.inspect_semantics(raw,'Open the top drawer and put the bowl inside.',INVENTORY)
  self.assertEqual(r['decision'],'needs_confirmation')
  self.assertIn('用户要求先确认再执行',r['uncertainties'])
 def test_drawer_opening_imperative_is_not_question(self):
  raw='停一下，把碗放到 stove 上。在这个新任务完成前，让顶层抽屉一直保持在收到这条新指令时的开度。'
  self.assertEqual(core.classify_utterance(raw),'cloud_decision')
 def test_real_questions_and_negations_remain_blocked(self):
  for raw in ['顶层抽屉的开度是多少？','把碗放到炉灶后，抽屉的开度多大？','不要停，把碗放到炉灶上并保持抽屉开度。','如果我说停一下，把碗放炉灶，会怎样？']:
   self.assertFalse(interaction.allowed_voice_action(core.classify_utterance(raw),'robot_revise_task'),raw)
 def test_explicit_close_postfix_does_not_add_confirmation(self):
  raw='停一下，先把中间抽屉关上，再把酒瓶放到 cabinet 的顶部。'
  r=core.inspect_semantics(raw,'Close the middle drawer first, then put the wine bottle on top of the cabinet.',INVENTORY)
  self.assertEqual(r['decision'],'checked');self.assertEqual(r['user_utterance'],raw)
 def test_reversed_drawer_order_still_rejected(self):
  with self.assertRaises(ValueError):core.inspect_semantics('先把中间抽屉关上，再把酒瓶放到柜顶。','Put the wine bottle on top of the cabinet, then close the middle drawer.',INVENTORY)
 def test_switch_state_preserves_bound_false_and_true(self):
  for state in [False,True]:
   for text in ['keep the stove at its current switch state','keep the stove in its current switch state']:
    o=compile_objective('Put the cream cheese in the bowl, and '+text+' until this task is completed.',XYZ,XYZ,{},current_binary_state={'turn_on_stove':state})
    self.assertIs(next(c['reference_value']for c in o.clauses if c['kind']=='preserve_predicate_state'),state)
 def test_unsupported_stove_temperature_not_silently_normalized(self):
  with self.assertRaises(UnsupportedObjective):compile_objective('put the cheese in the bowl. keep the stove at its current temperature.',XYZ,XYZ,{},current_binary_state={'turn_on_stove':False})
if __name__=='__main__':unittest.main()
