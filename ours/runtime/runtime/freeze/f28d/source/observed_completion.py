"""S1: causal MAIN image keypoints + measured proprioception only.

No simulator/environment/Oracle imports. No cached CURRENT detections may be
passed here. Historical coordinates are target references, never evidence of
present completion. Camera projection is supplied by a calibrated sensor adapter.
"""
from collections import deque
from dataclasses import dataclass,asdict
import numpy as np

OBJECTS=('bowl','cheese','wine_bottle','plate')
DESTINATIONS={'bowl_stove':('bowl','stove_placement'),'bowl_cabinet':('bowl','cabinet_top_placement'),
 'bowl_plate':('bowl','plate'),'cheese_bowl':('cheese','bowl'),
 'bottle_cabinet':('wine_bottle','cabinet_top_placement'),'bottle_rack':('wine_bottle','wine_rack_placement')}
@dataclass(frozen=True)
class Settings:
 confidence:float=.35
 open_width_m:float=.065
 closed_width_m:float=.060
 min_width_m:float=.002
 near_hand_px:float=26.
 bootstrap_near_px:float=14.
 bootstrap_displacement_px:float=5.
 lift_m:float=.020
 motion_m:float=.008
 motion_px:float=2.
 relative_motion_px:float=5.
 return_radius_px:float=6.
 place_radius_px:float=14.
 stable_radius_px:float=3.
 stable_steps:int=9
 minimum_frames:int=4
 hold_occlusion_steps:int=24
 clear_px:float=12.

def distance(a,b):
 return float(np.linalg.norm(np.asarray(a)-np.asarray(b))) if a is not None and b is not None else float('inf')

