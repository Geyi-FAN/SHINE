"""T6 private evaluator/physical setup. Never supplies Agent stages or actions.

Only the existing Gateway main thread steps physics. Query handlers read an
immutable last snapshot; setup motions are consumed by that same main thread.
"""
import base64,copy,io,json,threading,time
from collections import deque
from grasp_gate_clock import GraspClock
from pathlib import Path
import numpy as np


class Evaluator:
 def __init__(self,b,state,spec,root):
  self.b,self.state,self.spec,self.root=b,state,spec,Path(root)
  self.card=spec['t6_card'];self.lock=threading.RLock();self.latest=None;self.capture=None
  self.grasp_clock=GraspClock(['bowl','cheese','wine_bottle','plate']);self.windows=self.grasp_clock.real_windows
  self.identity=None;self.control=None;self.pending=None;self.home=(b.obs['robot0_eef_pos'].copy(),b.obs['robot0_eef_quat'].copy())
  original=b.apply
  def apply(action,phase):
   value=original(action,phase);self.observe();return value
  b.apply=apply
  self.observe()

 def observe(self):
  b,s=self.b,self.state;reader=b.cache_reader
  p=copy.deepcopy(reader.snapshot)
  rows={k:copy.deepcopy(list(v)[-1]) for k,v in reader.windows.items() if v}
  identity=(s.episode,s.task_id,s.task_intent_revision)
  self.grasp_clock.update(identity,b.physics_steps,b.control_steps,rows)
  self.identity=identity;self.control=b.control_steps;self.windows=self.grasp_clock.real_windows
  from benchmark_metrics.predicates import drawer_gap
  gaps={k:float(drawer_gap(rows['bowl']['articulation'][k])) for k in ['top','middle']}
  proof=dict(held_confirmed_5=self.grasp_clock.confirmed(),held_confirmed_5_policy_actions=self.grasp_clock.confirmed(legacy=True),held_confirmation_clock='distinct_real_control_cycles_including_pose_hold',
   last_error=s.last_error,failure_detail=s.failure_detail,scene_memory=s.scene_memory_status,
   drawer_gaps=gaps,step=b.physics_steps,control_step=b.control_steps,
   episode_id=s.episode,task_id=s.task_id,task_version=s.version,task_intent_revision=s.task_intent_revision,
   state=s.mode,instruction=s.instruction,observed_at=time.time(),physical=p,measurements=rows,
   gripper_qpos=b.obs['robot0_gripper_qpos'].tolist(),eef_position=b.obs['robot0_eef_pos'].tolist(),
   scene_inventory_names=list(b.env.env.obj_body_id),source='private_T6_evaluator_not_model_input')
  if b.physics_steps%2==0 or self.latest is None:
   from PIL import Image
   images=[]
   for key in ['agentview_image','robot0_eye_in_hand_image']:
    f=io.BytesIO();Image.fromarray(np.ascontiguousarray(b.obs[key][::-1,::-1])).save(f,format='JPEG',quality=90);images.append(f.getvalue())
   from qa_image import qa_image
   image=qa_image(*images,'/mnt/disk_4/geyi/audio_switch_benchmark/preflights/c3r_pi05_32_20261108/adapter/web_root/data/visual_atlas_v2')
   capture=dict(image=base64.b64encode(image).decode(),main=base64.b64encode(images[0]).decode(),wrist=base64.b64encode(images[1]).decode(),evidence=proof)
   with self.lock:self.capture=capture
  with self.lock:self.latest=proof
  if b.physics_steps%2==0:
   with (self.root/'t6_physics.private.jsonl').open('a') as f:f.write(json.dumps(proof)+'\n')

 def query(self,body):
  op=body.get('op')
  with self.lock:
   if op=='capture_qa':return copy.deepcopy(self.capture)
   if op=='inspect':return copy.deepcopy(self.latest)
   if op=='gate':
    from t6_gate import gate_errors
    p=copy.deepcopy(self.latest);errors=gate_errors(self.card,p)
    return dict(passed=not errors,errors=errors,evidence=p,observed_at=p['observed_at'],
     identity=dict(episode_id=p['episode_id'],task_id=p['task_id'],task_intent_revision=p['task_intent_revision']))
   if op=='reference_home':
    if self.pending:raise ValueError('Reference setup already running')
    if self.state.mode not in ['completed','needs_review','cancelled','idle'] or (self.b.thread and self.b.thread.is_alive()):
     raise ValueError('Reference setup requires retired/non-running source; cannot bypass pause')
    from scipy.spatial.transform import Rotation
    pos,quat=self.home;obs=self.b.obs
    high=min(max(float(pos[2]),float(obs['robot0_eef_pos'][2]))+.04,float(pos[2])+.11)
    current=obs['robot0_eef_quat'].copy()
    self.pending=dict(targets=[(np.r_[obs['robot0_eef_pos'][:2],high],current,55),(np.r_[pos[:2],high],current,70),(pos,current,60),(pos,quat,65)],index=0,done=0,started=time.monotonic())
    self.b.scoring_active=False;self.b.log('T6_reference_setup_started',source='fixed_initial_eef_reference_no_object_pose')
    return dict(accepted=True)
   if op=='reference_status':return dict(busy=self.pending is not None)
  raise ValueError('Unsupported private evaluator operation')

 def service(self):
  with self.lock:
   job=self.pending
  if not job:return False
  b,s=self.b,self.state
  if s.mode=='paused':return False
  with s.lock,b.env_lock:
   from scipy.spatial.transform import Rotation
   xyz,q,count=job['targets'][job['index']]
   dr=(Rotation.from_quat(q)*Rotation.from_quat(b.obs['robot0_eef_quat']).inv()).as_rotvec()
   action=np.r_[np.clip((xyz-b.obs['robot0_eef_pos'])/.05,-.35,.35),np.clip(dr/.5,-.35,.35),-1.]
   b.apply(action,'T6_reference_setup_not_scored_QA');job['done']+=1
   if job['done']>=count:
    job['index']+=1;job['done']=0
   if job['index']==len(job['targets']):
    from hold_gate import PoseHold
    b.pose=PoseHold(b.obs,b.env.env.robots[0].controller)
    if b.saved_points:
     frame=max(b.saved_points.scene.frame+1,b.physics_steps)
     b.saved_points.update_evidence(frame,b.cache_reader.memory_evidence(),b.cache_reader.memory_camera_id())
     b.saved_points.observe(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1]),frame)
    with self.lock:self.pending=None
    b.log('T6_reference_setup_completed',steps=250,eef_error_m=float(np.linalg.norm(b.obs['robot0_eef_pos']-self.home[0])))
  return True
