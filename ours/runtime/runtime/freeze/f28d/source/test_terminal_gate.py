import unittest
from observed_completion import ObservedCompletion
from terminal_gate import TerminalGate

def stage(op='cheese_bowl'):
 return dict(operation=op,object='cheese',kind='target')
def sensor(mon,f,open=True,visible=True,at_target=True):
 pts=[]
 if visible:
  for entity,k,p in [('cheese','K1',[100.,100.]),('cheese','K2',[100.,100.]),('bowl','K3',[100.,100.] if at_target else [170.,170.])]:
   pts.append(dict(entity=entity,keypoint=k,yx224=p,source='yolo_image_only',frame=f,det_confidence=.9,keypoint_confidence=.9))
 return mon.observe(f,[0.,0.,1.],[.04,.04] if open else [.02,.02],[50.,50.],pts)
def ready():
 m=ObservedCompletion()
 for f in [0,3,6,9]:sensor(m,f,at_target=False)
 return m
class Tests(unittest.TestCase):
 def check(self,m,gate=None,plan=None,success=True):
  g=gate or TerminalGate(6,'put the cream cheese in the bowl');p=plan or [stage()];g.register_plan(p)
  return g.check(m,{'remaining_plan':p},success,m.last,6)
 def test_native_authoritative_over_2d_relation(self):
  m=ready();self.assertFalse(m.snapshot['native_goal_relations']['cheese_bowl']);self.assertTrue(self.check(m)['passed'])
 def test_s1_relation_does_not_replace_native_false(self):
  m=ObservedCompletion()
  for f in [0,3,6,9]:sensor(m,f)
  self.assertTrue(m.snapshot['native_goal_relations']['cheese_bowl']);self.assertFalse(self.check(m,success=False)['passed'])
 def test_native_true_cannot_skip_closed_gripper(self):
  m=ObservedCompletion()
  for f in [0,3,6,9]:sensor(m,f,open=False)
  self.assertFalse(self.check(m)['passed'])
 def test_missing_current_object_does_not_use_cache(self):
  m=ready();sensor(m,12,visible=False);self.assertFalse(self.check(m)['passed'])
 def test_prefix_cannot_be_skipped(self):
  m=ready();g=TerminalGate(6,'return the bowl then put the cream cheese in the bowl');g.register_plan([dict(operation='return_bowl_clear'),stage()]);self.assertFalse(self.check(m,g)['passed'])
  m.events.append(dict(operation='return_bowl_clear',source='s1_rgb_proprio_v1',outcome='completed',confirmed_step=3));self.assertTrue(self.check(m,g)['passed'])
 def test_wrong_target_identity_rejected(self):
  m=ready();g=TerminalGate(6,'put cheese in bowl');g.register_plan([stage()])
  with self.assertRaises(ValueError):g.check(m,{'remaining_plan':[stage()]},True,9,4)
 def test_stale_or_future_sensor_rejected(self):
  m=ready();g=TerminalGate(6,'put cheese in bowl');g.register_plan([stage()])
  with self.assertRaises(ValueError):g.check(m,{'remaining_plan':[stage()]},True,12,6)
 def test_not_last_stage_cannot_terminate(self):
  m=ready();self.assertFalse(self.check(m,plan=[dict(operation='grasp_cheese'),stage()])['passed'])
if __name__=='__main__':unittest.main()
