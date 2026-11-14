import unittest,tempfile,copy
from pathlib import Path
from scene_memory import SceneMemory
from points import Points
from test_hybrid import fixture

def point(e='bowl',k='K3',xy=(96.,61.)):
    return dict(entity=e,keypoint=k,yx224=list(xy),det_confidence=.6,keypoint_confidence=.9,source='yolo_image_only')
def facts(static=True,delta=0):return {'bowl':dict(static=static,pose=[delta,0,0,1,0,0,0])}
class Tests(unittest.TestCase):
 def setUp(self):
    self.tmp=tempfile.TemporaryDirectory();self.s=SceneMemory(Path(self.tmp.name)/'log.jsonl')
 def tearDown(self):self.tmp.cleanup()
 def add(self):self.s.evidence(83,facts(),'camera');self.s.ingest([point()],83)
 def test_cached_missing(self):
    self.add();self.s.evidence(86,facts(),'camera');self.s.ingest([],86);p,status=self.s.resolve('bowl','K3');self.assertEqual((p['frame'],status),(83,'cached'))
 def test_movement_invalidates(self):
    self.add();self.s.evidence(84,facts(delta=.006),'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_contact_invalidates(self):
    self.add();self.s.evidence(84,facts(False),'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_camera_invalidates(self):
    self.add();self.s.evidence(84,facts(),'newcamera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_missing_evidence_invalidates(self):
    self.add();self.s.evidence(84,{},'camera');self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_jump_rejected_then_confirmed(self):
    self.add();self.s.evidence(86,facts(),'camera');self.s.ingest([point(xy=(130,100))],86);self.assertEqual(self.s.resolve('bowl','K3')[1],'cached');self.s.evidence(89,facts(),'camera');self.s.ingest([point(xy=(131,100))],89);self.assertEqual(self.s.resolve('bowl','K3')[1],'fresh')
 def test_handle_not_cached(self):
    self.s.evidence(0,{},'camera');self.s.ingest([point('middle_handle','K1')],0);self.s.evidence(3,{},'camera');self.s.ingest([],3);self.assertEqual(self.s.resolve('middle_handle','K1')[1],'missing')
 def test_no_slot_fallback(self):
    self.add();self.assertEqual(self.s.resolve('bowl','K1')[1],'missing')
 def test_disabled(self):
    self.s.enabled=False;self.add();self.s.evidence(86,facts(),'camera');self.s.ingest([],86);self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_bad_conf_bounds(self):
    self.s.evidence(0,facts(),'camera');p=point();p['det_confidence']=.09;self.s.ingest([p,point(xy=(500,1))],0);self.assertEqual(self.s.resolve('bowl','K3')[1],'missing')
 def test_bind_prompt_unchanged_and_cached_marker(self):
    self.add();self.s.evidence(86,facts(),'camera');self.s.ingest([],86)
    p=object.__new__(Points);p.scene=self.s;p.frame=86;p.camera_id='camera'
    d=dict(reference=dict(time_source='current',entity='bowl',keypoint='K3'),policy_prompt_template='place cheese at {current.bowl.K3}',remaining_plan=[dict(kind='target')]);text,marker=p.bind(d,86)
    self.assertEqual(text,'place cheese at <110,70>') # MAIN224 memory -> MAIN256 executor exactly once.
    self.assertEqual(marker['resolution'],'cached');self.assertEqual(marker['source_frame'],83);self.assertFalse(marker['valid'])
 def test_historical_not_overwritten(self):
    p=object.__new__(Points);p.scene=self.s;p.camera_id='camera';p.history_camera={'episode_start':'camera'};p.memory={('episode_start','bowl','K2'):dict(frame=-1,yx224=[10,20])};self.add();self.assertEqual(p.resolve('episode_start','bowl','K2')[0]['yx224'],[10,20]);p.camera_id='changed';self.assertIsNone(p.resolve('episode_start','bowl','K2')[0])
if __name__=='__main__':unittest.main()
