import sys,unittest
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B/'freeze/authority_src'))
from benchmark_metrics import load_rules
from continuation.terminal.completion_r4 import CompletionGate
class TerminalRegression(unittest.TestCase):
 def make(self,contact=False,goal=True,clear=None,x=0):
  f=dict(object_position=[x,0,.9],eef_position=[0,0,1.],target_contact=contact,support_contact=False)
  row=dict(adjusted_goal=goal,source=f,target=f)
  if clear is not None:row.update(requires_disengage=True,metric_evidence={'hand_clear_of_cabinet':clear})
  return row
 def test_cheese_still_touched_cannot_complete(self):
  g=CompletionGate(('e','t',1),load_rules())
  for _ in range(100):self.assertFalse(g.observe(self.make(contact=True),g.subject,6,full_contract=True))
 def test_cheese_unstable_cannot_complete(self):
  g=CompletionGate(('e','t',1),load_rules())
  for i in range(100):self.assertFalse(g.observe(self.make(x=.02*(i%2)),g.subject,6,full_contract=True))
 def test_close_clear_does_not_use_cheese_variables(self):
  g=CompletionGate(('e','t',1),load_rules())
  for _ in range(45):result=g.observe(self.make(clear=True),g.subject,0,full_contract=True)
  self.assertTrue(result)
 def test_clear_and_release_are_both_required(self):
  g=CompletionGate(('e','t',1),load_rules())
  for _ in range(50):self.assertFalse(g.observe(self.make(contact=True,clear=True),g.subject,6,full_contract=True))
  for _ in range(50):self.assertFalse(g.observe(self.make(contact=False,clear=False),g.subject,6,full_contract=True))
  for _ in range(50):result=g.observe(self.make(clear=True),g.subject,6,full_contract=True)
  self.assertTrue(result)
if __name__=='__main__':unittest.main()
