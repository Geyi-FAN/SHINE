"""Non-reset Switch runner with canonical observation boundary and frozen v2.5 scorer.
Policy factory: module:function returning an object with infer(request)->{'actions':H x 7}.
A declared model/method supplies its own planner; this runner's default is full instruction.
"""
import argparse,gzip,importlib,json,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np,h5py
import common
from sim_state import capture,restore,identity
from observation_boundary import request,save_views,PROFILES,pixel_difference,negligible_raster_difference,VERSION as OBS_VERSION
from protocol import StopController,evidence,evaluate_episode,load_rules
from compile_contracts import digest
B=Path(__file__).resolve().parents[1]
def run(case,contract,client,out,profile,execute_steps=3,smoke_budget=None,method='canonical',record_video=True):
 assert digest(contract)==case['contract_sha256'],'Scoring contract fingerprint mismatch'
 assert case['current_instruction']==contract['canonical_instruction_en']==contract['model_prompt_contract']['task'],'Instruction/contract mismatch'
 assert case['stop_policy']==contract['stop_policy']
 assert method in ('canonical','e3_oracle')
 assert method!='e3_oracle' or profile in ('smolvla_e3_training_256','smolvla_switch_256','pi05_libero_224')
 assert case['observation_protocol']==OBS_VERSION,'Observation protocol mismatch'
 metadata_method=getattr(client,'metadata',None) or getattr(client,'get_server_metadata',None)
 policy_metadata=metadata_method() if callable(metadata_method) else {}
 common.ROOT=out/'runtime_cache';common.setup()
 from revision_eval.env import make_libero_env
 from revision_eval.render_context import bind_render_context
 rt=common.suite_runtime();env=None;video=None;actions=[];measurements=[];chunks=[];initial=None;stop='budget_exhausted';started=time.monotonic()
 assert not (out/'result.json').exists(),'Refuse to overwrite results'
 out.mkdir(parents=True,exist_ok=True)
 try:
  env=bind_render_context(make_libero_env(rt.suite.get_task(case['source_task']),SimpleNamespace(env_img_res=256,seed=7,control_mode='relative'))[0]);env.env.ignore_done=True;env.env.horizon=10000
  obs=restore(env,dict(np.load(B/case['initial_state_file'])))
  if hasattr(client,'reset'):client.reset()
  if hasattr(client,'begin_source_episode'):
   client.begin_source_episode(request(obs,case['previous_instruction'],profile))
  with h5py.File(B/case['source_prefix_file']) as f:prefix=f['actions'][:case['fixed_switch_step']]
  assert len(prefix)==case['fixed_switch_step']
  for source_step,action in enumerate(prefix,1):
   obs,_,_,_=env.step(action.tolist())
   if hasattr(client,'observe_source'):
    # Only past/current observations, previous instruction and executed action;
    # never simulator state, future actions, phase labels or scoring references.
    client.observe_source(request(obs,case['previous_instruction'],profile),source_step,action.copy())
  meta=json.loads((B/'snapshots'/f"{case['snapshot_id']}.json").read_text());assert identity(capture(env))==meta['context_identity']
  source=rt.monitor(env,case['source_task']);target=rt.monitor(env,case['target_task']);initial=dict(articulation=source.measure()['articulation'],native_goal=bool(rt.frame(target,case['target_task'])['goal']));assert not initial['native_goal']
  def forbidden(*args,**kwargs):raise RuntimeError('No reset/state write allowed after switch')
  for name in ['reset','set_init_state','set_state','regenerate_obs_from_state']:
   if hasattr(env,name):setattr(env,name,forbidden)
  expected=json.loads((B/case['observation_record']).read_text());actual=save_views(obs,out/'first_policy_input',dict(profile=profile,case_id=case['case_id']))
  assert expected['version']==actual['version']==OBS_VERSION,'Review image protocol is stale'
  from PIL import Image
  differences={}
  for p in PROFILES:
   for view in ['main','wrist']:
    name=p+'_'+view+'.png'
    d=pixel_difference(np.asarray(Image.open(out/'first_policy_input'/name)),np.asarray(Image.open(B/'observations'/case['snapshot_id']/name)))
    differences[p+'_'+view]=d
    assert negligible_raster_difference(d),('First policy image materially differs from review image',name,d)
  actual['review_comparison']=differences
  common.write(out/'first_policy_input/views.json',actual)
  adapter=None;method_calls=[]
  if method=='e3_oracle':
   from e3_adapter import E3Adapter
   adapter=E3Adapter(env,case,obs,source.measure(),initial['native_goal'])
  if record_video:
   import imageio.v2 as imageio
   video=imageio.get_writer(str(out/'policy.mp4'),fps=20,codec='libx264',quality=7,macro_block_size=16,ffmpeg_params=['-threads','1'])
   from observation_boundary import camera
   video.append_data(np.concatenate([camera(obs['agentview_image'],profile),camera(obs['robot0_eye_in_hand_image'],profile)],axis=1))
  queue=[];ctrl=StopController(case,contract);budget=smoke_budget or case['budget'];call=0
  for step in range(1,budget+1):
   if not queue:
    req=request(obs,case['current_instruction'],profile);req['evaluation_case_id']=case['case_id'];req['evaluation_call_index']=call
    if adapter:
     req['prompt'],diagnostic=adapter.prompt();method_calls.append(dict(step=step-1,**diagnostic))
    if call==0:req['evaluation_seed']=case['policy_seed']
    ans=client.infer(req);raw=np.asarray(ans['actions'],float)
    assert raw.ndim==2 and raw.shape[1]==7 and len(raw)>0 and np.isfinite(raw).all()
    chunk=np.clip(raw[:execute_steps],-1,1);chunk[:,6]=np.where(chunk[:,6]>0,1.,-1.);queue=list(chunk);chunks.append(dict(call=call,step=step-1,prompt=req['prompt'],raw_actions=raw.tolist()));call+=1
   act=queue.pop(0);obs,_,_,_=env.step(act.tolist());actions.append(dict(phase='policy',action=act.tolist()))
   if video:video.append_data(np.concatenate([camera(obs['agentview_image'],profile),camera(obs['robot0_eye_in_hand_image'],profile)],axis=1))
   row=dict(step=step,phase='policy',source=source.measure(),target=target.measure(),goal_frame=rt.frame(target,case['target_task']),metric_evidence=evidence(env,case,contract));measurements.append(row)
   reason=('helper_plan_completed' if adapter.advance(obs,row['source'],bool(row['goal_frame']['goal']),step,queue) else None) if adapter else ctrl.observe(row)
   if reason:stop=reason;break
  if video:video.close();video=None
  trace=dict(actions=actions,chunks=chunks,measurements=measurements,metric_initial=initial)
  if adapter:trace.update(symbolic_calls=method_calls,stage_events=adapter.online.controller.events,completion_diagnostics=adapter.online.controller.completion_diagnostics)
  score=evaluate_episode(trace,case,contract,load_rules())
  result=dict(case_id=case['case_id'],status='completed',smoke_only=smoke_budget is not None,policy_label=getattr(client,'label',type(client).__name__),observation_profile=profile,observation_protocol=OBS_VERSION,instruction_protocol=case['instruction_protocol'],execute_steps=execute_steps,budget=budget,stop_reason=stop,stop_policy=case['stop_policy'],metrics=score,policy_actions=len(actions),seconds=time.monotonic()-started,method=method,benchmark_id=case['benchmark_id'],evaluation_split=case['evaluation_split'],case_contract_sha256=case['contract_sha256'],execution_protocol='agent_aligned_v4_pi05_616_20261029' if adapter else 'canonical_stop_controller',privileged_inputs=bool(adapter))
  result['prompt_order']='task_subgoal_coordinates' if adapter else 'full_task_only'
  result['video']={'file':'policy.mp4','fps':20,'views':['main','wrist'],'initial_frame_then_every_policy_step':True}
  result['source_history_hooks']={'initial_observation':hasattr(client,'begin_source_episode'),'past_observations_and_actions':hasattr(client,'observe_source')}
  result['policy_metadata']=policy_metadata
  with gzip.open(out/'trace.json.gz','wt') as f:json.dump(trace,f,default=common.json_default)
  common.write(out/'result.json',result);return result
 finally:
  if video:video.close()
  if env is not None:env.close()
