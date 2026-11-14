import unittest,tempfile
from pathlib import Path
from scene_memory import SceneMemory
from test_scene_memory import point
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.s=SceneMemory(Path(self.tmp.name)/'events');self.s.evidence(0,{},'camera')
 def tearDown(self):self.tmp.cleanup()
 def test_initial_stove_survives_missing_and_drift(self):
  self.s.seed_episode([point('stove_button','K1',(83,69))]);self.s.evidence(42,{},'camera');self.s.ingest([point('stove_button','K1',(73,67))],42)
  p,status=self.s.resolve('stove_button','K1');self.assertEqual(p['yx224'],[83,69]);self.assertEqual((p['frame'],status),(-1,'cached'))
 def test_high_conf_both_required(self):
  p=point('stove_button','K1');p['keypoint_confidence']=.49;self.s.seed_episode([p]);self.assertEqual(len(self.s.anchors),0)
  p['keypoint_confidence']=.9;p['det_confidence']=.49;self.s.seed_episode([p]);self.assertEqual(len(self.s.anchors),0)
 def test_late_visible_fixed_anchor(self):
  self.s.evidence(12,{},'camera');self.s.ingest([point('stove_placement','K3')],12);self.s.evidence(15,{},'camera');self.s.ingest([],15);self.assertEqual(self.s.resolve('stove_placement','K3')[0]['frame'],12)
 def test_camera_change(self):
  self.s.seed_episode([point('stove_button','K1')]);self.s.evidence(3,{},'new');self.assertEqual(self.s.resolve('stove_button','K1')[1],'missing')
 def test_episode_isolation(self):
  self.s.seed_episode([point('stove_button','K1')]);new=SceneMemory(Path(self.tmp.name)/'other');self.assertEqual(new.resolve('stove_button','K1')[1],'missing')
 def test_drawer_cannot_seed_from_episode(self):
  self.s.evidence(0,{'top_drawer_interior':dict(static=True,pose=[0])},'camera');self.s.seed_episode([point('top_drawer_interior','K3')]);self.assertEqual(len(self.s.anchors),0)
 def test_drawer_acquire_reuse_invalidate_reacquire(self):
  e='top_drawer_interior';self.s.evidence(10,{e:dict(static=True,pose=[.15])},'camera');self.s.ingest([point(e,'K3')],10);self.s.evidence(13,{e:dict(static=True,pose=[.15])},'camera');self.s.ingest([],13);self.assertEqual(self.s.resolve(e,'K3')[1],'cached')
  self.s.evidence(14,{e:dict(static=False,pose=[.14])},'camera');self.assertEqual(self.s.resolve(e,'K3')[1],'missing')
  self.s.evidence(25,{e:dict(static=True,pose=[.15])},'camera');self.s.ingest([point(e,'K3',(100,130))],25);self.assertEqual(self.s.resolve(e,'K3')[0]['frame'],25)
 def test_handle_not_seeded(self):
  self.s.seed_episode([point('top_handle','K1')]);self.assertEqual(len(self.s.anchors),0)
 def test_disabled(self):
  self.s.enabled=False;self.s.seed_episode([point('stove_button','K1')]);self.assertEqual(len(self.s.anchors),0)
if __name__=='__main__':unittest.main()
