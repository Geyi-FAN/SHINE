import unittest
from repair6.public_execution import bind
class PublicTaskIdentity(unittest.TestCase):
 def test_previous_completion_never_describes_successor(self):
  s=dict(task_id='new',task_intent_revision=2,agent_execution=dict(task_id='old',semantic_revision=1,phase='completed',completion_current_verified=True))
  r=bind(s);self.assertEqual(r['agent_execution']['phase'],'planning');self.assertFalse(r['agent_execution']['completion_current_verified']);self.assertEqual(s['agent_execution']['phase'],'completed')
 def test_current_completion_preserved(self):
  e=dict(task_id='new',semantic_revision=2,phase='completed',completion_current_verified=True)
  self.assertEqual(bind(dict(task_id='new',task_intent_revision=2,agent_execution=e))['agent_execution'],e)
 def test_idle_has_no_old_subgoal(self):self.assertIsNone(bind(dict(task_id=None,agent_execution=dict(phase='completed')))['agent_execution'])
if __name__=='__main__':unittest.main()
