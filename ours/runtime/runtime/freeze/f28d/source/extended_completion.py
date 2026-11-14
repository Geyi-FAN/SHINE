"""Refined P2: causal scheduling, fixed references, joint acceptance, coherent events.
P2_REFINE_VARIANT=BASE loads the original behavior unchanged.
"""
import os,copy,json
from collections import deque
from pathlib import Path
from extended_completion_frozen import ExtendedCompletion as Frozen,NEW_OPS,CONTAINERS,Settings
class ExtendedCompletion(Frozen):
 def __init__(self,*a,**kw):
  super().__init__(*a,**kw);self.variant=os.environ.get('P2_REFINE_VARIANT','R2');self.rgb_rows=deque(maxlen=512);self.stage_visual={};self.request_observation_hold=False;self.hold_since=None;self.trigger_log=[];self.request_geometry_observation=False
 def select(self,stage):
  super().select(stage);self.stage_visual=dict(last_call=-10000,next_due=self.last+30,count=0,positive_streak=0,last_positive=None);self.request_observation_hold=False;self.hold_since=None;self.request_geometry_observation=False
  from close_observation import CloseObservation
  self.close_observation=CloseObservation()
 def observe(self,*args):
  if self.variant=='BASE' or self.arm!='P2':return super().observe(*args)
  previous=copy.deepcopy(self.active);before=len(self.events);oldarm=self.arm
  # Compute exactly the original S1/RGB-D candidate without the frozen P2 gate.
  self.arm='P1'
  try:candidate=super().observe(*args)
  finally:self.arm=oldarm
  if previous is None or self.final_stage:return candidate
  # Keep sensing during a scripted camera/hand action, but do not commit
  # an intermediate completion or query vision on the pre-withdrawal view.
  # Reuse the existing three-frame evidence minimum after that action ends.
  action_end=getattr(self,'observation_action_end',-1)
  if action_end>=0:
   fresh_after_action=[r for r in self.rgb_rows if r['frame']>=max(action_end,self.entered)]
   defer=self.last<action_end or len(fresh_after_action)<3
   self.diagnostics['observation_action_lifecycle']=dict(action_end=action_end,frame=self.last,fresh_frames=len(fresh_after_action),completion_deferred=defer)
   if defer:
    self.events=self.events[:before];self.active=previous
    self.stage_visual['positive_streak']=0;self.stage_visual['last_positive']=None
    self.request_observation_hold=self.last>=action_end
    self.hold_since=self.last if self.request_observation_hold else None
    return None
  if self.verifier is None:
   if previous['operation'] in CONTAINERS|NEW_OPS and candidate is not None:
    self.events=self.events[:before];self.active=previous;self.diagnostics['visual_skip_reason']='verifier_not_configured';return None
   return candidate
  op=previous['operation'];semantics=op in CONTAINERS|NEW_OPS;is_candidate=candidate is not None
  if is_candidate and not semantics:
   guarded=True
   if os.environ.get('REPAIR_GRASP_GUARD','0')=='1' and previous['kind']=='grasp':
    from grasp_guard import grasp_motion
    evidence=grasp_motion(list(self.rgb_rows),previous,self.entered,self.last)
    self.diagnostics['independent_grasp_motion']=evidence;guarded=evidence['passed']
   if guarded:self.request_observation_hold=False;return candidate
  # Semantic candidates wait for visual agreement. Otherwise the current stage stays selected.
  if is_candidate:self.events=self.events[:before];self.active=previous;candidate=None
  state=self.stage_visual;frame=self.last;dwell=frame-self.entered;elapsed=frame-state['last_call'];pending=state['positive_streak']>0
  enough=len([r for r in self.rgb_rows if r['frame']>=self.entered])>=3
  close_gate=None
  if os.environ.get('REPAIR_CLOSE_CANDIDATE_HOLD','0')=='1' and op.startswith('close_'):
   from close_observation import current_candidate
   level='top' if op.endswith('top') else 'middle'
   was_measurement_hold=self.close_observation.start is not None
   close_gate=self.close_observation.advance(frame,current_candidate(self.geometry,level,self.calibration['closed_handles'][level]))
   if was_measurement_hold and not close_gate['observe']:self.request_observation_hold=False;self.hold_since=None
   if close_gate['observe']:self.request_observation_hold=True;self.hold_since=close_gate['start']
   if close_gate['request_view']:self.request_geometry_observation=True
  trigger='confirm_observation_candidate' if self.request_observation_hold and elapsed>=8 else 'confirm_visual_candidate' if pending and elapsed>=6 else 's1_candidate' if is_candidate and elapsed>=12 else 'periodic_observation' if frame>=state['next_due'] and elapsed>=12 else None
  # Resource bound is explicit and far less restrictive than 6/stage. No silent fallback.
  eligible=enough and trigger and state['count']<24
  if close_gate and close_gate['observe'] and not close_gate['ready']:eligible=False
  if self.variant in ('R8','R9','R10','R11') and eligible:
   # These are exactly the existing post-API hard guards, moved before the API.
   rows=[r for r in self.rgb_rows if r['frame']>=self.entered];recent=rows[-2:];width=self.samples[-1]['width'];guard=True
   if previous['kind']=='grasp':
    zs=[r['sensor']['eef_xyz'][2] for r in rows if r.get('sensor')];lift=self.samples[-1]['eef_xyz'][2]-min(zs) if zs else 0;guard=.002<=width<.060 and lift>=.020
   if previous['kind'] in ('return','release') or op in ('cheese_bowl','bowl_drawer','bowl_stove','bowl_plate','bowl_cabinet','bottle_cabinet','bottle_rack'):
    guard=len(recent)==2 and all(r.get('sensor',{}).get('width',0)>=.065 for r in recent)
   if not guard:
    eligible=False;self.diagnostics['visual_skip_reason']='existing_measured_hard_guard_not_yet_met'
    if pending:state['positive_streak']=0;self.request_observation_hold=False;self.hold_since=None
  if eligible and os.environ.get('CAP_VERIFIER_PREFLIGHT','0')=='1':
   from verifier_preflight import check as preflight_check
   try:preflight=preflight_check(previous,self.entered,frame,list(self.rgb_rows))
   except (KeyError,ValueError,TypeError,OSError):preflight=dict(applicable=False,permit=True,reason='preflight_unassessable_retain_original_path')
   self.diagnostics['verifier_preflight']=preflight
   if not preflight['permit']:
    from verifier_gate import VerifierGate
    if not hasattr(self,'rule_verifier_gate'):self.rule_verifier_gate=VerifierGate(periodic_limit=1 if os.environ.get('CAP_VERIFIER_PERIODIC_ONE','0')=='1'else 2)
    token=(op,self.entered,preflight['reason'])
    if getattr(self,'last_preflight_token',None)!=token:
     self.rule_verifier_gate.events.append(dict(operation=op,entered=self.entered,frame=frame,trigger=trigger,allowed=False,reason='geometry_preflight:'+preflight['reason'],evidence=preflight.get('evidence')))
    self.last_preflight_token=token;eligible=False
  if eligible and os.environ.get('RULE_FIRST_VERIFIER_ENABLED','0')=='1':
   from verifier_gate import VerifierGate
   if not hasattr(self,'rule_verifier_gate'):self.rule_verifier_gate=VerifierGate(periodic_limit=1 if os.environ.get('CAP_VERIFIER_PERIODIC_ONE','0')=='1'else 2)
   admission_guard=None
   if previous['kind']=='grasp' and os.environ.get('REPAIR_GRASP_GUARD','0')=='1':
    from grasp_guard import grasp_motion
    measured=grasp_motion(list(self.rgb_rows),previous,self.entered,frame)
    if measured.get('applicable',True):admission_guard=bool(measured['passed'])
   recovery_epoch=max(getattr(self,'last_code_recovery_frame',-1),getattr(self,'observation_action_end',-1))
   eligible=self.rule_verifier_gate.permit(previous,self.entered,frame,list(self.rgb_rows),trigger,is_candidate,admission_guard,recovery_epoch)
  if eligible:
   state['last_call']=frame;state['count']+=1
   res=self.verifier.check(previous,self.entered,list(self.rgb_rows),self.samples[-1],self.history,self.diagnostics)
   res.update(trigger=trigger,stage_call_index=state['count']);self.trigger_log.append(dict(frame=frame,operation=op,trigger=trigger,accepted=res['accepted']))
   if res['accepted']:
    state['positive_streak']+=1;state['last_positive']=frame
    # RGB-D/S1 has already satisfied sustained measurable guards; otherwise require
    # a second agreeing visual judgment on new frames, not repeated API sampling.
    joint_grasp=False
    if os.environ.get('REPAIR_STRONG_GRASP_JOINT','0')=='1' and previous['kind']=='grasp':
     measured=res.get('independent_grasp_motion',{})
     joint_grasp=measured.get('applicable',True) and measured.get('passed',False) and measured.get('target_lift_m',0)>=.020 and measured.get('current_hand_distance_m',1)<=.080
     self.diagnostics['strong_rgbd_plus_visual_grasp']=bool(joint_grasp)
    if is_candidate or state['positive_streak']>=2 or joint_grasp:
     self.events=self.events[:before];candidate=self._event(previous,frame,'refined_p2_joint_visual_acceptance')
     from completion_proof import build_drawer_proof
     proof=build_drawer_proof(candidate,self.verifier.calls,is_candidate)
     if proof is not None:candidate['completion_proof']=proof
     self.events.append(candidate);self.active=None;self.request_observation_hold=False;self._commit_observed_event(candidate)
    else:self.request_observation_hold=(os.environ.get('REPAIR_DRAWER_GUARD','0')=='1' and op.startswith('close_')) or self.variant not in ('R5','R6','R7','R8','R9','R10','R11');self.hold_since=frame if self.request_observation_hold else None;state['next_due']=frame+6
   else:
    state['positive_streak']=0;self.request_observation_hold=False;self.hold_since=None
    # Early checks every30; after repeated unsuccessful calls back off to60 then90.
    state['next_due']=frame+(30 if state['count']<4 else 60 if state['count']<8 else 90)
    if os.environ.get('REPAIR_DRAWER_GUARD','0')=='1' and op.startswith('close_'):
     measured=res.get('independent_drawer_guard',{})
     missing=measured.get('reason') in ('insufficient_fresh_geometry','insufficient_sustained_depth')
     # A clear measured NOT-CLOSED result means continue closing, not hold/release.
     # A measurable completion candidate or missing evidence calls for observation.
     if measured.get('passed') or missing and res.get('visual_semantics_passed_before_geometry'):
      self.request_observation_hold=True;self.hold_since=frame if self.hold_since is None else self.hold_since;state['next_due']=frame+8;self.request_geometry_observation=True
  if close_gate and close_gate['observe'] and self.active is not None:
   self.request_observation_hold=True;self.hold_since=close_gate['start']
  if self.hold_since is not None and frame-self.hold_since>18:self.request_observation_hold=False
  if close_gate:self.diagnostics['close_candidate_observation']=close_gate
  self.diagnostics['visual_monitor']=dict(state,trigger=trigger,pending_hold=self.request_observation_hold,hard_call_limit=24)
  return candidate
 def _commit_observed_event(self,e):
  # An accepted event must agree with the state sent to the next Agent call.
  # This is an observation-derived estimate, never a simulator contact assertion.
  obj=e['object'];op=e['operation'];s=self.samples[-1]
  if op.startswith('grasp_'):
   self.held=obj;self.last_held_frame=e['confirmed_step'];self.held_width=s['width'];self.snapshot['held_object']=obj
  elif obj in self.snapshot.get('objects',{}) and (op.startswith(('return_','release_')) or op in ('cheese_bowl','bowl_drawer','bowl_stove','bowl_plate','bowl_cabinet','bottle_cabinet','bottle_rack')):
   self.held='none';self.held_width=None;self.snapshot['held_object']='none';self.snapshot['objects'][obj]['supported']=True
   if op.startswith('return_'):self.snapshot['objects'][obj]['returned_and_released']=True
   if op in self.snapshot['native_goal_relations']:self.snapshot['native_goal_relations'][op]=True
  elif op.startswith(('open_','close_')):
   level='top' if 'top' in op else 'middle';opening=op.startswith('open_');self.snapshot['drawers'][level].update(open=opening,closed_current=not opening,closed_confirmed=not opening)
  self.snapshot['last_visual_event']=dict(e,evidence_source='visual_plus_measured_guard_estimate')
