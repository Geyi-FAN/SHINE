"""Private physical fixture evidence only; never an Agent input."""
import copy
import math
from t4_private_base_evidence import TickRecorder as BaseRecorder,source_ready as original_ready,GOALS
EARLY={'M0','P0','K0'}
ENTITY={1:('bowl','akita_black_bowl_1'),4:('bowl','akita_black_bowl_1'),5:('plate','plate_1'),7:(None,'flat_stove_1'),8:('bowl','akita_black_bowl_1'),9:('wine_bottle','wine_bottle_1')}
def contact_facts(b,spec):
 entity,body=ENTITY[spec['source_task']]
 if not hasattr(b,'easy_contact_geoms'):
  names=[b.env.sim.model.geom_id2name(i)or''for i in range(b.env.sim.model.ngeom)]
  robot={i for i,n in enumerate(names)if n.startswith(('robot0','gripper0'))};target={i for i,n in enumerate(names)if n.startswith(body)}
  if not robot or not target:raise ValueError(('Cannot verify robot/source contact identities',body,len(robot),len(target)))
  b.easy_contact_geoms=(robot,target)
 robot,target=b.easy_contact_geoms;contact=False
 for i in range(b.env.sim.data.ncon):
  c=b.env.sim.data.contact[i]
  if(c.geom1 in robot and c.geom2 in target)or(c.geom2 in robot and c.geom1 in target):contact=True;break
 delta=None
 if entity:
  current=b.cache_reader.windows[entity][-1]['object_position'];delta=math.dist(current,b.t4_recorder.xyz[body])
 return dict(source_entity=entity,source_body=body,robot_source_contact=contact,source_displacement_m=delta,source_policy_actions=b.control_steps-b.task_start_control if b.task_count==1 else 0,stove_on=b.cache_reader.snapshot['native_goal_relations']['turn_on_stove'])
class TickRecorder(BaseRecorder):
 def record(self,phase,stepped=True):
  # Reproduce base trace with the fixture facts captured in the same owner tick.
  b=self.bridge;measurements={};keys=('object_position','eef_position','support_contact','target_contact','finger_contact','bilateral_finger_contact','object_speed','gripper_gap','articulation','geometric_support_contact','container_support_evidence')
  for name,w in b.cache_reader.windows.items():
   if w:measurements[name]={k:copy.deepcopy(w[-1][k])for k in keys if k in w[-1]}
  import time
  row=dict(time=time.time(),monotonic=time.monotonic(),step=b.physics_steps,simulation_time=float(b.env.sim.data.time),control_step=b.control_steps,episode_id=b.state.episode,task_id=b.state.task_id,version=b.state.version,mode=b.state.mode,phase=phase,policy_action=stepped and phase in('authorized_kernel_control','authorized_native_control','source_policy'),physical=copy.deepcopy(b.cache_reader.snapshot),measurements=measurements,episode_initial_positions=self.xyz,proprioception=dict(robot0_gripper_qpos=b.obs['robot0_gripper_qpos'].tolist()),private_fixture=contact_facts(b,self.spec))
  self.recent.append(row)
  if row['policy_action']and row['physical']['native_goal_relations'].get(GOALS[b.case['target_task']])is True:self.policy_goal_seen[b.state.task_id]=True
  import json
  self.stream.write(json.dumps(row,separators=(',',':'))+'\n')
 def __init__(self,bridge,xyz,spec):super().__init__(bridge,xyz,spec);self.spec=spec

def source_ready(ticks,spec,retained=False):
 if spec['phase']not in EARLY:return original_ready(ticks,spec,retained)
 if len(ticks)<3:return False
 window=list(ticks)[-3:]
 for row in window:
  f=row.get('private_fixture',{})
  if(f.get('source_policy_actions',0)<3 or f.get('robot_source_contact',True)or row['physical']['held_object']!='none'):return False
  if spec['phase']=='K0':
   if f.get('stove_on')is not False:return False
  elif f.get('source_displacement_m')is None or f['source_displacement_m']>.002:return False
 return len({r['task_id']for r in window})==1 and bool(window[-1]['task_id'])
