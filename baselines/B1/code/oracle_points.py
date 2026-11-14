"""Typed simulation coordinates; no reference plan or next-stage access.

K1 = visible segmentation centroid, K2 = object-root projection, K3 = named
placement reference using the already frozen YOLO-label geometry conventions.
Historical K2 is frozen at episode start / actual instruction takeover.
"""
import json,time,threading
from pathlib import Path
from types import SimpleNamespace
import numpy as np

BRIDGE=None
OBJECTS={'bowl':'akita_black_bowl_1','plate':'plate_1','cheese':'cream_cheese_1','wine_bottle':'wine_bottle_1'}
SITES={'stove_placement':'flat_stove_1_cook_region','cabinet_top_placement':'wooden_cabinet_1_top_side','top_drawer_interior':'wooden_cabinet_1_top_region','table_front_placement':'main_table_stove_front_region','wine_rack_placement':'wine_rack_1_top_region'}
RULE_FILE=Path('/mnt/disk_4/geyi/yolo_v3r_3000_20261024/destination_rules.json')

class Scene:
 def __init__(self,folder):
  self.frame=-1;self.path=folder/'memory_events.jsonl';self.enabled=True;self.transfer_enabled=False;self.cache={};self.anchors={};self.configuration={'mode':'Oracle typed references; no detector; no canonical plan'}
 def log(self,event,**kw):
  self.path.parent.mkdir(parents=True,exist_ok=True)
  with self.path.open('a') as f:f.write(json.dumps({'event':event,'wall_time':time.time(),**kw})+'\n')

