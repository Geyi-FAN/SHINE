"""G0/G1 migration adapter. No environment, policy HTTP or actuator capability.

Payloads stay byte-for-byte structurally equal; task/control identity lives outside
F28d's strict eight-key input. Completion is a proposal, not a robot action.
"""
import copy,dataclasses,hashlib,json,math,time
from typing import Optional

PLANNER_KEYS={'user_message','physical_state','completed_events','reference_availability','episode_id','task_version','frame','mode'}
PHYSICAL_KEYS={'source','observed_step','held_object','objects','drawers','native_goal_relations','observed_scene_context','robot','latest_drawer_observations','latest_relation_observations','drawer_predicate_interpretation','planning_handoff_context','execution_language_task','ownership_observation_memory','relation_state_memory','latest_ownership_observation','recovery_observation_memory','visual_observation','observed_relations','last_visual_event','drawer_state_memory'}
PRIVATE_KEYS={'body_xpos','object_poses','ground_truth','gt_positions','oracle_subgoal','oracle_next_stage','next_oracle_operation','task_contract_text','required_invariants','contracts_private','oracle_events','sim_snapshot','private_facts','full_instruction','score','metrics','benchmark_success','initial_xyz'}
ROLES={'wording','planning','verifier','recovery'}
MODEL='Qwen3.8-27B-FP8'
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def deny_private(x,path='input'):
 if isinstance(x,dict):
  for k,v in x.items():
   if k in PRIVATE_KEYS:raise ValueError('Private field rejected: '+path+'.'+k)
   deny_private(v,path+'.'+k)
 elif isinstance(x,list):
  for i,v in enumerate(x):deny_private(v,path+'['+str(i)+']')

def payload_from_body(body):
 for m in body['messages']:
  if m['role']!='user':continue
  c=m['content']
  if isinstance(c,str):return json.loads(c)
  if isinstance(c,list)and c and c[0].get('type')=='text':return json.loads(c[0]['text'])
 raise ValueError('Missing actual initial user payload')

@dataclasses.dataclass(frozen=True)
class Identity:
 episode_id:str
 task_id:str
 semantic_revision:int
 control_generation:int
 stage_id:str
 entered_step:int

@dataclasses.dataclass(frozen=True)
class Observation:
 frame:int
 capture_monotonic:float
 camera_transform_id:str='main256-to224-fixed-v1'

@dataclasses.dataclass(frozen=True)
class Ticket:
 identity:Identity
 observation:Observation
 role:str
 request_sha256:str

class StageTickets:
 """Separate semantic revision, cancellation generation and observation age."""
 def __init__(self,identity):self.identity=identity;self.paused=False;self.consumed=set();self.committed=[]
 def issue(self,role,body,observation):
  if role not in ROLES:raise ValueError('Unknown role')
  if self.paused:raise ValueError('Paused')
  return Ticket(self.identity,observation,role,digest(body))
 def pause(self):self.paused=True;self.identity=dataclasses.replace(self.identity,control_generation=self.identity.control_generation+1)
 def resume(self):self.paused=False;self.identity=dataclasses.replace(self.identity,control_generation=self.identity.control_generation+1)
 def new_task(self,task_id):
  self.identity=dataclasses.replace(self.identity,task_id=task_id,semantic_revision=self.identity.semantic_revision+1,control_generation=self.identity.control_generation+1,stage_id='initial',entered_step=0);self.paused=False
 def reset(self,episode_id):
  self.identity=Identity(episode_id,'none',0,self.identity.control_generation+1,'initial',0);self.paused=False;self.committed=[]
 def qa(self):return self.identity
 def advance(self,stage_id,entered):self.identity=dataclasses.replace(self.identity,stage_id=stage_id,entered_step=entered)
 def accepts(self,ticket,now,*,action=False,current_evidence_frame=None,contradicted=False):
  if self.paused or ticket.identity!=self.identity:return False,'identity_or_pause'
  if digest(dataclasses.asdict(ticket))in self.consumed:return False,'duplicate'
  if ticket.observation.capture_monotonic>now:return False,'future_capture'
  if action and now-ticket.observation.capture_monotonic>3:return False,'stale_action_observation'
  if not action and(current_evidence_frame is None or current_evidence_frame<ticket.observation.frame or contradicted):return False,'missing_or_contrary_current_evidence'
  return True,'eligible_proposal_only'
 def commit(self,ticket,now,**kwargs):
  ok,reason=self.accepts(ticket,now,**kwargs)
  if ok:self.consumed.add(digest(dataclasses.asdict(ticket)));self.committed.append(dict(role=ticket.role,frame=ticket.observation.frame))
  return ok,reason

