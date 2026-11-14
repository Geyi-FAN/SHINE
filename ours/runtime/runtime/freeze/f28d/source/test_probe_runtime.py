import unittest
from probe_runtime import prerequisite_order

def row(step,ready=False,target=False):return dict(step=step,metric_evidence={'probe_prerequisite':{'ready':ready}},goal_frame={'goal':target},adjusted_goal=target)
class Tests(unittest.TestCase):
 def test_required_order(self):self.assertTrue(prerequisite_order([row(1,True),row(2,target=True)])['passed'])
 def test_target_too_early(self):self.assertFalse(prerequisite_order([row(1,target=True),row(2,True)])['passed'])
 def test_same_step_not_strict_order(self):self.assertFalse(prerequisite_order([row(1,True,True)])['passed'])
 def test_prerequisite_never_achieved(self):self.assertFalse(prerequisite_order([row(1,target=True)])['passed'])
 def test_goal_never_achieved(self):self.assertFalse(prerequisite_order([row(1,True)])['passed'])
 def test_no_fabricated_future(self):self.assertFalse(prerequisite_order([])['passed'])
if __name__=='__main__':unittest.main()
