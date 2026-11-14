"""Native source execution, continuous M1, then a command without pre-pause.
The GT-held predicate is a PRIVATE benchmark injection trigger, never Agent input.
"""
import concurrent.futures,copy,json,time
import numpy as np
from policy_backend import build_smol_inputs

def switch_contract(contract, articulation):
 result=copy.deepcopy(contract)
 for clause in result['clauses']:
  if clause['kind']=='preserve_articulation_state'and clause.get('reference')=='instruction_switch':
   clause['reference_q']=articulation[clause['joint']]
 return result

def prepare(bridge,client,case):
 b=bridge;state=b.state;b.scoring_active=False
 source_names={1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',5:'plate',6:'cheese',8:'bowl',9:'wine_bottle'}
 expected=source_names[case['source_task']]
 # Build memory before the old task, not only at the instruction switch.
 points=b.runner.Points(b.root/'episode_memory/points',episode_id=state.episode,episode_frame_at_takeover=0)
 image=np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1]);facts=b.cache_reader.memory_evidence();camera=b.cache_reader.memory_camera_id()
 points.initialize_episode(image,facts,camera);points.begin_instruction(image,0)
 b.command('robot_start_task',instruction=case['previous_instruction'])
 pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);future=None;captured=None;owner=None;calls=0;source_actions=0;streak=0;next_tick=time.monotonic();started=time.monotonic();source_id=state.task_id;missing_actions=0
 def infer(obs,call):
  req=build_smol_inputs(obs,case['previous_instruction'].rstrip()+'\n');req.update(evaluation_case_id='G2-natural-source:'+case['case_id'],evaluation_call_index=call)
  if call==0:req['evaluation_seed']=case['policy_seed']
  return client.infer(req)
 outcome=None
 try:
  while source_actions<1200 and time.monotonic()-started<300:
   if future is not None and future.done():
    answer=future.result();actions=np.asarray(answer['actions'],float)[:4];actions=np.clip(actions,-1,1);actions[:,6]=np.where(actions[:,6]>0,1.,-1.)
    accepted=state.accept_actions(owner,actions,0,captured)
    b.log('native_source_policy_result',accepted=accepted,source_task_id=source_id,capture_monotonic=captured)
    future=None
   if not state.queue and future is None:
    from hold_gate import PoseHold
    b.pose=PoseHold(b.obs,b.env.env.robots[0].controller)
    obs=copy.deepcopy(b.obs);captured=b.capture_monotonic;owner=state.version;future=pool.submit(infer,obs,calls);calls+=1
   now=time.monotonic()
   if now>=next_tick:
    with state.lock,b.env_lock:
     action=state.next_action();is_policy=action is not None
     if not is_policy:action=b.pose.action(b.obs)
     b.apply(action,'source_policy'if is_policy else'async_wait_hold')
     if is_policy:source_actions+=1
     if is_policy and source_actions%4==0:
      points.update_evidence(b.control_steps,b.cache_reader.memory_evidence(),b.cache_reader.memory_camera_id());points.observe(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1]),b.control_steps)
     item=b.cache_reader.snapshot.get('objects',{}).get(expected,{})
     held=b.cache_reader.snapshot.get('held_object')==expected and item.get('supported')is False
     streak=streak+1 if held else 0
     if streak>=3 and source_actions>=4:
      before=dict(mode=state.mode,task_id=state.task_id,version=state.version,physical_state_sha256=b.state_hash(),pending_action_count=len(state.queue),simulation_time=float(b.env.sim.data.time),physics_step=b.physics_steps,source_actions=source_actions)
      assert state.mode=='running'
      b.command('robot_revise_task',instruction=case['public_user_instruction'])
      if future is not None:
       # Drain this actual in-flight result, then submit with its OLD identity.
       # accept_actions is required to reject it; no old action is applied.
       old_future=future;old_owner=owner;old_capture=captured
       def discard_late(f):
        try:
         ans=f.result();ok=state.accept_actions(old_owner,np.asarray(ans['actions'],float)[:4],0,old_capture);b.log('source_late_result_rejected',accepted=ok,old_version=old_owner,current_version=state.version)
        except Exception as e:b.log('source_late_result_error',type=type(e).__name__)
       old_future.add_done_callback(discard_late)
      outcome=dict(reached=True,trigger='three GT-held/non-supported benchmark observations; trigger only, never Agent input',source_actions=source_actions,source_policy_calls=calls,before_command=before,after_command=dict(mode=state.mode,task_id=state.task_id,version=state.version,physical_state_sha256=b.state_hash(),simulation_time=float(b.env.sim.data.time),physics_step=b.physics_steps,pending_action_count=len(state.queue)),pre_pause_commands=0,reset_at_switch=False,continuous_scene_memory=True,source_seconds=time.monotonic()-started)
      b.log('natural_interruption',**outcome)
      break
    next_tick=time.monotonic()+.05
   time.sleep(.002)
  if outcome is None:outcome=dict(reached=False,source_actions=source_actions,source_policy_calls=calls,reason='source_did_not_reach_held_trigger',pre_pause_commands=0,reset_at_switch=False,continuous_scene_memory=True,source_seconds=time.monotonic()-started)
 finally:pool.shutdown(wait=False,cancel_futures=True)
 if outcome['reached']:
  # Final-target scoring begins only AFTER the new user task is authorized.
  b.initial=dict(articulation=b.source.measure()['articulation'],native_goal=bool(b.rt.frame(b.target,case['target_task'])['goal']))
  b.contract=switch_contract(b.contract,b.initial['articulation'])
  b.root.joinpath('natural_contract.json').write_text(json.dumps(b.contract,ensure_ascii=False,indent=2)+'\n')
  b.measurements=[];b.terminal=b.authority.published.StopController(case,b.contract,b.rules);b.scoring_active=True
 b.root.joinpath('natural_source.json').write_text(json.dumps(outcome,ensure_ascii=False,indent=2)+'\n')
 return outcome
