import unittest,os,json,ast
import numpy as np
from pathlib import Path
from extended_completion import ExtendedCompletion,Settings
from depth_sensor import xyz_from_point
R=Path(__file__).resolve().parent.parent
os.environ.setdefault('P012_DRAWER_CALIBRATION',str(R/'data/drawer_calibration.json'))
def point(e,k,yx,f):return dict(entity=e,keypoint=k,yx224=yx,frame=f,source='yolo_image_only',det_confidence=.99,keypoint_confidence=.99)
def observe(m,f,points=None,geometry=None,width=.08):
 m.supply(f,np.zeros((224,224,3),np.uint8),np.zeros((224,224,3),np.uint8),geometry or {})
 return m.observe(f,[0,0,1],[width/2,-width/2],[200,200],points or [])
class Tests(unittest.TestCase):
 def setUp(self):os.environ['P012_ARM']='P1'
 def test_depth_sensor_center(self):
  cal=dict(position=[0,0,0],rotation=np.eye(3).tolist(),focal=128)
  self.assertTrue(np.allclose(xyz_from_point([111.5,111.5],np.ones((256,256)),cal),[0,0,-1]))
 def test_invalid_depth_unknown(self):
  self.assertIsNone(xyz_from_point([100,100],np.zeros((256,256)),dict(position=[0]*3,rotation=np.eye(3).tolist(),focal=128)))
 def test_closed_confirmation_temporal(self):
  m=ExtendedCompletion();c=m.calibration['closed_handles']['top'];g={'top_handle.K1':c['xyz']}
  observe(m,0,geometry=g);m.select(dict(operation='close_top',kind='close',object='top_drawer'))
  for f in [3,6]:self.assertIsNone(observe(m,f,geometry=g))
  self.assertIsNotNone(observe(m,9,geometry=g))
 def test_missing_handle_unknown(self):
  m=ExtendedCompletion();observe(m,0);m.select(dict(operation='open_top',kind='open_top',object='top_drawer'));self.assertIsNone(observe(m,3));self.assertIsNone(m.snapshot['drawers']['top']['open'])
 def test_partial_drawer_not_open(self):
  m=ExtendedCompletion();c=m.calibration['closed_handles']['top'];g={'top_handle.K1':(np.array(c['xyz'])+.04*np.array(c['opening_axis'])).tolist()}
  observe(m,0,geometry=g);m.select(dict(operation='open_top',kind='open_top',object='top_drawer'))
  for f in [3,6,9,12]:self.assertIsNone(observe(m,f,geometry=g))
 def test_open_top_confirmed(self):
  m=ExtendedCompletion();c=m.calibration['closed_handles']['top'];g={'top_handle.K1':(np.array(c['xyz'])+.16*np.array(c['opening_axis'])).tolist()}
  observe(m,0,geometry=g);m.select(dict(operation='open_top',kind='open_top',object='top_drawer'))
  for f in [3,6]:self.assertIsNone(observe(m,f,geometry=g))
  self.assertIsNotNone(observe(m,9,geometry=g))
 def test_container_depth_contradiction(self):
  m=ExtendedCompletion();observe(m,0);m.select(dict(operation='cheese_bowl',kind='target',object='cheese'))
  for f in [3,6,9,12]:
   p=[point('cheese','K2',[100,100],f),point('cheese','K1',[100,100],f),point('bowl','K3',[100,100],f)]
   self.assertIsNone(observe(m,f,p,{'cheese.K2':[0,0,1.3],'bowl.K3':[0,0,1.0]}))
 def test_push_needs_no_grasp(self):
  m=ExtendedCompletion();observe(m,0);m.select(dict(operation='push_plate',kind='target',object='plate'))
  e=None
  for f in [3,6,9,12]:e=observe(m,f,[point('plate','K2',[100,100],f),point('table_front_placement','K3',[100,100],f)],width=.08)
  self.assertIsNotNone(e)
 def test_stable_cache_not_fresh(self):
  m=ExtendedCompletion()
  with self.assertRaises(ValueError):observe(m,0,[dict(point('plate','K2',[1,1],0),source='cached')])
 def test_p0_does_not_emit_observable_event(self):
  os.environ['P012_ARM']='P0';m=ExtendedCompletion();observe(m,0);m.select(dict(operation='push_plate',kind='target',object='plate'))
  for f in [3,6,9,12]:self.assertIsNone(observe(m,f,[point('plate','K2',[100,100],f),point('table_front_placement','K3',[100,100],f)]))
  self.assertIsNotNone(m.active);self.assertEqual(m.events,[])
 def test_p2_rejected_candidate_does_not_fall_back(self):
  os.environ['P012_ARM']='P2';m=ExtendedCompletion()
  class Reject:
   calls=0
   def check(self,*args):self.calls+=1;return {'accepted':False}
  m.verifier=Reject();c=m.calibration['closed_handles']['top'];g={'top_handle.K1':c['xyz']}
  observe(m,0,geometry=g);m.select(dict(operation='close_top',kind='close',object='top_drawer'))
  for f in [3,6,9,12,15]:self.assertIsNone(observe(m,f,geometry=g))
  self.assertEqual(m.verifier.calls,1);self.assertIsNotNone(m.active)
 def test_p2_call_exhaustion_not_automatic_success(self):
  os.environ['P012_ARM']='P2';m=ExtendedCompletion();c=m.calibration['closed_handles']['top'];g={'top_handle.K1':c['xyz']}
  class MustNotCall:
   def check(self,*args):raise AssertionError('exhausted verifier must not be called')
  m.verifier=MustNotCall()
  observe(m,0,geometry=g);m.select(dict(operation='close_top',kind='close',object='top_drawer'));m.stage_visual['count']=24
  for f in [3,6,9,12]:self.assertIsNone(observe(m,f,geometry=g))
  self.assertEqual(m.events,[])
 def test_no_simulator_imports(self):
  for name in ['extended_completion.py','depth_sensor.py','visual_verifier.py']:
   text=(R/'source'/name).read_text();tree=ast.parse(text)
   for node in ast.walk(tree):
    if isinstance(node,ast.ImportFrom):self.assertNotIn(node.module,['completion','benchmark_metrics','sim_runtime','sym_geometry'])
 def test_dataset_split(self):
  if not (R/'data/cases.jsonl').exists():self.skipTest('Historical 96-case dataset fixture is not copied into this 11-case repair workspace; original split is unchanged.')
  a=list(map(json.loads,(R/'data/cases.jsonl').read_text().splitlines()));self.assertEqual(len(a),96)
  self.assertFalse({c['root_id'] for c in a if c['split']=='dev'}&{c['root_id'] for c in a if c['split']=='holdout'})
if __name__=='__main__':unittest.main()
