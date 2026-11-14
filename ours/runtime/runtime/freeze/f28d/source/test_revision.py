import unittest,tempfile
from pathlib import Path
from scene_memory import SceneMemory
from test_scene_memory import point,facts
class ConsensusTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.m=SceneMemory(Path(self.t.name)/'log')
 def tearDown(self):self.t.cleanup()
 def feed(self,t,q=.3,delta=0,static=True,reusable=True,xy=(96,61)):
  f=facts(static,delta);f['bowl']['cache_reusable']=reusable
  self.m.evidence(t,f,'camera');p=point(xy=xy);p['det_confidence']=q;self.m.ingest([p],t)
 def test_consensus_survives_occlusion(self):
  for t in [0,3,6]:self.feed(t)
  self.m.evidence(9,facts(),'camera');self.m.ingest([],9)
  p,k=self.m.resolve('bowl','K3');self.assertEqual(k,'cached');self.assertEqual(p['frame'],0)
 def test_low_single_frame_not_cached(self):
  self.feed(0);self.m.evidence(3,facts(),'camera');self.m.ingest([],3);self.assertEqual(self.m.resolve('bowl','K3')[1],'missing')
 def test_gap_not_consensus(self):
  for t in [0,9,18]:self.feed(t)
  self.assertFalse(self.m.cache)
 def test_motion_cannot_accumulate_consensus(self):
  for t in [0,3,6]:self.feed(t,delta=t*.001)
  self.assertFalse(self.m.cache)
 def test_rebuild_after_moved_then_static(self):
  self.feed(0,.9)
  self.m.evidence(1,facts(delta=.02),'camera');self.assertFalse(self.m.cache)
  for t in [3,6,9]:self.feed(t,delta=.02,static=False)
  self.assertTrue(self.m.cache);self.assertEqual(self.m.cache[('bowl','K3')]['pose'][0],.02)
 def test_support_loss_invalidates_candidate(self):
  self.feed(0);self.feed(3);self.feed(6,reusable=False)
  self.assertFalse(self.m.cache)
 def test_below_point_floor_rejected(self):
  for t in [0,3,6]:self.feed(t,q=.09)
  self.assertFalse(self.m.cache)
 def test_camera_change_clears_consensus(self):
  self.feed(0);self.feed(3);self.m.evidence(4,facts(),'other');self.assertFalse(self.m.consensus)
if __name__=='__main__':unittest.main()
