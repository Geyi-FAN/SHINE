import unittest
from planner import validate
from test_hybrid import fixture
class Tests(unittest.TestCase):
 def blocked(self):
  i,o=fixture('return_bowl');o.update(status='need_observation',reference=None,current_subgoal_template=None,policy_prompt_template=None,request='Future handle is missing');return i,o
 def test_m1_unchanged(self):self.assertEqual(validate(*self.blocked(),m2=False),[])
 def test_future_does_not_block(self):self.assertTrue(any('M2:' in e for e in validate(*self.blocked(),m2=True)))
 def test_missing_current_still_blocks(self):
  i,o=self.blocked();i['reference_availability'][0]['available']=False;self.assertEqual(validate(i,o,m2=True),[])
 def test_unsatisfied_physical_prerequisite_not_overridden(self):
  i,o=fixture('cheese_bowl');o.update(status='need_observation',reference=None,current_subgoal_template=None,policy_prompt_template=None,request='Need physical observation');self.assertEqual(validate(i,o,m2=True),[])
 def test_clarification_not_overridden(self):
  i,o=self.blocked();o['status']='need_clarification';self.assertEqual(validate(i,o,m2=True),[])
if __name__=='__main__':unittest.main()
