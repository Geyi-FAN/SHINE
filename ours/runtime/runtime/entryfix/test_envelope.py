import unittest
from types import SimpleNamespace as NS
from entryfix.envelope import install
class Envelope(unittest.TestCase):
 def test_source_task_return_regression_exactly_one_period(self):
  p=NS(is_smol=lambda:True);p.policy_template=lambda t,o:'Task: '+t+'.\nCurrent subgoal: '+o['template']+'.\nCoordinates: MAIN, 256x256, <y,x> pixels.\n';m=NS(policy_template=p.policy_template);install(p,m)
  task='Return the cream cheese to its position at the beginning of the source task, release it, then put the wine bottle on top of the cabinet.';op={'template':'return the cream cheese to its episode-start position at {episode_start.cheese.K2}, release it stably'};actual=m.policy_template(task,op)
  self.assertNotIn('..',actual);self.assertIn(task+'\n',actual);self.assertEqual(op['template'],'return the cream cheese to its episode-start position at {episode_start.cheese.K2}, release it stably')
 def test_internal_task_clauses_are_preserved(self):
  p=NS(is_smol=lambda:True);p.policy_template=lambda t,o:t+'.\n'+o['template']+'.';m=NS(policy_template=p.policy_template);install(p,m);self.assertEqual(m.policy_template('Put the bowl on the plate. Keep the bottle where it is.',{'template':'place it.'}),'Put the bowl on the plate. Keep the bottle where it is.\nplace it.')
 def test_other_executor_format_is_unchanged(self):
  old=lambda t,o:t+'; '+o['template'];p=NS(is_smol=lambda:False,policy_template=old);m=NS(policy_template=old);install(p,m);self.assertEqual(m.policy_template('Task.',{'template':'Subgoal.'}),'Task.; Subgoal.')
if __name__=='__main__':unittest.main()
