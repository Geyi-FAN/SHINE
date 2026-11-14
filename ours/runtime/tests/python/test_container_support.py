import copy,unittest
from types import SimpleNamespace as NS
import numpy as np
from entryfix.support import container_support
class Support(unittest.TestCase):
 def mon(self,vertical=.06,native=True,robot=False,z=.8):
  c=NS(geom1=1,geom2=2,frame=np.eye(3).ravel(),pos=np.array([0,0,z]));d=NS(contact=[c],ncon=1,xipos=np.array([[0,0,1.]]))
  def force(m,d,i,out):out[:3]=[1,0,vertical]
  return NS(model=None,live=d,target_geoms={2},robot_geoms={1}if robot else set(),object_geom_owner={1:'akita_black_bowl_1'},target_body=0,mj=NS(mj_contactForce=force),env=NS(env=NS(_eval_predicate=lambda _:native)),config=NS(minimum_support_force=.001))
 def test_horizontal_normal_with_upward_friction_is_load_bearing(self):
  r=container_support(self.mon());self.assertTrue(r['loaded']);self.assertEqual(r['contacts'][0]['normal_z'],0)
 def test_contact_without_upward_load_is_not_support(self):self.assertFalse(container_support(self.mon(vertical=0))['loaded'])
 def test_robot_contact_does_not_supply_external_support(self):self.assertFalse(container_support(self.mon(robot=True))['loaded'])
 def test_no_containment_is_not_container_support(self):self.assertFalse(container_support(self.mon(native=False))['loaded'])
 def test_contact_above_com_is_not_support(self):self.assertFalse(container_support(self.mon(z=1.1))['loaded'])
 def test_force_below_existing_minimum_is_rejected(self):self.assertFalse(container_support(self.mon(vertical=.0001))['loaded'])
 def test_canonical_measurement_preserves_original_geometry_and_measured_force(self):
  from entryfix.support import augmented
  raw=dict(support_contact=False,object_position=[0.,0.,1.])
  fixed=augmented(self.mon(),raw)
  self.assertTrue(fixed['support_contact']);self.assertFalse(fixed['geometric_support_contact'])
  self.assertTrue(fixed['container_support_evidence']['loaded']);self.assertFalse(raw['support_contact'])
 def test_final_release_uses_same_measured_support_as_private_trace(self):
  from entryfix.support import augmented
  from unified.final_release import evidence
  from benchmark_metrics.config import load_rules
  raw=dict(support_contact=False,target_contact=False,object_position=[0.,0.,1.],eef_position=[0.,0.,1.1])
  canonical=[augmented(self.mon(),raw)for _ in range(5)]
  bridge=NS(case=dict(target_task=6),rules=load_rules(),cache_reader=NS(windows=dict(cheese=canonical)))
  self.assertTrue(evidence(bridge)['passed']);self.assertFalse(any(f['geometric_support_contact']for f in canonical))
  bridge.cache_reader.windows['cheese']=[augmented(self.mon(vertical=0),raw)for _ in range(5)]
  self.assertFalse(evidence(bridge)['passed'])
 def test_actual_bridge_install_updates_private_reader_not_online_monitor(self):
  import sys
  from unittest.mock import patch
  from entryfix.support import install
  mon=self.mon();mon.measure=lambda:dict(support_contact=False);mon.target_name='cream_cheese_1'
  class Bridge:
   def __init__(self):self.cache_reader=NS(mon=dict(cheese=mon));self.target=mon;self.online_monitor=object()
   def measure(self,phase):return self.cache_reader.mon['cheese'].measure()
  class Gate:
   def observe(self,*a,**k):return False
  with patch.dict(sys.modules,{'t3repair.terminal':NS(CompletionGate=Gate)}):
   install(Bridge);bridge=Bridge();online=bridge.online_monitor
   measured=bridge.cache_reader.mon['cheese'].measure()
   self.assertTrue(measured['support_contact']);self.assertFalse(measured['geometric_support_contact'])
   self.assertIs(bridge.online_monitor,online)
if __name__=='__main__':unittest.main()
