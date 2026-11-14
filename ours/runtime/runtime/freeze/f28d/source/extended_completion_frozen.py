"""Observable intermediate predicates. No simulator, joint truth, masks or benchmark imports."""
import os,json,copy
from pathlib import Path
from collections import deque
import numpy as np
from completion_s1_base import ObservedCompletion as Base,Settings,distance,DESTINATIONS

NEW_OPS={'open_middle','open_top','close_middle','close_top','push_plate','turn_on_stove','maintain'}
CONTAINERS={'cheese_bowl','bowl_drawer'}
class ExtendedCompletion(Base):
 def __init__(self,history=None,settings=None):
  super().__init__(history,settings);self.arm=os.environ.get('P012_ARM','P1');self.sensor=None;self.geometry={};self.rgb_rows=deque(maxlen=12);self.ext_rows=deque(maxlen=6);self.stage_frame=None;self.verifier=None;self.final_stage=False;self.last_verify=-10000;self.verify_counts={};self.last_mon_snapshot=None
  path=Path(os.environ['P012_DRAWER_CALIBRATION']);self.calibration=json.loads(path.read_text()) if path.exists() else {}
 def supply(self,frame,main,wrist,geometry):
  self.geometry=geometry
  self.rgb_rows.append(dict(frame=frame,main=np.array(main),wrist=np.array(wrist),geometry=copy.deepcopy(geometry)))
 def _drawer(self,level):
  p=self.geometry.get(level+'_handle.K1');cal=self.calibration.get('closed_handles',{}).get(level)
  if p is None or cal is None:return dict(open=None,closed_current=None,closed_confirmed=None)
  delta=np.asarray(p)-np.asarray(cal['xyz']);gap=float(np.dot(delta,np.asarray(cal['opening_axis'])))
  # RGB-D reference was calibrated on development images; not the live joint coordinate.
  closed=abs(gap)<=.010;opened=gap>=.145
  self.ext_rows[-1]['drawer_gaps'][level]=gap
  recent=[r['drawer_gaps'].get(level) for r in self.ext_rows]
  sustained=len(recent)>=4 and self.ext_rows[-1]['frame']-self.ext_rows[-4]['frame']>=9
  return dict(open=bool(opened),closed_current=bool(closed),closed_confirmed=bool(sustained and all(x is not None and abs(x)<=.010 for x in recent[-4:])))
 def _container(self,op,s):
  obj,target=('cheese','bowl') if op=='cheese_bowl' else ('bowl','top_drawer_interior')
  a=self.geometry.get(obj+'.K2');b=self.geometry.get(target+'.K3')
  if a is None or b is None:return None
  delta=np.asarray(a)-np.asarray(b)
  # Ray-depth of labeled visible references. Broad geometric proxy, not proof of support.
  relation=bool(np.linalg.norm(delta[:2])<=.045 and -.02<=delta[2]<=.065)
  if op=='bowl_drawer':relation=relation and self.snapshot['drawers']['top']['open'] is True
  return bool(relation and self._released(s,obj))
 def observe(self,*args):
  previous=copy.deepcopy(self.active);before=len(self.events)
  extended=previous and previous['operation'] in NEW_OPS|{'bowl_drawer'}
  if extended:self.active=None
  candidate=super().observe(*args)
  if extended:self.active=previous
  frame=self.last;s=self.samples[-1]
  if self.rgb_rows:self.rgb_rows[-1]['sensor']=dict(width=s['width'],eef_xyz=s['eef_xyz'],eef_yx=s['eef_yx'])
  self.ext_rows.append(dict(frame=frame,drawer_gaps={}))
  self.snapshot['drawers']={level:self._drawer(level) for level in ('top','middle')}
  for op in CONTAINERS:self.snapshot['native_goal_relations'][op]=self._container(op,s)
  plate=self.point(s,'plate','K2');dest=self.point(s,'table_front_placement','K3') or self._history_point('episode_start','table_front_placement','K3')
  self.snapshot['native_goal_relations']['push_plate']=None if plate is None or dest is None else bool(distance(plate,dest)<=14 and self.stable('plate'))
  self.snapshot['native_goal_relations']['open_middle']=self.snapshot['drawers']['middle']['open']
  self.snapshot['native_goal_relations']['turn_on_stove']=None
  if previous and previous['operation'] in CONTAINERS:
   complete=self.snapshot['native_goal_relations'][previous['operation']] is True
   if candidate and not complete:
    self.events=self.events[:before];self.active=previous;candidate=None
   if complete and candidate is None:
    candidate=self._event(previous,frame,'rgbd_container_relation_and_observed_release');self.events.append(candidate);self.active=None
  if previous and previous['operation'] in NEW_OPS:
   op=previous['operation'];complete=False
   if op.startswith('close_'):complete=self.snapshot['drawers']['top' if op.endswith('top') else 'middle']['closed_confirmed'] is True
   elif op.startswith('open_'):
    level='top' if op.endswith('top') else 'middle';recent=[r['drawer_gaps'].get(level) for r in self.ext_rows]
    complete=len(recent)>=4 and all(x is not None and x>=.145 for x in recent[-4:]) and self.ext_rows[-1]['frame']-self.ext_rows[-4]['frame']>=9
    if op=='open_middle':complete=complete and distance(self.point(s,'middle_handle','K1'),s['eef_yx'])>=12 and self.point(s,'middle_handle','K1') is not None
   elif op=='push_plate':complete=self.snapshot['native_goal_relations']['push_plate'] is True
   if complete:candidate=self._event(previous,frame,'observable_extended_predicate');self.events.append(candidate);self.active=None
   self.diagnostics.update(operation=op,status='completed' if complete else 'unknown' if (op=='turn_on_stove' or op.startswith(('open_','close_')) and self.snapshot['drawers']['top' if op.endswith('top') else 'middle']['open'] is None) else 'in_progress',reason='rgbd_drawer_gap_or_fresh_plate_region')
  self.diagnostics['observable_geometry']=self.geometry;self.diagnostics['drawer_estimates']=self.snapshot['drawers']
  # P0 receives exactly the same sensor facts/Agent prompt as P1/P2; only selected-stage completion is Oracle-controlled.
  if self.arm=='P0':
   self.events=self.events[:before];self.active=previous;return None
  if self.arm=='P2' and previous and not self.final_stage:
   needs_semantics=previous['operation'] in CONTAINERS|NEW_OPS
   semantic_candidate=candidate is not None and needs_semantics
   trigger=(semantic_candidate or frame-(self.entered or 0)>=120) and frame-self.last_verify>=60
   eligible=trigger and self.verifier is not None and self.verify_counts.get((previous['operation'],self.entered),0)<6
   if semantic_candidate:
    # P2 never silently falls back to unverified S1 after cooldown/call exhaustion.
    self.events=self.events[:before];self.active=previous;candidate=None
   if eligible:
    self.last_verify=frame;key=(previous['operation'],self.entered);self.verify_counts[key]=self.verify_counts.get(key,0)+1
    result=self.verifier.check(previous,self.entered,list(self.rgb_rows),s,self.history,self.diagnostics)
    if result['accepted']:
     self.events=self.events[:before];candidate=self._event(previous,frame,'s1_plus_visual_joint_acceptance');self.events.append(candidate);self.active=None

  return candidate
 def _event(self,stage,frame,reason):return dict(operation=stage['operation'],object=stage['object'],outcome='completed',reason=reason,entered_step=self.entered,confirmed_step=frame,source='observable_extended_v1')
 def select(self,stage):
  if self.active:raise ValueError('Cannot replace unfinished stage')
  self.active=dict(stage);self.entered=self.last;self.stage_min_z=self.samples[-1]['eef_xyz'][2];self.confirm_counts={};self.stage_frame=copy.deepcopy(self.rgb_rows[-1]) if self.rgb_rows else None
