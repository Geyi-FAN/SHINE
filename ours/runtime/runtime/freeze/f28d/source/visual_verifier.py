"""Causal visual verification with fixed historical and stage-start references.
No benchmark, simulator object state or scoring-contract imports.
"""
import json,time,base64,urllib.request,io,os
from pathlib import Path
import numpy as np
from PIL import Image
from agent_transport import ProviderUnavailable
from local_transport import connection, verifier_request_json as request_json
class VisualVerifier:
 def __init__(self,folder):
  self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.calls=[];self.context={}
  self.cfg,self.key=connection('verifier')
  self.variant=os.environ.get('P2_REFINE_VARIANT','R1');self.prompt=Path(__file__).with_name('verifier_prompt_'+self.variant+'.txt').read_text()
 def configure(self,episode_main,takeover_main,takeover_wrist,user_message):
  self.context=dict(episode_main=np.array(episode_main),takeover_main=np.array(takeover_main),takeover_wrist=np.array(takeover_wrist),user_message=user_message)
 def check(self,stage,entered,rows,sensor,history,diagnostics):
  eligible=[r for r in rows if r['frame']>=entered];selected=eligible[-4:] if self.variant in ('R6','R7','R8','R9','R10','R11') else eligible[-3:];startrow=eligible[0] if eligible else None
  keyrow=None
  if self.variant in ('R2','R3') and len(eligible)>3:
   if stage['kind']=='grasp':keyrow=min(eligible,key=lambda r:r.get('sensor',{}).get('eef_xyz',[0,0,999])[2])
   elif stage['kind'] in ('return','release'):
    closed=[r for r in eligible if r.get('sensor',{}).get('width',.1)<.060];keyrow=closed[-1] if closed else None
  item=dict(operation=stage['operation'],entered=entered,frame=sensor['frame'],variant=self.variant,accepted=False,required=['object_identity','goal_relation','temporal_stability']);i=len(self.calls)
  if stage['kind'] in ('return','release') or stage['operation'] in ('cheese_bowl','bowl_drawer','bowl_stove','bowl_plate','bowl_cabinet','bottle_cabinet','bottle_rack'):item['required'].append('release')
  if stage['operation'].endswith('_clear') or stage['operation']=='open_middle':item['required'].append('disengagement')
  ref=stage.get('reference')
  if self.variant in ('R9','R10','R11'):
   catalog=json.loads(Path(__file__).with_name('operators.json').read_text());ref=catalog[stage['operation']]['reference'];stage=dict(stage,reference=ref)
  entities={stage['object'],ref['entity'] if ref else stage['object']}
  if 'drawer' in stage['object']:entities.update(['top_handle','middle_handle'])
  def describe(r):
   result=dict(frame=r['frame'],depth_WORLD_xyz_m={k:v for k,v in r['geometry'].items() if k.split('.')[0] in entities},robot_proprioception=r.get('sensor'))
   if self.variant in ('R9','R10','R11'):
    valid=[p for p in r.get('image_points',[]) if p['entity'] in entities and p.get('frame',r['frame'])==r['frame']]
    result['fresh_MAIN224_yx_points']=[dict(entity=p['entity'],keypoint=p['keypoint'],yx_px=p['yx224'],detection_confidence=p['det_confidence'],keypoint_confidence=p['keypoint_confidence']) for p in valid]
    if stage['operation'].startswith(('close_','open_')):
     from drawer_ray import estimate
     level='top' if stage['operation'].endswith('top') else 'middle';point=next((p for p in valid if p['entity']==level+'_handle' and p['keypoint']=='K1'),None)
     cal=json.loads(Path(os.environ['P012_DRAWER_CALIBRATION']).read_text());result['auxiliary_drawer_ray_estimate']=estimate(point,r.get('camera_calibration'),cal['closed_handles'].get(level))
   result['static_destination_depth_memory']={k:v for k,v in r.get('static_destination_geometry',{}).items() if k.split('.')[0] in entities}
   return result
  payload=dict(schema='causal_visual_verifier_v2',user_message=self.context.get('user_message'),selected_subgoal=stage,entered_step=entered,required_checks=item['required'],coordinate_systems=dict(MAIN224_yx_px='[row,column] in fixed MAIN224; never WRIST',WORLD_xyz_m='measured depth + calibrated camera extrinsics; meters; EEF uses same world axes'),recent_frames=[describe(r) for r in selected],stage_start=describe(startrow) if startrow else None,measured_hard_evidence=dict(holding=diagnostics.get('holding'),drawer_estimates=diagnostics.get('drawer_estimates')),historical_target_references=[dict(time_source=t,entity=e,keypoint=k,MAIN224_yx_px=p['yx224']) for (t,e,k),p in history.items() if ref and (t,e,k)==(ref['time_source'],ref['entity'],ref['keypoint'])])
  if self.variant in ('R2','R3'):
   h=diagnostics.get('holding',{});payload['measured_hard_evidence']=dict(gripper_width_m=sensor['width'],object_to_eef_MAIN_distance_px=h.get('near_px'),estimated_recent_image_comotion=h.get('co_motion'),note='co-motion is a fallible short-window heuristic; false or missing is not proof of a missed grasp; no held-object or drawer-state label is supplied')
   payload['action_reference_keyframe']=describe(keyrow) if keyrow else None
  if self.variant in ('R7','R8','R9','R10','R11'):
   estimates=payload.pop('measured_hard_evidence');drawers=estimates.get('drawer_estimates') or {};estimates['drawer_estimates']={level:{k:v for k,v in values.items() if v is not None} for level,values in drawers.items() if any(v is not None for v in values.values())};payload['s1_fallible_estimates']=estimates;payload['estimate_warning']='Unavailable fields omitted. These estimates are not measured object truth. Use images to resolve missing evidence; no missing estimate is a negative veto.'
  if self.variant=='R4':
   payload['s1_estimated_evidence_not_truth']=payload.pop('measured_hard_evidence');payload['s1_estimates_warning']='holding and drawer labels are fallible estimates, not measured object truth; unknown does not veto clear RGB evidence'
  if self.variant in ('R9','R10','R11'):
   payload['historical_landmark_points']=[dict(time_source=t,entity=e,keypoint=k,MAIN224_yx_px=p['yx224'],detection_confidence=p['det_confidence'],keypoint_confidence=p['keypoint_confidence'],role='historical reference only; never evidence of current completion') for (t,e,k),p in history.items() if e in entities and (self.variant!='R11' or stage['kind'] in ('return','release') and ref and t==ref['time_source'])]
  if stage['kind']=='grasp' and os.environ.get('REPAIR_GRASP_GUARD','0')=='1':
   from grasp_guard import grasp_motion
   measured=grasp_motion(eligible,stage,entered,sensor['frame'])
   payload['independent_rgbd_grasp_measurements']={k:v for k,v in measured.items() if k!='passed'}
   payload['independent_rgbd_measurement_warning']='Existing observed motion/quality measurements, not an Oracle state or completed-stage label. Preserve visual identity checks and independent acceptance guards.'
  contents=[dict(type='text',text=json.dumps(payload))];roles=[]
  def add(role,frame,main,wrist=None):
   im=Image.fromarray(np.concatenate([main,wrist],axis=1) if wrist is not None else main);b=io.BytesIO();im.save(b,format='JPEG',quality=85);name=f'{i}_{len(roles)}_{role}_{frame}.jpg';(self.folder/name).write_bytes(b.getvalue());roles.append(dict(role=role,frame=frame,file=name));contents.extend([dict(type='text',text=f'{role}, frame={frame}, '+('MAIN left; WRIST right' if wrist is not None else 'MAIN only')),dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+base64.b64encode(b.getvalue()).decode()))])
  if self.context.get('episode_main') is not None and (self.variant!='R11' or stage['kind']=='return'):add('EPISODE_START',-1,self.context['episode_main'])
  if stage['kind']=='release' and self.context.get('takeover_main') is not None:add('INSTRUCTION_TAKEOVER',0,self.context['takeover_main'],self.context['takeover_wrist'])
  if self.variant=='R3':
   # A reference marker denotes the historical destination, never the present object.
   if ref and ref['time_source'] in ('episode_start','instruction_takeover'):
    target=history.get((ref['time_source'],ref['entity'],ref['keypoint']))
    if target and self.context.get('episode_main') is not None:
     from PIL import ImageDraw
     marker=Image.fromarray(self.context['episode_main'].copy());draw=ImageDraw.Draw(marker);y,x=target['yx224'];draw.ellipse((x-4,y-4,x+4,y+4),outline='cyan',width=2);add('HISTORICAL_TARGET_CYAN_REFERENCE_ONLY',-1,np.asarray(marker))
   if stage['operation'].startswith(('open_','close_')) and self.context.get('episode_main') is not None and selected:
    # Fixed MAIN cabinet crop from the immutable initial image detector handles.
    h=[p['yx224'] for (t,e,k),p in history.items() if t=='episode_start' and e in ('top_handle','middle_handle') and k=='K1']
    if h:
     ys,xs=zip(*h);box=(max(0,int(min(xs))-24),max(0,int(min(ys))-40),min(224,int(max(xs))+40),min(224,int(max(ys))+55));add('EPISODE_CABINET_MAIN_CROP',-1,np.asarray(Image.fromarray(self.context['episode_main']).crop(box).resize((224,224))))
     for r in selected[-2:]:add('RECENT_CABINET_MAIN_CROP',r['frame'],np.asarray(Image.fromarray(r['main']).crop(box).resize((224,224))))
  if startrow:add('STAGE_START',startrow['frame'],startrow['main'],startrow['wrist'])
  if keyrow and keyrow is not startrow and keyrow['frame'] not in {z['frame'] for z in selected}:add('ACTION_REFERENCE',keyrow['frame'],keyrow['main'],keyrow['wrist'])
  for r in selected:add('RECENT',r['frame'],r['main'],r['wrist'])
  payload['image_roles']=roles;(self.folder/f'{i}_input.json').write_text(json.dumps(payload,indent=2));start=time.monotonic()
  try:
   prompt=self.prompt
   if self.variant in ('R10','R11'):
    rubrics=json.loads(Path(__file__).with_name('verifier_rubrics.json').read_text());kind='drawer' if stage['operation'].startswith(('close_','open_')) else stage['kind'] if stage['kind'] in ('grasp','return','release') else 'placement' if 'release' in item['required'] else 'push' if stage['operation']=='push_plate' else 'other';prompt=prompt.replace('<SELECTED_RUBRIC>',rubrics[kind])
   (self.folder/f'{i}_system.txt').write_text(prompt)
   body=dict(model=self.cfg['model'],messages=[dict(role='system',content=prompt),dict(role='user',content=contents)],enable_thinking=False,response_format=dict(type='json_object'),temperature=0,max_tokens=1000)
   req=urllib.request.Request(self.cfg['chat_url'],data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+self.key,'Content-Type':'application/json'})
   raw=request_json(req,timeout=90)
   pred=json.loads(raw['choices'][0]['message']['content']);item['response']=pred;item['usage']=raw.get('usage');checks=pred.get('checks',[]);frames={r['frame'] for r in selected};allframes={role['frame'] for role in roles}
   valid=bool(isinstance(checks,list) and all(set(c.get('evidence_frames',[]))<=allframes for c in checks))
   passed=all(any(c.get('condition')==name and c.get('verdict')=='pass' and set(c.get('evidence_frames',[]))&frames for c in checks) for name in item['required'])
   temporal=any(c.get('condition')=='temporal_stability' and len(set(c.get('evidence_frames',[]))&frames)>=2 for c in checks)
   guard=('release' not in item['required'] or (len(selected)>=2 and all(r.get('sensor',{}).get('width',0)>=.065 for r in selected[-2:])))
   if stage['kind']=='grasp':
    zs=[r['sensor']['eef_xyz'][2] for r in eligible if r.get('sensor')];lift=sensor['eef_xyz'][2]-min(zs) if zs else 0
    guard=guard and .002<=sensor['width']<.060 and lift>=.020
    item['measured_grasp_guard']=dict(width=sensor['width'],eef_lift_m=lift)
    if self.variant in ('R3','R4'):
     window=[r for r in eligible if sensor['frame']-r['frame']<=30 and r['geometry'].get(stage['object']+'.K1') is not None]
     if len(window)>=3 and window[-1]['frame']-window[0]['frame']>=6:
      origin=window[0];end=window[-1];delta=np.asarray(end['geometry'][stage['object']+'.K1'])-np.asarray(origin['geometry'][stage['object']+'.K1']);hand=np.asarray(end['sensor']['eef_xyz'])-np.asarray(origin['sensor']['eef_xyz']);movement=float(np.linalg.norm(delta));handmove=float(np.linalg.norm(hand));agreement=float(np.linalg.norm(delta-hand))
      # Repeated fresh stationary-object depth contradicts a claim of lifting that object.
      contradiction=(movement<.005 and handmove>=.008) if self.variant=='R3' else (movement<.005 or handmove<.008 or agreement>.030)
      guard=guard and not contradiction;item['measured_grasp_guard'].update(target_motion_m=movement,eef_motion_m=handmove,relative_motion_error_m=agreement,stationary_object_contradiction=contradiction)
   item['accepted']=bool(pred.get('status')=='completed' and valid and passed and temporal and guard and len(selected)>=3 and selected[-1]['frame']-selected[0]['frame']>=6)
   item.update(schema_valid=valid,physical_guard=bool(guard),temporal_evidence=temporal)
   if os.environ.get('REPAIR_GRASP_GUARD','0')=='1' and stage['kind']=='grasp':
    from grasp_guard import grasp_motion
    item['independent_grasp_motion']=grasp_motion(eligible,stage,entered,sensor['frame'])
    item['accepted']=item['accepted'] and item['independent_grasp_motion']['passed']
   if os.environ.get('REPAIR_CONTAINER_GUARD','0')=='1' and stage['operation'] in ('cheese_bowl','bowl_drawer'):
    from container_guard import container_consensus
    item['independent_container_guard']=container_consensus(selected,stage['operation'],sensor['frame'])
    item['accepted']=item['accepted'] and item['independent_container_guard']['passed']
   if os.environ.get('REPAIR_DRAWER_GUARD','0')=='1' and stage['operation'].startswith('close_'):
    item['visual_semantics_passed_before_geometry']=item['accepted']
    level='top' if stage['operation'].endswith('top') else 'middle'
    from drawer_ray import estimate
    cal=json.loads(Path(os.environ['P012_DRAWER_CALIBRATION']).read_text())
    observed=[]
    for row in selected:
     point=next((p for p in row.get('image_points',[]) if p['entity']==level+'_handle' and p['keypoint']=='K1'),None)
     est=estimate(point,row.get('camera_calibration'),cal['closed_handles'].get(level))
     if est is not None:observed.append(dict(frame=row['frame'],**est))
    from drawer_guard import closing_evidence
    item['independent_drawer_guard']=closing_evidence(selected,level,sensor['frame'],cal['closed_handles'][level],observed)
    item['accepted']=item['accepted'] and item['independent_drawer_guard']['passed']

  except ProviderUnavailable:
   raise
  except Exception as e:item['infrastructure_error']=type(e).__name__+': '+str(e)
  item['seconds']=time.monotonic()-start;self.calls.append(item)
  with (self.folder/'calls.jsonl').open('a') as f:f.write(json.dumps(item)+'\n')
  return item
