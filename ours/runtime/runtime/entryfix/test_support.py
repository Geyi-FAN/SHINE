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
if __name__=='__main__':unittest.main()
