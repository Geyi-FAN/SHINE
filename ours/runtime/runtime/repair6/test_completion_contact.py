import unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'reference'))
from repair6.completion import CompletionGate
class ContainerGate(unittest.TestCase):
 def run_gate(self,contact):
  gate=CompletionGate(('e','t',1),{'restore':{'position_steps':1,'support_steps':1,'support_min_true':1,'release_steps':1,'stable_steps':1,'stable_diameter_m':.005,'withdraw_steps':1,'withdraw_distance_m':.08}},hold_ticks=1)
  frame=dict(object_position=[0,0,0],eef_position=[0,0,.1],support_contact=False,target_contact=False,object_object_contacts=([dict(objects=['akita_black_bowl_1','cream_cheese_1'],penetration=.0001)]if contact else[]))
  for _ in range(7):accepted=gate.observe(dict(adjusted_goal=True,source=frame,target=frame),('e','t',1),6,full_contract=True)
  return accepted
 def test_no_support_does_not_complete(self):self.assertFalse(self.run_gate(False))
 def test_actual_container_contact_can_complete(self):self.assertTrue(self.run_gate(True))
if __name__=='__main__':unittest.main()
