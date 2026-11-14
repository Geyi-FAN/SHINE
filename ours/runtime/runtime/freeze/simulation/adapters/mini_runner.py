"""Frozen paired mini evaluation; observation-only GT, never stage control."""
import argparse,gzip,hashlib,json,time,traceback
from pathlib import Path
import numpy as np
from PIL import Image
from common import write_json,sha256
from schema import ROOT as DATA,WORK
from sim_runtime import GeometryRuntime,new_env,restore,capture,identity,benchmark,get_libero_path
from eval_inputs import build_inputs,resize
from common import write_json,sha256
from revision_eval.events import RevisionEvents
from revision_eval.metrics import hold_frame_ok
from openpi_client.websocket_client_policy import WebsocketClientPolicy

def path(p):
 return Path(str(p).replace('/mnt/disk_2/geyi',str(WORK),1))

from restore_metrics import gates,order_errors

def run(c,client,variant,out,protocol_id,override=None,video_enabled=True):
 cid=c['case_id'];r=dict(case_id=cid,group=c['group'],variant=variant,protocol_id=protocol_id,training_overlap=c['training_overlap'],
   restore_required=bool(c.get('restore_object')),native_success=False,sgs=False,complete=False,policy_actions=0,hold_steps=0,restore25=False,restore35=False,withdraw=False,
   oracle_stage_management=False,reset_after_policy_start=False,state_writes_after_policy_start=False,
   budget=c['budget'] if override is None else override,diagnostic_budget_override=override,status='started')
 env=None;video=None;trace=[];actions=[];chunks=[];queue=[];started=time.monotonic();events=None
 try:
  normal=c['kind']=='normal';new=c['kind']=='new_revision';rt=GeometryRuntime()
  if normal:
   suite=benchmark.get_benchmark_dict()[c['suite']]();t=suite.get_task(c['task_id']);bddl=Path(get_libero_path('bddl_files'))/t.problem_folder/t.bddl_file
  elif new:bddl=path(c['bddl_file'])
  else:
   t=rt.suite.get_task(c['source_task']);bddl=Path(get_libero_path('bddl_files'))/t.problem_folder/t.bddl_file
  env=new_env(bddl);cp=path(c['context_file'] if normal or new else c['snapshot_file']);context=dict(np.load(cp));obs=restore(env,context)
  r['context_sha256']=sha256(cp);r['start_state_identity']=identity(capture(env))
  if normal or new:
   audit=json.loads((DATA/'mini/context_audits'/(cid+'.json')).read_text())
   assert r['context_sha256']==audit['context_sha256']
   assert r['start_state_identity']==audit['context_identity']
  if not normal and not new:
   expected=json.loads(cp.with_suffix('.json').read_text())['context_identity'];assert r['start_state_identity']==expected
   initial=dict(np.load(path(c['initial_state_file'])));reference=resize(initial['main_raw_image'][::-1,::-1])
  else:
   reference=resize(np.asarray(Image.open(path(c['reference_image'])).convert('RGB')))
  r['initial_reference_sha256']=hashlib.sha256(reference.tobytes()).hexdigest()
  if not normal:
   source=rt.monitor(env,c['source_task']);target=rt.monitor(env,c['target_task']);at=source.measure()
   if not new:events=RevisionEvents(c['contract'],{},at,c['target_task'],c['instruction'])
  if video_enabled:
   import imageio
   video=imageio.get_writer(str(out/(cid+'.mp4')),fps=10,macro_block_size=16)
  def forbidden(*args,**kwargs):raise RuntimeError('No state/reset writes during evaluated policy rollout')
  for name in ('reset','set_init_state','set_state','regenerate_obs_from_state'):
   if hasattr(env,name):setattr(env,name,forbidden)
  stable=0;call=0;last_grip=-1.;streak25=streak35=withdraw_streak=0;errors=set();restored_active=False
  def measure(step,phase):
   nonlocal streak25,streak35,withdraw_streak,restored_active
   if normal:
    goal=bool(env.env._check_success());frame=dict(goal=goal,stable=goal,no_robot_contact=True)
    trace.append(dict(step=step,phase=phase,goal_frame=frame));return frame
   sm=source.measure();tm=target.measure();frame=rt.frame(target,c['target_task'])
   if events:events.update(step,sm,tm,env.env._eval_predicate)
   row=dict(step=step,phase=phase,source=sm,target=tm,goal_frame=frame)
   if c.get('restore_object'):
    ref=np.asarray(c['initial_xyz'][c['restore_object']]);g25=gates(sm,ref,.025);g35=gates(sm,ref,.035)
    streak25=streak25+1 if all(g25.values()) else 0;streak35=streak35+1 if all(g35.values()) else 0
    withdraw=all(g35.values()) and np.linalg.norm(np.asarray(sm['eef_position'])-sm['object_position'])>=.08
    withdraw_streak=withdraw_streak+1 if withdraw else 0
    r['restore25'] |= streak25>=5;r['restore35'] |= streak35>=5;r['withdraw'] |= withdraw_streak>=5
    row.update(restore_gates25=g25,restore_error_m=float(np.linalg.norm(np.asarray(sm['object_position'])-ref)))
    if new:
     if restored_active and not g35['position']:errors.add('restored_object_moved_again')
     restored_active |= r['restore35']
     errors.update(order_errors(frame['goal'],r['restore25'],r['withdraw']))
   trace.append(row);return frame
  def step(action,phase,number):
   nonlocal obs
   obs,_,_,_=env.step(np.asarray(action).tolist());actions.append(dict(phase=phase,action=np.asarray(action).tolist()))
   if video and number%2==0:video.append_data(np.concatenate([obs['agentview_image'][::-1,::-1],obs['robot0_eye_in_hand_image'][::-1,::-1]],axis=1))
   return measure(number,phase)
  for i in range(r['budget']):
   if not queue:
    measurement=None if normal else source.measure()
    req=build_inputs(c,variant,obs,reference,measurement,context.get('frozen_observation_state') if call==0 else None)
    req.update(evaluation_case_id=cid,evaluation_call_index=call)
    if call==0:
     req['evaluation_seed']=c['policy_seed'];h=hashlib.sha256()
     for k in ('observation/image','observation/wrist_image','observation/state'):h.update(np.ascontiguousarray(req[k]).tobytes())
     h.update(c['instruction'].encode());r['first_common_input_sha256']=h.hexdigest()
    ans=client.infer(req);assert ans['evaluation_call_index']==call
    if variant in 'BD':assert ans['provided_initial_reference_sha256']==r['initial_reference_sha256']
    raw=np.asarray(ans['actions'],float);assert raw.shape==(10,7) and np.isfinite(raw).all()
    execution=np.clip(raw[:3],-1.,1.);execution[:,6]=np.where(execution[:,6]>0,1.,-1.)
    chunks.append(dict(step=i,call=call,prompt=req['prompt'],raw_actions=raw.tolist()));queue=list(execution);call+=1
   a=queue.pop(0);last_grip=a[6];frame=step(a,'policy',i+1);r['policy_actions']=i+1
   r['native_success'] |= frame['goal'];stable=stable+1 if frame['stable'] else 0
   if stable>=5:break
  if stable>=5:
   survived=True
   for h in range(40):
    frame=step([0,0,0,0,0,0,last_grip],'hold',r['policy_actions']+h+1);r['hold_steps']+=1
    ok=frame['goal'] if normal else hold_frame_ok(frame,c['target_task']) and (c['target_task'] not in (0,7) or frame['no_robot_contact'])
    survived=survived and ok
   r['sgs']=bool(survived and frame['stable'])
  if events:
   r['instruction_compliance']=events.result();r['complete']=r['sgs'] and events.result()['passed']
  elif new:
   if not r['restore25']:errors.add('restore25_event_missing')
   if not r['withdraw']:errors.add('withdraw_event_missing')
   r['instruction_compliance']=dict(passed=not errors,reasons=sorted(errors));r['complete']=r['sgs'] and not errors
  else:r['complete']=r['sgs']
  r['status']='success' if r['complete'] else 'contract_or_hold_failed' if stable>=5 else 'budget_exhausted'
 except Exception:r.update(status='runtime_error',error=traceback.format_exc())
 finally:
  r['seconds']=time.monotonic()-started;r['trace_path']=str(out/(cid+'.trace.json.gz'));r['video_path']=str(out/(cid+'.mp4')) if video else None
  with gzip.open(r['trace_path'],'wt',compresslevel=3) as f:json.dump(dict(actions=actions,chunks=chunks,measurements=trace),f)
  if video:video.close()
  if env:env.close()
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--variant',required=True,choices=list('ABCD'));p.add_argument('--port',required=True,type=int);p.add_argument('--jobs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--budget',type=int);p.add_argument('--smoke',action='store_true');p.add_argument('--no-video',action='store_true');a=p.parse_args()
 from evaluation_identity import protocol_id as make_protocol_id
 protocol_id=make_protocol_id();client=WebsocketClientPolicy('127.0.0.1',a.port);meta=client.get_server_metadata();assert meta['model']==a.variant and meta['protocol_id']==protocol_id
 a.out.mkdir(parents=True,exist_ok=True)
 for c in json.loads(a.jobs.read_text()):
  override=6 if a.smoke and c['kind']!='normal' else a.budget
  dest=a.out/(c['case_id']+'.json')
  if dest.exists():
   old=json.loads(dest.read_text());assert old['server_metadata']==meta and old['diagnostic_budget_override']==override
   if old['status']=='runtime_error':raise RuntimeError('Existing runtime error; use new output directory after fixing')
   continue
  result=run(c,client,a.variant,a.out,protocol_id,override,not a.no_video);result['server_metadata']=meta;result['smoke_only']=a.smoke;write_json(dest,result);print(c['case_id'],result['status'],flush=True)
  if result['status']=='runtime_error':raise RuntimeError(result['error'])
if __name__=='__main__':main()