class ObservedCompletion:
 def __init__(self,history=None,settings=None):
  self.settings=settings or Settings()
  if not .1<=self.settings.confidence<=1:raise ValueError('S1 confidence must be in [0.1,1]')
  self.history=history or {};self.samples=deque(maxlen=16)
  self.events=[];self.active=None;self.entered=None;self.last=-1;self.held='unknown';self.last_held_frame=-10000
  self.snapshot={};self.diagnostics={};self.confirm_counts={};self.stage_min_z=None;self.released=False
  self.held_width=None;self.last_seen_width=None;self.holding_evidence={}
 def point(self,sample,entity,k='K2'):
  p=sample['points'].get((entity,k));return p['yx224'] if p is not None else None
 def _history_point(self,source,entity,k='K2'):
  p=self.history.get((source,entity,k))
  if p is None:return None
  if min(p.get('det_confidence',0),p.get('keypoint_confidence',0))<self.settings.confidence:return None
  return p['yx224']
 def _window(self,entity,k='K2'):
  c=self.settings;rows=list(self.samples);rows=[r for r in rows if r['frame']>=max(0,self.last-15)]
  # Only a continuous suffix of fresh detections counts as stable.
  good=[]
  for r in reversed(rows):
   if self.point(r,entity,k) is None:break
   good.append(r)
  return list(reversed(good))
 def stable(self,entity):
  w=self._window(entity);c=self.settings
  if len(w)<c.minimum_frames or w[-1]['frame']-w[0]['frame']<c.stable_steps:return False
  a=np.array([self.point(r,entity) for r in w]);return bool(np.max(np.linalg.norm(a-np.median(a,axis=0),axis=1))<=c.stable_radius_px)
 def _holding(self,s):
  c=self.settings;w=s['width'];near={};motion={}
  for e in OBJECTS:
   p=self.point(s,e,'K1');near[e]=distance(p,s['eef_yx'])
   rows=[r for r in self.samples if s['frame']-r['frame']<=18 and self.point(r,e,'K1') is not None]
   evidence=False
   if len(rows)>=3 and p is not None:
    old=rows[0];a=np.array(p)-np.array(self.point(old,e,'K1'));b=np.array(s['eef_yx'])-np.array(old['eef_yx']) if s['eef_yx'] is not None and old['eef_yx'] is not None else np.array([1e6,1e6])
    evidence=bool(np.linalg.norm(a)>=c.motion_px and np.linalg.norm(b)>=c.motion_px and np.linalg.norm(a-b)<=c.relative_motion_px and distance(s['eef_xyz'],old['eef_xyz'])>=c.motion_m)
   motion[e]=evidence
  closing=c.min_width_m<=w<c.closed_width_m
  candidates=[e for e in OBJECTS if closing and near[e]<=c.near_hand_px and motion[e]]
  if w>=c.open_width_m:
   self.held='none';self.held_width=None
  elif len(candidates)==1:
   self.held=candidates[0];self.last_held_frame=s['frame'];self.held_width=w
  elif len(candidates)>1:self.held='unknown'
  elif self.held in OBJECTS:
   # Opening relative to observed grasp width plus visual separation ends ownership.
   e=self.held;opening=self.held_width is not None and w-self.held_width>.012
   if near[e]>c.near_hand_px and opening:self.held='none'
   elif closing and near[e]<=c.near_hand_px:self.last_held_frame=s['frame']
   elif s['frame']-self.last_held_frame>c.hold_occlusion_steps:self.held='unknown'
  elif s['frame']==0 and closing:
   # A switch may start already carrying. This is an explicit RGB bootstrap
   # heuristic, NOT a simulator holding label; ambiguity stays unknown.
   displaced=[e for e in OBJECTS if near[e]<=c.bootstrap_near_px and self._history_point('episode_start',e) is not None and self.point(s,e) is not None and distance(self.point(s,e),self._history_point('episode_start',e))>=c.bootstrap_displacement_px]
   if len(displaced)==1:self.held=displaced[0];self.last_held_frame=s['frame'];self.held_width=w
  elif w<c.min_width_m:self.held='none'
  self.holding_evidence=dict(width_m=w,near_px={k:(v if np.isfinite(v) else None) for k,v in near.items()},co_motion=motion,held=self.held)
 def _released(self,s,obj):
  c=self.settings;rows=list(self.samples);width=s['width']
  # Open hand + stable object + hand separation are visual release proxies,
  # NOT claims of exact support/contact. Never infer support from missing pixels.
  return bool(s['eef_yx'] is not None and (width>=c.open_width_m or self.held in OBJECTS and self.held!=obj) and self.stable(obj) and distance(self.point(s,obj,'K1'),s['eef_yx'])>=c.clear_px and self.point(s,obj,'K1') is not None)
 def observe(self,frame,eef_xyz,gripper_qpos,eef_yx,points):
  if frame<=self.last:raise ValueError('S1 observations must be strictly causal')
  self.last=frame;c=self.settings;valid={}
  for p in points:
   xy=p.get('yx224');q=min(p.get('det_confidence',0),p.get('keypoint_confidence',0))
   if p.get('source')!='yolo_image_only':raise ValueError('Only fresh image YOLO detections accepted')
   if p.get('frame',frame)!=frame:raise ValueError('Cached point is not completion evidence')
   if q>=c.confidence and xy is not None and np.isfinite(xy).all() and np.all(np.asarray(xy)>=0) and np.all(np.asarray(xy)<=223):valid[(p['entity'],p['keypoint'])]=p
  s=dict(frame=frame,eef_xyz=list(eef_xyz),eef_yx=eef_yx,width=float(np.abs(gripper_qpos).sum()),points=valid)
  self.samples.append(s);self._holding(s)
  returned={};relations={};release={};errors={}
  for e in OBJECTS:
   release[e]=self._released(s,e);p=self.point(s,e);ref=self._history_point('episode_start',e)
   returned[e]=None if p is None or ref is None else bool(distance(p,ref)<=c.return_radius_px and release[e])
  for op,(obj,target) in DESTINATIONS.items():
   p=self.point(s,obj);dest=self.point(s,target,'K3')
   # Immutable facility anchors may supply a destination, never current object evidence.
   if dest is None and target.endswith('placement'):dest=self._history_point('episode_start',target,'K3')
   err=distance(p,dest);errors[op]=err if np.isfinite(err) else None
   relations[op]=None if p is None or dest is None else bool(err<=c.place_radius_px and release[obj])
  self.snapshot=dict(source='s1_rgb_proprio_estimates',observed_step=frame,held_object=self.held,
   objects={e:dict(robot_contact=None,supported=True if release[e] else None,bilateral_contact=None,returned_and_released=returned[e]) for e in OBJECTS},
   drawers={k:dict(open=None,closed_current=None,closed_confirmed=None) for k in ('top','middle')},native_goal_relations=relations)
  status='idle';complete=False;reason=None
  if self.active:
   op=self.active;obj=op['object'];kind=op['kind'];status='in_progress'
   if kind=='grasp':
    self.stage_min_z=min(self.stage_min_z,s['eef_xyz'][2]);lift=s['eef_xyz'][2]-self.stage_min_z
    confirmed=self.held==obj and self.holding_evidence['co_motion'].get(obj,False) and lift>=c.lift_m
    self.confirm_counts[obj]=self.confirm_counts.get(obj,0)+1 if confirmed else 0
    complete=self.confirm_counts[obj]>=2;reason='closed_gripper_target_comotion_and_lift'
    if self.point(s,obj,'K1') is None:status='unknown'
   elif kind in ('return','release'):
    t='episode_start' if kind=='return' else 'instruction_takeover';p=self.point(s,obj);ref=self._history_point(t,obj)
    complete=p is not None and ref is not None and distance(p,ref)<=c.return_radius_px and release[obj]
    if p is None or ref is None:status='unknown'
    reason='reference_match_open_gripper_fresh_static_object_and_separation'
   elif op['operation'] in DESTINATIONS:
    complete=relations[op['operation']] is True
    if relations[op['operation']] is None:status='unknown'
    reason='destination_proximity_open_gripper_fresh_static_object_and_separation'
   else:raise ValueError('Unsupported S1 operation '+op['operation'])
  self.diagnostics=dict(frame=frame,status='completed' if complete else status,operation=None if self.active is None else self.active['operation'],holding=self.holding_evidence,returned=returned,release=release,relations=relations,destination_error_px=errors,reason=reason)
  if complete:
   event=dict(operation=self.active['operation'],object=self.active['object'],outcome='completed',reason=reason,entered_step=self.entered,confirmed_step=frame,source='s1_rgb_proprio_v1')
   self.events.append(event);self.active=None;return event
  return None
 def select(self,stage):
  if self.active:raise ValueError('Cannot replace unfinished S1 stage')
  if stage['kind'] not in ('grasp','return','release') and stage['operation'] not in DESTINATIONS:raise ValueError('Unsupported S1 operation')
  self.active=dict(stage);self.entered=self.last;self.stage_min_z=self.samples[-1]['eef_xyz'][2];self.confirm_counts={}