class SmokePolicy:
 label='dummy_environment_smoke_not_model_baseline'
 def infer(self,request):return {'actions':np.tile([0,0,0,0,0,0,-1.],(4,1))}
def main():
 p=argparse.ArgumentParser();p.add_argument('--case-id',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--profile',choices=list(PROFILES),default=None);p.add_argument('--method',choices=['canonical','e3_oracle'],default='canonical');p.add_argument('--policy-factory');p.add_argument('--smoke-budget',type=int);a=p.parse_args()
 cases={c['case_id']:c for prefix in ['', 'memory_'] for c in map(json.loads,(B/(prefix+'cases.jsonl')).read_text().splitlines())};cts={c['case_id']:c for prefix in ['', 'memory_'] for c in json.loads((B/(prefix+'contracts.json')).read_text())}
 a.profile=a.profile or ('smolvla_e3_training_256' if a.method=='e3_oracle' else 'pi05_libero_224')
 if a.smoke_budget:
  client=SmokePolicy()
 else:
  if not a.policy_factory:p.error('A real policy factory is required; dummy is smoke-only')
  module,func=a.policy_factory.split(':');client=getattr(importlib.import_module(module),func)()
 result=run(cases[a.case_id],cts[a.case_id],client,a.out,a.profile,smoke_budget=a.smoke_budget,method=a.method);print(json.dumps(result,ensure_ascii=False,default=common.json_default))
if __name__=='__main__':main()