class ObservedSceneStateStore:
 """Stores only vetted observation packets; never accepts simulator snapshots."""
 def __init__(self):self.packet=None
 def publish(self,physical_state,observation,*,fresh_detector_points,resolved_action_references):
  deny_private(physical_state)
  if set(physical_state)-PHYSICAL_KEYS:raise ValueError('Unknown physical fields: '+str(set(physical_state)-PHYSICAL_KEYS))
  src=str(physical_state.get('source',''))
  if not src.startswith(('s1_','observed_','image_')):raise ValueError('State is not observation-derived')
  for p in fresh_detector_points:
   if p.get('frame')!=observation.frame or p.get('time_source','current')!='current':raise ValueError('Historical point cannot be fresh completion evidence')
  self.packet=dict(physical_state=copy.deepcopy(physical_state),observation=observation,fresh_detector_points=copy.deepcopy(fresh_detector_points),resolved_action_references=copy.deepcopy(resolved_action_references))
  return self.packet

class F28dExecutionAdapter:
 """Capability-limited boundary, intended for the later single-owner Gateway.
 Runtime binding is deliberately absent during G0/G1. Callers cannot env.step.
 """
 def planner_input(self,payload,identity):
  deny_private(payload)
  if set(payload)!=PLANNER_KEYS:raise ValueError('Strict eight-key planner interface')
  if payload['episode_id']!=identity.episode_id or payload['task_version']!=identity.semantic_revision:raise ValueError('Semantic identity mismatch')
  if set(payload['physical_state'])-PHYSICAL_KEYS:raise ValueError('Unknown physical_state fields: '+str(set(payload['physical_state'])-PHYSICAL_KEYS))
  return copy.deepcopy(payload)
 def role_body(self,role,body):
  if role not in ROLES or body.get('model')!=MODEL:raise ValueError('Frozen local model/role mismatch')
  p=payload_from_body(body);deny_private(p)
  if role=='planning'and set(p)!=PLANNER_KEYS:raise ValueError('Planner allowlist mismatch')
  allowed={'wording':{'original_user_message','current_image_observation'},'verifier':{'schema','user_message','selected_subgoal','entered_step','required_checks','coordinate_systems','recent_frames','stage_start','historical_target_references','s1_fallible_estimates','estimate_warning','historical_landmark_points','independent_rgbd_grasp_measurements','independent_rgbd_measurement_warning'},'recovery':{'schema','user_message','sensor_frames','fallible_holding_estimate','observation_request_context','measured_gripper_width_m','opening_definition','historical_visual_reference'}}
  if role in allowed and set(p)-allowed[role]:raise ValueError('Unknown '+role+' fields: '+str(set(p)-allowed[role]))
  return copy.deepcopy(body)
 def dispatch_action(self,*args,**kwargs):raise RuntimeError('G0/G1 zero-action mode: no actuator capability')

def bind_policy_reference(decision,point,*,camera_transform_id,expected_episode_id):
 """Same MAIN224 float -> MAIN256 final rounding as frozen Points.bind()."""
 if decision.get('status')!='plan_ready':raise ValueError('Blocked/hold cannot produce policy prompt')
 reference=decision.get('reference');text=decision['policy_prompt_template']
 if not reference:
  if '{'in text or'}'in text:raise ValueError('Unexpected unbound reference')
  return text,None
 if not point:raise ValueError('No (0,0) fallback or K substitution')
 if point.get('episode_id',expected_episode_id)!=expected_episode_id:raise ValueError('Wrong episode point')
 if point.get('camera_transform_id',camera_transform_id)!=camera_transform_id:raise ValueError('Wrong camera version')
 for key in ('entity','keypoint'):
  if point.get(key)!=reference[key]:raise ValueError('Wrong point type')
 if point.get('time_source')!=reference['time_source']:
  # A CURRENT reference may resolve to a still-valid historical STATIC anchor.
  # The resolver must explicitly certify this; history alone is not permission.
  validated_static=(reference['time_source']=='current'and point.get('resolution')=='cached'and point.get('cache_validated')is True and point.get('reference_time_source')=='current')
  if not validated_static:raise ValueError('Wrong time source')
 yx=point.get('yx224')
 if not isinstance(yx,list)or len(yx)!=2 or not all(isinstance(v,(int,float))and math.isfinite(v)and 0<=v<=223 for v in yx):raise ValueError('Invalid point')
 out=[round((v+.5)*256/224-.5)for v in yx]
 token='{'+'.'.join(reference[k]for k in ('time_source','entity','keypoint'))+'}'
 text=text.replace(token,'<'+','.join(map(str,out))+'>')
 if '{'in text or'}'in text:raise ValueError('Unbound reference')
 return text,dict(yx=out,source_frame=point.get('frame'),source_time_source=point.get('time_source'),resolution=point.get('resolution','recorded'),camera_transform_id=camera_transform_id)
