import copy,sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'runtime'))
from unified.native_handoff import ready
class NativeQueueFeedback(unittest.TestCase):
 def setUp(self):
  self.subject=('episode','source',1);self.d=dict(accepted=True,subject=list(self.subject))
  self.s=SimpleNamespace(mode='completed',completion_status='verified',agent_execution=dict(completion_current_verified=True,completion_receipt=dict(source='current_supervisor_verification_each_real_physics_frame',required_physics_frames=40,ready=True,consecutive_verified_physics_frames=40)))
 def test_completed_native_source_without_symbolic_monitor_can_handoff(self):self.assertTrue(ready(self.s,self.d,self.subject))
 def test_running_paused_or_unverified_task_cannot_handoff(self):
  for mode in ['running','paused','cancelled','needs_review']:
   self.s.mode=mode;self.assertFalse(ready(self.s,self.d,self.subject))
 def test_old_task_feedback_cannot_advance_new_task(self):self.assertFalse(ready(self.s,self.d,('episode','another',1)))
 def test_raw_goal_boolean_is_not_full_contract_acceptance(self):
  self.assertFalse(ready(self.s,dict(native_goal=True),self.subject));self.s.agent_execution['completion_current_verified']=False;self.assertFalse(ready(self.s,self.d,self.subject))
 def test_fewer_than_40_frames_or_legacy_text_receipt_is_not_enough(self):
  r=self.s.agent_execution['completion_receipt'];r['consecutive_verified_physics_frames']=39;self.assertFalse(ready(self.s,self.d,self.subject));r['consecutive_verified_physics_frames']=40;r['source']='native_libero_goal_v2';self.assertFalse(ready(self.s,self.d,self.subject))
 def test_no_world_or_symbolic_ownership_is_read(self):
  class World:
   def __getattr__(self,name):raise AssertionError('forbidden world read')
  self.s.memory=World();self.s.saved_mon=World();self.assertTrue(ready(self.s,self.d,self.subject))
if __name__=='__main__':unittest.main()
