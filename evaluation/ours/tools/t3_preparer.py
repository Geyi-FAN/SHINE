"""Benchmark-owned fixed source preparation, never an execution Agent tool.

Replays real control actions from the published T6 bank with the identical
initial fixture. Construction stops inside the original T3 physical predicate.
No simulator coordinates, phase answer or expert instruction enters a model.
"""
from pathlib import Path
import hashlib,json,time
import numpy as np
from t3_source_window import reached

BASE=Path('/mnt/disk_4/geyi/audio_switch_benchmark/T6/releases/t6-prefix-v2-20261108')
POOL={
 '0_D1':'T6SC_DRAWER_STATE_PARTLY_OPEN',
 '1_M2':'T6SC_CURRENT_ACTION_CARRY_BOWL',
 '4_M2':'T6SC_EXTRA_BOWL_TO_CABINET',
 '6_M2':'T6SC_CHEESE_BOWL_CHEESE_HELD',
 '9_M2':'T6SC_ABSENT_TENNIS_WINE_TO_RACK',
}
class SourcePreparer:
 def __init__(self,b,state,spec,root):
  self.b,self.state,self.spec,self.root=b,state,spec,Path(root)
  self.key=str(spec['source_task'])+'_'+spec['phase'];self.construct=spec.get('t3_prepare_mode')=='construct'
  self.bank=Path(spec['t3_bank_root'])/self.key
  if self.construct:
   self.use_verified_v1=bool(spec.get('t3_construct_from_verified_v1'))
   folder=Path(spec['t3_construct_from_verified_v1'])/self.key if self.use_verified_v1 else BASE/'prefixes'/POOL.get(self.key,'T6SC_ABSENT_TENNIS_WINE_TO_RACK')
   meta=json.loads((folder/'PREFIX.json').read_text());self.expected_identity=None
  else:
   folder=self.bank;meta=json.loads((folder/'PREFIX.json').read_text());self.expected_identity=meta['state_identity']
  actual={k:v['sha256']for k,v in spec['fixture']['assets'].items()}
  expected={k:v['sha256']for k,v in meta['fixture']['assets'].items()}
  assert actual==expected and spec['fixture']['scene_seed']==meta['fixture']['scene_seed'],'fixture_mismatch'
  p=folder/'actions.jsonl';assert hashlib.sha256(p.read_bytes()).hexdigest()==meta['actions_sha256']
  self.actions=[json.loads(x)['action']for x in p.read_text().splitlines()]
  assert len(self.actions)==meta['steps'] and all(np.shape(x)==(7,)and np.isfinite(x).all()for x in self.actions)
  self.index=0;self.rows=[];self.streak=0;self.done=False;self.adopted=False;self.started=time.time();self.initial_stove=0.
  self.live_after_u0=not(self.construct or spec.get('t3_prepare_validate_only'))
  self.source_id=None;self.rejected=False
  state.ready=self.live_after_u0;state.mode='idle'if self.live_after_u0 else'loading';b.scoring_active=False
  if self.construct:self.bank.mkdir(parents=True,exist_ok=False)
  self.meta=meta;self.pool_folder=str(folder)
  self.extra_pose=None;self.extra_remaining=None
  if not self.construct:
   from prefix_observation import observe
   observe(b)
   previous=b.apply
   def observed_apply(action,phase):
    result=previous(action,phase)
    if b.task_count<=1 and b.physics_steps%3==0:observe(b)
    return result
   b.apply=observed_apply
 def phase_ready(self,margin=False):
  # A private constructor predicate, not an observed Agent completion event.
  t=dict(self.b.audit.last,task_id='preparer',mode='running',policy_actions=self.index)
  valid=reached(t,self.spec,'preparer',self.initial_stove)
  if margin and self.spec['phase']=='D1':
   gap=abs(t['measurements']['bowl']['articulation']['middle'])
   valid=valid and .04<=gap<=.11
  return valid
 def service(self):
  b,s=self.b,self.state
  assert not self.done and b.task_count==0,'preparation_only_before_method_execution'
  if self.live_after_u0:
   if not s.task_id or s.mode=='paused':return False
   if self.source_id is None:
    from continuation.live.objectives import compile_objective
    try:
     obj=compile_objective(s.instruction,b.case['initial_xyz'],b.case['initial_xyz'],b.source.measure()['articulation'])
     matched=obj.target_task==self.spec['source_task']
    except Exception:matched=False
    if not matched:
     self.rejected=True;self.done=True;s._hold('needs_review','accepted_source_goal_does_not_match_original_U0')
     (self.root/'SOURCE_PREPARATION.json').write_text(json.dumps(dict(passed=False,reason='accepted_source_goal_mismatch',expected_source_not_injected=True))+'\n')
     return False
    self.source_id=s.task_id
    s.agent_execution=dict(phase='benchmark_reference_source_preparation',task_id=s.task_id,semantic_revision=s.task_intent_revision,
                          source='declared_common_source_preparer',completion_current_verified=False)
   if s.task_id!=self.source_id:raise RuntimeError('source_task_changed_during_private_preparation')
  else:assert not s.task_id,'construction_and_cold_validation_have_no_user_task'
  with s.lock,b.env_lock:
   for _ in range(6):
    if self.index>=len(self.actions):
     if self.construct and self.use_verified_v1 and self.spec['phase']=='M2'and self.extra_remaining is None:
      from hold_gate import PoseHold
      self.extra_pose=PoseHold(b.obs,b.env.env.robots[0].controller);self.extra_pose.xyz[2]+=.025;self.extra_remaining=14
     if not self.extra_remaining:break
    action=self.extra_pose.action(b.obs)if self.extra_remaining else self.actions[self.index]
    b.apply(action,'T3_private_fixed_preparation_not_method_actions')
    if self.extra_remaining:self.extra_remaining-=1
    self.index+=1;self.rows.append(dict(step=self.index,action=action,phase='benchmark_preparation'))
    self.streak=self.streak+1 if self.phase_ready(margin=True)else 0
    if not self.construct and self.index==len(self.actions):
     from prefix_observation import observe
     observe(b)
    if self.construct and self.streak>=3 and not self.use_verified_v1:break
   if self.construct:
    complete=self.streak>=3 and(not self.use_verified_v1 or self.index>=len(self.actions)and(self.spec['phase']!='M2'or self.extra_remaining==0))
   else:complete=self.index==len(self.actions)
   if complete:
    context=b.authority.state.capture(b.env);identity=b.authority.state.identity(context)
    valid=self.phase_ready()and(self.construct or identity==self.expected_identity)
    if not valid:raise RuntimeError('fixed_source_endpoint_invalid')
    if self.construct:
     path=self.bank/'actions.jsonl';path.write_text(''.join(json.dumps(x)+'\n'for x in self.rows))
     np.savez_compressed(self.bank/'endpoint.npz',**context)
     meta=dict(version='T3-controlled-source-prefix-v2-20261109'if self.use_verified_v1 else'T3-controlled-source-prefix-v1-20261109',source_key=self.key,fixture=self.spec['fixture'],
       source_pool=self.pool_folder,
       steps=self.index,actions_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
       endpoint_sha256=hashlib.sha256((self.bank/'endpoint.npz').read_bytes()).hexdigest(),state_identity=identity,
       original_trigger_unchanged=True,complete_all_tick_actions=True,includes_holds=True,
       construction_margin={'D1_middle_gap_m':[.04,.11],'consecutive_frames':3},
       chosen_before_any_switch_audio_or_downstream_outcome=True)
     if self.use_verified_v1:meta.update(construction_from_verified_v1=True,universal_M2_clear_lift_m=.025,universal_M2_extra_control_ticks=14,not_selected_by_Ours_downstream_score=True)
     (self.bank/'PREFIX.json').write_text(json.dumps(meta,indent=2)+'\n')
     (self.bank/'ENDPOINT.private.json').write_text(json.dumps(b.audit.last,indent=2)+'\n')
    from hold_gate import PoseHold
    b.pose=PoseHold(b.obs,b.env.env.robots[0].controller)
    self.done=True;s.ready=True;s.mode='running'if self.live_after_u0 else'idle'
    result=dict(passed=True,steps=self.index,source_key=self.key,actual_state_identity=identity,
                original_T3_predicate_passed=True,no_switch_audio_during_setup=True,source_U0_precedes_preparation=self.live_after_u0,memory_from_actual_RGB=True,
                private_preparer_not_Agent_execution=True,construct=self.construct,seconds=time.time()-self.started)
    (self.root/'SOURCE_PREPARATION.json').write_text(json.dumps(result,indent=2)+'\n')
    if self.construct or self.spec.get('t3_prepare_validate_only'):b.stopping=True
   elif self.index>=len(self.actions)and not(self.construct and self.use_verified_v1 and self.spec['phase']=='M2'and(self.extra_remaining is None or self.extra_remaining>0)):
    raise RuntimeError('source_pool_did_not_reach_original_T3_phase:'+self.key)
 def adopt_source(self):
  b,s=self.b,self.state
  if self.adopted or self.rejected or not self.done or not s.task_id or s.mode!='running':return
  assert b.task_count==0 and not b.thread,'source_preparer_does_not_override_a_running_method'
  b.task=s.task_id;b.task_count=1;b.task_start_control=b.control_steps;b.task_started=time.monotonic()
  b.case.update(public_user_instruction=s.instruction,instruction=s.instruction,current_instruction=s.instruction,
                target_task=self.spec['source_task'],source_task=self.spec['source_task'])
  b.route='benchmark_prepared_predecessor';b.fixture_hold=True;b.fixture_used=True;b.source_phase_streak=3
  # This is the user's actually accepted U0, not a typed benchmark command.
  # No expert text, expected U1 plan or completion event is injected.
  s.execution_profile='benchmark_prepared_predecessor'
  s.agent_execution=dict(phase='executing_prepared_predecessor',task_id=s.task_id,
     semantic_revision=s.task_intent_revision,source='declared_benchmark_preparation',completion_current_verified=False)
  b.engine_start_step=b.control_steps
  b.saved_points.begin_instruction(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1]),max(b.control_steps,b.saved_points.scene.frame))
  self.adopted=True;b.audit.record()
  b.log('benchmark_prepared_source_adopted',source_task=self.spec['source_task'],no_typed_task_injection=True,
        setup_actions_excluded_from_method=True,actual_user_instruction=s.instruction)
