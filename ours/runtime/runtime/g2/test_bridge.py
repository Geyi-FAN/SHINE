import ast,copy,io,json,queue,sys,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from bridge import SingleOwnerBridge,RPC,KernelRetired,EpisodeStopped
B=Path(__file__).resolve().parents[1]
class BridgeTests(unittest.TestCase):
 def bridge(self,mode='paused'):
  b=object.__new__(SingleOwnerBridge);b.state=SimpleNamespace(lock=threading.RLock(),mode=mode,episode='e',task_id='t',task_intent_revision=1,version=2,queue=[]);b.env_lock=threading.RLock();b.requests=queue.Queue();b.io={'role':'planning'};b.terminal_reason=None;b.closed=False;b.stale_discarded=0;b.approved_events=[];b.ctx=None;b.applied=[];b.token=lambda:('e','t',1,b.state.version);b.apply=lambda a,phase:b.applied.append((a,phase));b.pose=SimpleNamespace(action=lambda obs:[0]*7);b.obs={};return b
 def test_paused_io_cannot_step(self):
  b=self.bridge();self.assertFalse(b.pump(True));self.assertFalse(b.applied)
 def test_running_io_can_advance_physics(self):
  b=self.bridge('running');self.assertTrue(b.pump(True));self.assertEqual(b.applied[0][1],'async_wait_hold')
 def test_no_tick_ahead_of_20hz_deadline(self):
  b=self.bridge('running');r=RPC('action',([0]*7,),{},b.token());b.requests.put(r);self.assertFalse(b.pump(False));self.assertFalse(r.done.is_set());self.assertFalse(b.applied)
 def test_late_action_after_pause_rejected(self):
  b=self.bridge();r=RPC('action',([0]*7,),{},('e','t',1,1));b.requests.put(r);b.pump(True);self.assertIsInstance(r.error,KernelRetired);self.assertFalse(b.applied)
 def test_old_generation_after_resume_rejected(self):
  b=self.bridge('running');r=RPC('action',([0]*7,),{},('e','t',1,1));b.requests.put(r);b.pump(True);self.assertIsInstance(r.error,KernelRetired);self.assertFalse(b.applied)
 def test_render_during_pause_is_read_only(self):
  b=self.bridge();b.env=SimpleNamespace(sim=SimpleNamespace(render=lambda **kw:'image'));r=RPC('render',(),{},b.token());b.requests.put(r);b.pump(True);self.assertEqual(r.value,'image');self.assertFalse(b.applied)
 def test_engine_busy_does_not_block_control_thread(self):
  b=self.bridge();ready=threading.Event();release=threading.Event()
  def busy():
   with b.env_lock:ready.set();release.wait(1)
  t=threading.Thread(target=busy);t.start();self.assertTrue(ready.wait(1));start=time.monotonic();self.assertFalse(b.pump(True));self.assertLess(time.monotonic()-start,.1);release.set();t.join()
 def test_state_change_continuity_measured_from_rgb_proprio(self):
  b=self.bridge();a={'robot0_eef_pos':np.zeros(3),'robot0_gripper_qpos':np.zeros(2),'agentview_image':np.zeros((2,2,3),np.uint8)};c=copy.deepcopy(a);self.assertTrue(b.continuity(a,c)['passed']);c['robot0_eef_pos'][0]=.01;self.assertFalse(b.continuity(a,c)['passed'])
 def test_candidate_server_physics_call_guarded_by_pause(self):
  tree=ast.parse((B/'freeze/voice/robot_gateway/server.py').read_text());found=[]
  class Visitor(ast.NodeVisitor):
   def __init__(self):self.stack=[]
   def visit_If(self,n):
    self.stack.append(ast.unparse(n.test))
    for c in n.body:self.visit(c)
    self.stack.pop()
    for c in n.orelse:self.visit(c)
   def visit_Call(self,n):
    if isinstance(n.func,ast.Attribute)and isinstance(n.func.value,ast.Name)and n.func.value.id=='env'and n.func.attr=='step':found.append(list(self.stack))
    self.generic_visit(n)
  Visitor().visit(tree);self.assertEqual(len(found),1);self.assertIn("state.mode != 'paused'",found[0])
 def visual_fixture(self,dx=2.,stage=None):
  b=self.bridge();b.physics_steps=10;b.root=Path(tempfile.mkdtemp(prefix='g2-visual-'));b.obs={'robot0_gripper_qpos':np.array([.04,-.04]),'agentview_image':np.zeros((4,4,3),np.uint8)};b.log=lambda *a,**kw:None
  point=dict(entity='bowl',keypoint='K2',yx224=[10.,10.+dx],det_confidence=.99,keypoint_confidence=.99,source='yolo_image_only')
  points=SimpleNamespace(proc=SimpleNamespace(stdin=io.StringIO(),stdout=io.StringIO(json.dumps(dict(points=[point]))+'\n')),memory={('episode_start','bowl','K2'):dict(yx224=[10.,10.])})
  mon=SimpleNamespace(settings=SimpleNamespace(confidence=.35,stable_radius_px=3.,motion_m=.008,open_width_m=.065,min_width_m=.002,closed_width_m=.06,return_radius_px=6.),active=stage)
  context=dict(mon=mon,points=points,obs=copy.deepcopy(b.obs));old=[dict(point,yx224=[10.,10.])];return b,context,old
 def test_small_rgb_change_rechecked_with_same_yolo_and_frozen_thresholds(self):
  b,c,old=self.visual_fixture(2.);ok,proof=b.observed_continuity('planning',c,old,dict(eef_translation_m=.006));self.assertTrue(ok);self.assertEqual(proof['stable_radius_px'],3.)
 def test_object_movement_not_accepted_by_large_background_similarity(self):
  b,c,old=self.visual_fixture(4.);ok,_=b.observed_continuity('planning',c,old,dict(eef_translation_m=.006));self.assertFalse(ok)
 def test_return_rechecks_current_point_against_original_reference(self):
  b,c,old=self.visual_fixture(2.,dict(operation='return_bowl',kind='return',object='bowl'));ok,proof=b.observed_continuity('verifier',c,old,dict(eef_translation_m=.006));self.assertTrue(ok);self.assertTrue(proof['current_checks']['current_object_at_historical_reference'])
 def test_missing_current_return_object_does_not_use_other_keypoint(self):
  b,c,old=self.visual_fixture(2.,dict(operation='return_bowl',kind='return',object='bowl'));p=dict(old[0],keypoint='K1');c['points'].proc.stdout=io.StringIO(json.dumps(dict(points=[p]))+'\n');ok,proof=b.observed_continuity('verifier',c,[p],dict(eef_translation_m=.006));self.assertFalse(ok);self.assertFalse(proof['current_checks']['current_object_at_historical_reference'])
if __name__=='__main__':unittest.main(verbosity=2)
