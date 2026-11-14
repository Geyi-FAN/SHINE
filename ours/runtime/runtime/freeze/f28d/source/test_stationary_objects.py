import unittest,tempfile,math
from pathlib import Path
from scene_memory import SceneMemory,pose_deltas,stationary_window
from test_scene_memory import point,facts

class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=SceneMemory(Path(self.tmp.name)/'events');self.s.evidence(0,facts(),'camera')
 def tearDown(self):self.tmp.cleanup()
 def add(self):self.s.ingest([point()],0)
 def test_submillimetre_jitter_and_occlusion_reuses_point(self):
  self.add();self.s.evidence(10,facts(delta=.0008),'camera');self.s.ingest([],10);p,status=self.s.resolve('bowl','K3');self.assertEqual((p['frame'],status),(0,'cached'))
 def test_best_confidence_survives_weaker_detection(self):
  self.add();self.s.evidence(3,facts(),'camera');p=point(xy=(98,63));p['det_confidence']=.95;p['keypoint_confidence']=.95;self.s.ingest([p],3)
  self.s.evidence(6,facts(),'camera');self.s.ingest([point(xy=(97,62))],6);self.assertEqual(self.s.resolve('bowl','K3')[1],'fresh')
  self.s.evidence(9,facts(),'camera');self.s.ingest([],9);p,status=self.s.resolve('bowl','K3');self.assertEqual((p['frame'],p['yx224'],status),(3,[98,63],'cached'))
 def test_low_confidence_current_is_not_persistent(self):
  p=point();p['det_confidence']=.2;self.s.ingest([p],0);self.assertEqual(self.s.resolve('bowl','K3')[1],'fresh');self.s.evidence(3,facts(),'camera');self.s.ingest([],3);self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_cumulative_movement_cannot_refresh_origin(self):
  self.add()
  for step,delta,conf in [(1,.002,.7),(2,.004,.8)]:
   self.s.evidence(step,facts(delta=delta),'camera');p=point();p['det_confidence']=conf;self.s.ingest([p],step)
  self.s.evidence(3,facts(delta=.006),'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_quaternion_sign_flip_is_not_motion(self):
  self.add();f=facts();f['bowl']['pose'][3]=-1;self.s.evidence(3,f,'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'cached')
 def test_rotation_invalidates(self):
  self.add();f=facts();a=math.radians(6)/2;f['bowl']['pose'][3:]=[math.cos(a),0,0,math.sin(a)];self.s.evidence(3,f,'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_light_touch_does_not_invalidate_small_pose_change(self):
  self.add();f=facts(False,delta=.0008);f['bowl']['cache_reusable']=True;self.s.evidence(3,f,'camera');self.s.ingest([],3);self.assertEqual(self.s.resolve('bowl','K3')[1],'cached')
 def test_reusable_flag_cannot_override_large_motion(self):
  self.add();f=facts(False,delta=.006);f['bowl']['cache_reusable']=True;self.s.evidence(3,f,'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_grasp_or_support_loss_invalidates_even_if_static_flag_true(self):
  self.add();f=facts();f['bowl']['cache_reusable']=False;self.s.evidence(3,f,'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_no_future_or_wrong_slot(self):
  self.add();self.assertEqual(self.s.resolve('cheese','K3')[1],'missing');self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
  with self.assertRaises(ValueError):self.s.evidence(-1,facts(),'camera')
 def test_nan_confidence_rejected(self):
  p=point();p['det_confidence']=float('nan');self.s.ingest([p],0);self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_stationary_window(self):
  rows=[dict(object_position=[i*.0002,0,0],object_quaternion_wxyz=[1,0,0,0],support_contact=True,target_contact=False) for i in range(5)]
  self.assertTrue(stationary_window(rows,.002,2));rows[-1]['object_position']=[.01,0,0];self.assertFalse(stationary_window(rows,.002,2))
 def test_window_contact_and_insufficient_evidence(self):
  r=dict(object_position=[0,0,0],object_quaternion_wxyz=[1,0,0,0],support_contact=True,target_contact=False)
  self.assertFalse(stationary_window([r]*4,.002,2));self.assertFalse(stationary_window([dict(r,target_contact=True)]*5,.002,2));self.assertFalse(stationary_window([dict(r,support_contact=False)]*5,.002,2))
 def test_invalid_pose(self):
  self.assertEqual(pose_deltas([0],None),(float('inf'),float('inf')))

if __name__=='__main__':unittest.main()