class OraclePoints:
 def __init__(self,folder,episode_id=None,episode_frame_at_takeover=None):
  self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.episode_id=episode_id;self.episode_frame_at_takeover=episode_frame_at_takeover or 0;self.frame=None;self.memory={};self.current={};self.timings=[];self.scene=Scene(self.folder);self.camera_id='main256-to224-fixed-v1';self.history_camera={};self.instruction_version=0;self.required_reference=None;self.last_image_points={};self._mask_ids=None
 def _capture(self):
  if BRIDGE is None:raise RuntimeError('Oracle points must be bound to a live single-owner bridge')
  from sym_geometry import project
  env=BRIDGE.view if threading.current_thread()!=threading.main_thread() else BRIDGE.env
  sim=env.sim;core=env.env;rules=json.loads(RULE_FILE.read_text())['rules']
  if self._mask_ids is None:
   ids={k:[i for i,n in enumerate(sim.model.geom_names) if n and n.startswith(v+'_')] for k,v in OBJECTS.items()}
   for level in ['middle','top']:
    ids[level+'_handle']=[g for g in range(sim.model.ngeom) if int(sim.model.geom_dataid[g])>=0 and int(sim.model.geom_type[g])==7 and level+'_handle' in sim.model.mesh_id2name(int(sim.model.geom_dataid[g])) and sim.model.geom_group[g]==1]
   ji=sim.model.joint_name2id('flat_stove_1_button');bid=int(sim.model.jnt_bodyid[ji]);ids['stove_button']=[i for i in range(sim.model.ngeom) if int(sim.model.geom_bodyid[i])==bid and sim.model.geom_rgba[i,3]>=.99 and max(sim.model.geom_rgba[i,:3])<.35]
   self._mask_ids=ids
  seg=sim.render(width=256,height=256,camera_name='agentview',segmentation=True)[::-1,::-1];points=[]
  def add(e,k,yx,valid,definition):
   if valid and np.isfinite(yx).all() and np.all(np.asarray(yx)>=0) and np.all(np.asarray(yx)<=223):points.append({'entity':e,'keypoint':k,'yx224':np.asarray(yx,float).tolist(),'source':'oracle_geometry','definition':definition,'physics_step':BRIDGE.physics_steps})
  for e,ids in self._mask_ids.items():
   mask=np.isin(seg[:,:,1],ids)&(seg[:,:,0]==5);pixels=np.argwhere(mask)
   if len(pixels):add(e,'K1',(pixels.mean(0)+.5)*.875-.5,True,'visible_segmentation_centroid')
  for e,name in OBJECTS.items():
   bid=sim.model.body_name2id(core.objects_dict[name].root_body);pos=np.asarray(sim.data.body_xpos[bid]).copy();yx,v=project(sim,pos);add(e,'K2',yx,v,'object_root_projection')
   if e in ['bowl','plate']:
    pos+=np.asarray(sim.data.body_xmat[bid]).reshape(3,3)@np.array([0,0,.03 if e=='bowl' else .005]);yx,v=project(sim,pos);add(e,'K3',yx,v,'semantic_inner_reference')
  for e,site in SITES.items():
   if e=='top_drawer_interior' and not core._eval_predicate(['open','wooden_cabinet_1_top_region']):continue
   pos=np.asarray(sim.data.site_xpos[sim.model.site_name2id(site)]).copy();definition='named_site_center:'+site
   if e in rules:
    rule=rules[e];bid=sim.model.body_name2id(rule['fixture']+'_main');pos=np.asarray(sim.data.body_xpos[bid])+np.asarray(sim.data.body_xmat[bid]).reshape(3,3)@np.asarray(rule['local_xyz']);definition='frozen_destination_rule:'+e
   yx,v=project(sim,pos);add(e,'K3',yx,v,definition)
  return points
 def observe(self,image,frame,time_source='current',camera_id=None):
  start=time.monotonic();rows=self._capture();self.timings.append(time.monotonic()-start)
  values={(time_source,p['entity'],p['keypoint']):dict(p,time_source=time_source,frame=frame,source_episode_frame=BRIDGE.physics_steps) for p in rows}
  if time_source=='current':self.current=values;self.frame=frame;self.scene.frame=frame
  else:self.memory.update(values);self.history_camera[time_source]=camera_id or self.camera_id
  self.scene.log('oracle_points',time_source=time_source,frame=frame,physics_step=BRIDGE.physics_steps,count=len(rows),seconds=self.timings[-1],point_source='oracle_geometry')
 def update_evidence(self,frame,facts,camera_id):self.scene.frame=max(self.scene.frame,frame);self.camera_id=camera_id
 def initialize_episode(self,image,facts,camera_id):
  if 'episode_start' in self.history_camera:raise ValueError('episode memory initialized twice')
  self.camera_id=camera_id;self.observe(image,-1,'episode_start',camera_id);self.scene.frame=0
 def begin_instruction(self,image,frame):
  self.memory={k:v for k,v in self.memory.items() if k[0]!='instruction_takeover'};self.history_camera.pop('instruction_takeover',None);self.instruction_version+=1;self.observe(image,frame,'instruction_takeover');self.scene.frame=frame
 def transfer_episode_objects(self,*args,**kw):pass
 def resolve(self,t,e,k):
  if t=='current':return self.current.get((t,e,k)),'oracle_current'
  if self.history_camera.get(t)!=self.camera_id:return None,'camera_version_mismatch'
  return self.memory.get((t,e,k)),'oracle_historical'
 def available(self,catalog):
  refs={tuple(o['reference'][k] for k in ['time_source','entity','keypoint']) for o in catalog.values() if o['reference']}
  return [dict(time_source=t,entity=e,keypoint=k,available=self.resolve(t,e,k)[0] is not None) for t,e,k in sorted(refs)]
 def bind(self,decision,frame):
  ref=decision['reference'];text=decision['policy_prompt_template'];self.required_reference=ref
  if ref is None:return text,{'source':'no_point_operator','valid':False,'yx':None,'reference':None}
  key=tuple(ref[k] for k in ['time_source','entity','keypoint']);p,resolution=self.resolve(*key)
  if p is None:raise ValueError('Oracle reference unavailable: '+json.dumps(ref))
  yx=np.rint(p['yx224']).astype(int).tolist();text=text.replace('{'+'.'.join(key)+'}','<'+','.join(map(str,yx))+'>')
  if '{' in text or '}' in text:raise ValueError('Unbound symbolic reference')
  marker={'source':'oracle_geometry','valid':False,'yx':yx,'reference':ref,'resolution':resolution,'source_frame':p['frame'],'source_physics_step':p['physics_step'],'camera_transform_id':self.camera_id,'definition':p['definition']};self.scene.log('bind',**marker);return text,marker
 def close(self):pass
