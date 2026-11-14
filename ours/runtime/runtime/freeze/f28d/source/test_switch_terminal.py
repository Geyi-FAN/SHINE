import sys,unittest
from unittest.mock import patch
sys.path.insert(0,'/mnt/disk_4/geyi/smolvla_eval')
from switch_terminal import SwitchTerminal
class Tests(unittest.TestCase):
 def setUp(self):
  self.g=SwitchTerminal({'target_task':6},{'clauses':[{'id':'keep','kind':'preserve_position'}]}, {},{})
  self.d={'remaining_plan':[{'operation':'cheese_bowl'}]};self.ms=[{'step':1,'goal_frame':{'goal':True},'adjusted_goal':True}]
 def score(self,last=True,success=True):return dict(components={'keep':{'last_state':last}},instruction_adjusted={'success':success})
 def test_success_without_s1_or_pixels(self):
  with patch('switch_terminal.evaluate_episode',return_value=self.score()):self.assertTrue(self.g.check(self.ms,self.d)['passed'])
 def test_ever_success_does_not_override_current_violation(self):
  with patch('switch_terminal.evaluate_episode',return_value=self.score(False)):self.assertFalse(self.g.check(self.ms,self.d)['passed'])
 def test_missing_evidence_not_pass(self):
  with patch('switch_terminal.evaluate_episode',return_value=self.score(None)):self.assertFalse(self.g.check(self.ms,self.d)['passed'])
 def test_lost_target_not_pass(self):
  self.ms[0]['adjusted_goal']=False
  with patch('switch_terminal.evaluate_episode') as f:
   self.assertFalse(self.g.check(self.ms,self.d)['passed']);f.assert_not_called()
 def test_order_failure_not_pass(self):
  with patch('switch_terminal.evaluate_episode',return_value=self.score(success=False)):self.assertFalse(self.g.check(self.ms,self.d)['passed'])
 def test_intermediate_stage_never_switches_using_oracle(self):
  with patch('switch_terminal.evaluate_episode') as f:
   self.assertFalse(self.g.check(self.ms,{'remaining_plan':[{'operation':'grasp_cheese'},{'operation':'cheese_bowl'}]})['passed']);f.assert_not_called()
if __name__=='__main__':unittest.main()
