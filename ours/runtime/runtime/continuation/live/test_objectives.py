import unittest
from continuation.live.objectives import compile_objective,UnsupportedObjective,OBJECTS
class Objectives(unittest.TestCase):
 def setUp(self):self.xyz={x:[0.,0.,.9]for x in OBJECTS.values()};self.q={'middle':0.,'top':0.}
 def make(self,t):return compile_objective(t,self.xyz,self.xyz,self.q)
 def test_normal_goal_from_public_instruction(self):
  self.assertEqual(self.make('put the bowl on the stove').target_task,1)
  self.assertEqual(self.make('put the cream cheese in the bowl').target_task,6)
 def test_cleanup_order_is_verified_not_generated(self):
  a=self.make('Return the bowl to its episode-start position and release it, then close the top drawer, then open the middle drawer of the cabinet.')
  self.assertEqual(a.target_task,0);self.assertEqual([(c['before'],c['after'])for c in a.clauses if c['kind']=='completion_order'],[('restore_0','close_0'),('close_0','target')])
 def test_return_only_no_invented_stove_goal(self):
  a=self.make('Return the bowl to its episode-start position and release it.')
  self.assertTrue(a.return_only);self.assertFalse(any(c['kind']=='completion_order'for c in a.clauses))
 def test_preserve_after_return_has_scope(self):
  a=self.make('Return the bowl to its episode-start position and release it, then put the cheese in the bowl. Keep the bowl at its returned position afterward.')
  self.assertEqual(next(c for c in a.clauses if c['kind']=='preserve_position')['activation_after'],'restore_0')
 def test_unknown_or_ambiguous_is_not_shortened(self):
  for t in ['put it there','put the cheese in the bowl. Keep the bowl there and move the wine bottle under the table','Return the bowl to its episode-start position, then move it onto the plate','Return the bowl to its episode-start position and release it, then move it onto the plate','put the bowl on the stove then put the wine bottle on the rack','put the bowl on the stove then close the middle drawer']:
   with self.subTest(t=t),self.assertRaises(UnsupportedObjective):self.make(t)
 def test_open_only_does_not_invent_bowl_placement(self):
  self.assertEqual(self.make('open the top drawer').open_only,'top')
  self.assertIsNone(self.make('open the top drawer and put the bowl inside').open_only)
 def test_drawer_scope_from_public_source_only(self):
  t='put the cheese in the bowl. Leave the drawer as it is.'
  with self.assertRaises(UnsupportedObjective):self.make(t)
  a=compile_objective(t,self.xyz,self.xyz,self.q,previous_instruction='open the middle drawer of the cabinet')
  self.assertEqual(next(c for c in a.clauses if c['kind']=='preserve_articulation_state')['joint'],'middle')
if __name__=='__main__':unittest.main()
