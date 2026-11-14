"""Private, read-only physical evidence. Passive pause samples do not step physics."""
import copy,json,time
from pathlib import Path
import numpy as np
class Recorder:
 def __init__(self,root,bridge):
  self.root=Path(root);self.b=bridge;self.file=(self.root/'physical.jsonl').open('w');self.last=None;self.seq=0;self.hold_remaining=0;self.last_passive=0
 def record(self,phase='passive',owner=None):
  with self.b.state.lock:return self._record(phase,owner)
 def _record(self,phase='passive',owner=None):
  b=self.b;s=b.state;self.seq+=1;rows={k:dict(v[-1])for k,v in b.cache_reader.windows.items()if v};facts=copy.deepcopy(b.cache_reader.snapshot)
  policy=phase in ('authorized_kernel_control','source_policy','authorized_native_control')
  row=dict(time=time.time(),monotonic=time.monotonic(),episode_id=s.episode,sample=self.seq,step=b.physics_steps,simulation_time=float(b.env.sim.data.time),task_id=s.task_id if owner is None else owner[0],version=s.version if owner is None else owner[1],mode=s.mode,phase=phase,physics_tick=phase!='passive',policy_action=policy,policy_actions=b.control_steps,physical=facts,measurements={obj:{k:v for k,v in measured.items()if k in ('object_position','object_quaternion_wxyz','eef_position','target_contact','finger_contact','support_contact','articulation')}for obj,measured in rows.items()},episode_initial_positions=b.case['initial_xyz'],proprioception={k:np.asarray(b.obs[k]).tolist()for k in ('robot0_eef_pos','robot0_eef_quat','robot0_gripper_qpos')},state_hash=b.state_hash())
  from repair.physical_extra import evidence
  row['evaluator_extra']=evidence(b.env,b.obs)
  row.update(task_count=b.task_count,task_started=b.task_started,fixture_hold=b.fixture_hold,source_phase_reached=b.source_phase_streak>=3,hold_remaining=self.hold_remaining,route=b.route,kernel_error=b.kernel_error)
  self.file.write(json.dumps(row)+'\n');self.file.flush();self.last=row
 def passive(self):
  if time.monotonic()-self.last_passive<.05:return
  self.last_passive=time.monotonic()
  if self.b.state.mode in ('paused','idle','completed','budget_exhausted','needs_review','cancelled'):self.record()
 def close(self):self.file.close()
