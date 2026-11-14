import argparse,copy,gzip,hashlib,http.client,io,json,os,sys,time,traceback
from pathlib import Path
from bootstrap import B,configure

def main():
 p=argparse.ArgumentParser();p.add_argument('--case-id',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=19869);p.add_argument('--gpu',type=int,default=4);p.add_argument('--pause-probe',action='store_true');p.add_argument('--pause-role',default='planning');p.add_argument('--control-budget',type=int,default=1200);p.add_argument('--natural-source',action='store_true');a=p.parse_args()
 if a.out.exists():raise SystemExit('Preserve prior attempt; choose a new output directory')
 a.out.mkdir(parents=True);(a.out/'logs').mkdir()
 core,runner,authority=configure(a.out,a.gpu)
 from sim_runtime import GeometryRuntime,new_env,get_libero_path
 from grounding import inventory_from_names
 from bridge import SingleOwnerBridge
 from policy_backend import SmolHTTPClient
 from response_memo import fingerprint
 import numpy as np
 implementation_sha256={str(f.relative_to(B)):hashlib.sha256(f.read_bytes()).hexdigest()for folder in ['g2','g21']for f in(B/folder).glob('*.py')}
 case=next(c for c in json.loads((B/'g2/fixed32.json').read_text())if c['case_id']==a.case_id)
 case['authority_resource_root']=str(Path(case['snapshot_file']).parent.parent)
 os.environ['HYBRID_POLICY_NAMESPACE']='G2_v1:'+a.out.parent.name
 class Client(SmolHTTPClient):
  def infer(self,request):
   response=super().infer(request);response.update(paired_request_sha256=fingerprint(request),paired_response_memo_hit=False,paired_action_sha256=fingerprint(np.asarray(response['actions'],np.float32)));return response
 client=Client(port=a.port);metadata=client.get_server_metadata()
 assert metadata['weights_sha256']=='30a620085ba28b8faec160ae68a9276d705ec0fb6d2fc9237e706379d0c5eebc';assert metadata['normalization_sha256']=='d4e03a22ef5d89a910e32c233a509465ad0d265381a06745917d69fd8924a635'
 (a.out/'policy_metadata.json').write_text(json.dumps(metadata,indent=2))
 rt=GeometryRuntime();task=rt.suite.get_task(case['source_task']);env=new_env(Path(get_libero_path('bddl_files'))/task.problem_folder/task.bddl_file)
 context=dict(np.load(case['initial_state_file']if a.natural_source else case['snapshot_file']))
 if a.natural_source:
  obs=authority.state.restore(env,context);actual=authority.state.capture(env)
  for key in ('body_pos','body_quat','state'):
   expected=np.asarray(context[key])[1:]if key=='state'else np.asarray(context[key]);value=np.asarray(actual[key])[1:]if key=='state'else np.asarray(actual[key]);assert np.array_equal(np.round(value,8),np.round(expected,8)),key
  (a.out/'initial_context_check.json').write_text(json.dumps(dict(source=str(case['initial_state_file']),state8_decimal_match=True,no_post_start_restore=True),indent=2))
 else:obs=authority.checked_restore(case,a.out)(env,context)
 state=core.RobotState(a.out/'transaction_state');state.ready=True;state.mode='idle';state.obs=copy.deepcopy(obs);state.observed_at=time.time();state.policy_metadata=metadata;state.execution_backend='agent';state.execution_profile='F28d-local-four-roles';state.scene_inventory=inventory_from_names(name for category in('objects','fixtures')for names in env.env.parsed_problem[category].values()for name in names)
 bridge=SingleOwnerBridge(env,obs,state,a.out,case,runner,authority);bridge.install_hooks();bridge.build_run_function()
 # Correct text only. The private scoring contract is not supplied in this tool.
 source_outcome=None
 if a.natural_source:
  from natural_source import prepare
  try:source_outcome=prepare(bridge,client,case)
  except BaseException:
   bridge.kernel_error=traceback.format_exc();bridge.stop_reason='source_preparation_runtime_error';source_outcome=dict(reached=False,reason='source_preparation_runtime_error',pre_pause_commands=0,reset_at_switch=False)
 else:bridge.command('robot_start_task',instruction=case['public_user_instruction'])
 post_switch_begin=time.monotonic();post_switch_control_start=bridge.control_steps;post_switch_physics_start=bridge.physics_steps;post_switch_holds_start=bridge.async_hold_steps
 if source_outcome is None or source_outcome['reached']:bridge.start(client)
 else:bridge.stop_reason=bridge.stop_reason or'source_preparation_failed';bridge.worker_done.set()
 next_tick=time.monotonic();pause_start=None;pause_done=False;before_hash=None;before_step=None;before_time=None;generation_results=[]
 try:
  while time.monotonic()-(post_switch_begin if a.natural_source else bridge.begin)<900:
   now=time.monotonic();allow=now>=next_tick
   if a.pause_probe and not pause_done and pause_start is None and bridge.io and bridge.io['role']==a.pause_role and now-bridge.io['started']>.1:
    bridge.command('robot_pause',reason='G2_explicit_pause_probe')
    with state.lock,bridge.env_lock:before_hash=bridge.state_hash();before_step=bridge.physics_steps;before_time=float(env.sim.data.time)
    pause_start=now
   if pause_start is not None and not pause_done and now-pause_start>=.6:
    with state.lock,bridge.env_lock:
     audit=dict(before_hash=before_hash,after_hash=bridge.state_hash(),before_physics_step=before_step,after_physics_step=bridge.physics_steps,before_simulation_time=before_time,after_simulation_time=float(env.sim.data.time),pause_wall_seconds=now-pause_start)
     audit['passed']=audit['before_hash']==audit['after_hash']and before_step==bridge.physics_steps and before_time==float(env.sim.data.time);bridge.pause_probes.append(audit);bridge.log('hard_pause_probe',**audit)
    bridge.command('robot_resume');pause_done=True
   stepped=bridge.pump(allow)
   if stepped:next_tick=time.monotonic()+.05
   if bridge.worker_done.is_set():
    if bridge.kernel_error=='retired_generation'and state.mode=='paused':
     time.sleep(.002);continue
    generation_results.append(dict(generation=bridge.generation,error=bridge.kernel_error,status=None if bridge.kernel_result is None else bridge.kernel_result.get('status')))
    if bridge.kernel_error=='retired_generation'and state.mode=='running'and not bridge.terminal_reason and bridge.restart_count<2:
     bridge.restart_count+=1;bridge.resume_requested=False;bridge.start(client,resume=True);continue
    break
   if bridge.terminal_reason:break
   if bridge.control_steps-post_switch_control_start>=a.control_budget:
    bridge.stop_reason='authorized_control_budget_exhausted';break
   time.sleep(.002)
  else:bridge.stop_reason='wall_budget_exhausted'
 except BaseException:bridge.kernel_error=traceback.format_exc();bridge.stop_reason='gateway_runtime_error'
 finally:
  if not bridge.terminal_reason and state.mode=='running':
   reason=bridge.stop_reason or bridge.kernel_error or(None if bridge.kernel_result is None else bridge.kernel_result.get('status'))or'kernel_stopped'
   state._hold('budget_exhausted'if'budget'in reason else'needs_review',reason);state.completion_status='not_verified';bridge.log('task_stopped_receipt',reason=reason,mode=state.mode,completion=state.completion_status)
  # Persist real physical evidence before scoring, including scoring failures.
  with gzip.open(a.out/'gateway_trace.json.gz','wt')as f:json.dump(dict(measurements=bridge.measurements,metric_initial=bridge.initial),f)
  bridge.close();scoring_error=None
  try:score=bridge.score()
  except BaseException:scoring_error=traceback.format_exc();score={};bridge.stop_reason='scoring_runtime_error'
  result=dict(case_id=case['case_id'],group=case['group'],mode='G2.1 real asynchronous Gateway, current-contract stop and observed-goal guard',control_budget=a.control_budget,authorized_control_steps=bridge.control_steps,physics_steps=bridge.physics_steps,async_wait_hold_steps=bridge.async_hold_steps,pause_probes=bridge.pause_probes,late_results_discarded=bridge.stale_discarded,kernel_restarts=bridge.restart_count,generations=generation_results,terminal_reason=bridge.terminal_reason,stop_reason=bridge.stop_reason,kernel_error=bridge.kernel_error,status=state.mode if bridge.terminal_reason else bridge.stop_reason or(None if bridge.kernel_result is None else bridge.kernel_result.get('status'))or bridge.kernel_error,metrics=score,completed_events=bridge.approved_events,seconds=time.monotonic()-bridge.begin,reset_after_start=False,state_writes_after_start=False,new_model_calls=True,oracle_subgoal=False,oracle_points=False,cache_validity_simulator_assisted=True,final_feedback='independent published original v2.5',clock_contract='engine frame counts authorized kernel actions; async hold physics ticks use separate physics_step',policy_port=a.port,render_gpu=a.gpu,video=str(a.out/'gateway_environment.mp4'))
  (a.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
  if scoring_error:result.update(status='scoring_runtime_error',scoring_error=scoring_error)
  result.update(natural_case_id=('NATURAL8__'+case['case_id'])if a.natural_source else None,natural_source=source_outcome,post_switch_seconds_including_cleanup=time.monotonic()-post_switch_begin,authorized_post_switch_control_steps=bridge.control_steps-post_switch_control_start,post_switch_physics_steps=bridge.physics_steps-post_switch_physics_start,post_switch_async_hold_steps=bridge.async_hold_steps-post_switch_holds_start,final_gateway_mode=state.mode,final_completion_status=state.completion_status,implementation_sha256=implementation_sha256,acceptance_decision=bridge.acceptance_decision,acceptance_protocol='current-contract-stop-v1',progress_guard=os.environ.get('G21_PROGRESS_GUARD','1')=='1')
  (a.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
  env.close();state.db.close()
 print(json.dumps(dict(case_id=a.case_id,status=result['status'],physical_steps=bridge.physics_steps,actions=bridge.control_steps,success=score.get('instruction_adjusted',{}).get('success'),seconds=result['seconds'])),flush=True)
 return result
if __name__=='__main__':main()
