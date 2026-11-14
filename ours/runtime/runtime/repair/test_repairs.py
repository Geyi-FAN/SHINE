import copy,sys,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B/'freeze/voice/robot_gateway'),str(B/'freeze/authority_src'),str(B)]
from clarification import bound_object_answer
from repair.completion import CompletionGate
from benchmark_metrics import load_rules
class ClarificationTests(unittest.TestCase):
 def test_literal_open_answer(self):
  e=dict(question='Which object do you want to move?',missing_slot='object',original_utterance='Please move it.')
  self.assertEqual(bound_object_answer(e,'The cream cheese.','The cream cheese.'),'The cream cheese.')
  self.assertEqual(bound_object_answer(e,'The cream cheese.','cheese'),'The cream cheese.')
  for text,answer in [('The ball.','The bowl.'),('Not the bowl.','The bowl.'),('The cheese.','The bowl.'),('The bowl or cheese.','The bowl.'),('The bowl.','Put the bowl on the stove.')]:
   with self.subTest(text=text,answer=answer),self.assertRaises(ValueError):bound_object_answer(e,text,answer)
 def test_offered_choice_still_bound(self):
  e=dict(question='Which object?',missing_slot='object',original_utterance='I mean the bowl or the wine bottle; move it.')
  self.assertEqual(bound_object_answer(e,'The ball.','The bowl.'),'The bowl.')
  with self.assertRaises(ValueError):bound_object_answer(e,'The cheese.','The cheese.')
class CompletionTests(unittest.TestCase):
 def row(self,contact=False,support=True,goal=True,x=0):
  f=dict(object_position=[x,0,0],eef_position=[0,0,.1],target_contact=contact,support_contact=support)
  return dict(adjusted_goal=goal,source=f,target=f)
 def test_target_touch_does_not_complete(self):
  g=CompletionGate(('e','t',1),load_rules())
  for _ in range(100):self.assertFalse(g.observe(self.row(contact=True),g.subject,1,full_contract=True))
  self.assertFalse(g.holding)
 def test_release_stability_then_real_hold(self):
  g=CompletionGate(('e','t',1),load_rules());results=[g.observe(self.row(),g.subject,1,full_contract=True) for _ in range(50)]
  self.assertFalse(any(results[:40]));self.assertTrue(results[-1])
 def test_stale_identity_and_drift(self):
  g=CompletionGate(('e','t',1),load_rules())
  for _ in range(10):g.observe(self.row(),g.subject,1,full_contract=True)
  self.assertFalse(g.observe(self.row(),('e','t',2),1,full_contract=True))
  self.assertFalse(g.observe(self.row(goal=False),g.subject,1,full_contract=True));self.assertEqual(g.hold_seen,0)
 def test_containment_no_bottom_support_proxy(self):
  g=CompletionGate(('e','t',1),load_rules())
  for _ in range(50):result=g.observe(self.row(support=False),g.subject,6,full_contract=True)
  self.assertTrue(result)
 def test_failed_contract_never_complete(self):
  g=CompletionGate(('e','t',1),load_rules())
  for _ in range(100):self.assertFalse(g.observe(self.row(),g.subject,1,full_contract=False))
class WordingTests(unittest.TestCase):
 def test_current_support_not_invented(self):
  from repair.wording_guard import extra_errors
  self.assertTrue(extra_errors('put the cheese in the bowl','put the cheese in the bowl currently on the table'))
  self.assertFalse(extra_errors('put the cheese in the bowl on the stove','put the cheese in the bowl currently on the stove'))
  self.assertFalse(extra_errors('put the cheese in the bowl','put the cheese in the bowl'))
  self.assertTrue(extra_errors('put the cheese in the bowl on the stove','put the cheese in the bowl currently on the table'))
  self.assertTrue(extra_errors('put the cheese in the bowl','put the cheese in the bowl on the table'))
  self.assertFalse(extra_errors('put the bowl on the stove','place the bowl on the stove'))
class TelemetryTests(unittest.TestCase):
 def test_predecessor_completed_not_successor_completed(self):
  from repair.telemetry import inspect
  sample=dict(step=229,policy_actions=91,task_started=10,simulation_time=12,state_hash='hash',mode='completed',task_id='predecessor',task_count=1,fixture_hold=False,source_phase_reached=True,hold_remaining=0,route='native',kernel_error=None)
  snapshot=inspect(sample,now=20)
  self.assertEqual((snapshot['task_id'],snapshot['task_count'],snapshot['mode']),('predecessor',1,'completed'))
  self.assertFalse(snapshot['mode']=='completed'and snapshot['task_count']==2)
  sample=dict(sample,task_id='successor',task_count=2,mode='running',task_started=20)
  snapshot=inspect(sample,now=21);self.assertEqual(snapshot['mode'],'running');self.assertEqual(snapshot['task_elapsed_s'],1)
class CausalTargetTests(unittest.TestCase):
 def test_async_effect_after_action(self):
  from repair.reference.causal_target import first_authorized_hit
  rows=[dict(task_id='t',policy_action=True,mode='running',physics_tick=True,phase='source_policy'),dict(task_id='t',policy_action=False,mode='running',physics_tick=True,phase='async_wait_hold')]
  self.assertEqual(first_authorized_hit(rows,[False,True],{'t'}),1)
  self.assertIsNone(first_authorized_hit(rows,[False,True],{'other'}))
  self.assertIsNone(first_authorized_hit(rows[1:],[True],{'t'}))
  rows[1].update(mode='completed',phase='evaluator_terminal_hold')
  self.assertIsNone(first_authorized_hit(rows,[False,True],{'t'}))
if __name__=='__main__':unittest.main()
