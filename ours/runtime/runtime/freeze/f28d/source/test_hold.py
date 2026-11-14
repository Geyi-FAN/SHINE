import unittest
from types import SimpleNamespace
import numpy as np
from hold_gate import PoseHold,CandidateGate
from test_observed_completion import point,obs,history,stage,ObservedCompletion
CTRL=SimpleNamespace(use_delta=True,output_max=np.array([.05]*3+[.5]*3),output_min=np.array([-.05]*3+[-.5]*3))
def robot(x=0):return {'robot0_eef_pos':[x,0,1],'robot0_eef_quat':[0,0,0,1]}
class Tests(unittest.TestCase):
 def test_hold_zero_gripper(self):
  h=PoseHold(robot(),CTRL);a=h.action(robot(.002));self.assertAlmostEqual(a[0],-.04);self.assertEqual(a[6],0)
 def test_pose_rotation(self):
  from scipy.spatial.transform import Rotation
  h=PoseHold(robot(),CTRL);o=robot();o['robot0_eef_quat']=Rotation.from_rotvec([0,0,.1]).as_quat();a=h.action(o);self.assertAlmostEqual(a[5],-.2)
 def test_zero_preserves_panda_target(self):
  from robosuite.models.grippers.panda_gripper import PandaGripper
  g=PandaGripper();g.format_action(np.array([1.]));a=g.current_action.copy();g.format_action(np.array([0.]));np.testing.assert_array_equal(g.current_action,a)
 def test_require_nine_steps(self):
  m=ObservedCompletion(history());ps=[point('bowl','K1',[100,100]),point('bowl','K2',[100,100])]
  for t in [0,3,6,9]:obs(m,t,ps)
  gate=CandidateGate({},stage(),9,robot(),CTRL)
  self.assertEqual(gate.check(m,9,robot()),'observe')
  for t in [12,15]:obs(m,t,ps);self.assertEqual(gate.check(m,t,robot()),'observe')
  obs(m,18,ps);self.assertEqual(gate.check(m,18,robot()),'accept')
 def test_missing_never_confirm(self):
  m=ObservedCompletion(history());obs(m,0);gate=CandidateGate({},stage(),0,robot(),CTRL)
  for t in [3,6,9,12,15]:obs(m,t);self.assertEqual(gate.check(m,t,robot()),'observe')
  obs(m,18);self.assertEqual(gate.check(m,18,robot()),'resume')
 def test_no_open_on_held(self):
  h=PoseHold(robot(),CTRL);self.assertEqual(h.action(robot())[6],0.)
if __name__=='__main__':unittest.main()
