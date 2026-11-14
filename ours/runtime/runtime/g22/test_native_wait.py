import unittest
from types import SimpleNamespace as N
import numpy as np
from g22.native_wait import tick

class NativeWaitTests(unittest.TestCase):
 def bridge(self):
  def log(kind,**kw):
   assert not(set(kw)&{'kind','simulation_time','physics_step','control_step'}),'bridge adds these fields automatically'
  return N(obs={'robot0_eef_pos':np.array([.1,.2,.9])},env=N(env=N(robots=[N(controller=None)]),sim=N(data=N(time=1.))),pose='episode_start',log=log)
 def test_new_future_captures_current_pose(self):
  b=self.bridge();n=N(future=None);n.tick=lambda *_:setattr(n,'future',object());tick(b,n,None,{},lambda obs,_:obs['robot0_eef_pos'].copy());np.testing.assert_array_equal(b.pose,[.1,.2,.9])
 def test_same_inflight_future_keeps_request_pose(self):
  b=self.bridge();b.pose='request_pose';n=N(future=object(),tick=lambda *_:None);tick(b,n,None,{},lambda *_:self.fail('must not rebase a still-inflight request'));self.assertEqual(b.pose,'request_pose')
 def test_no_request_does_not_invent_hold(self):
  b=self.bridge();n=N(future=None,tick=lambda *_:None);tick(b,n,None,{},lambda *_:self.fail('no request'));self.assertEqual(b.pose,'episode_start')
if __name__=='__main__':unittest.main()
