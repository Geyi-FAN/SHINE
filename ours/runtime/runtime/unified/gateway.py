"""Isolated speech-compatible Gateway; one owner of the G2 physical bridge.
No scoring contract or evaluator trigger is supplied to any language model.
"""
import argparse,copy,gzip,hashlib,importlib.util,io,json,os,signal,sys,threading,time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2')]
from bootstrap import configure

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--spec',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--port',type=int,required=True);ap.add_argument('--gpu',type=int,default=4);ap.add_argument('--policy-port',type=int,default=19866);a=ap.parse_args()
 spec=json.loads(a.spec.read_text());a.out.mkdir(parents=True,exist_ok=True);(a.out/'logs').mkdir(exist_ok=True)
 os.environ.update(VOICE_ROBOT_DATA_DIR=spec.get('state_directory',str(a.out/'gateway')),VOICE_EVAL_RECORD_DIR=str(a.out/'recordings'),VOICE_HARNESS_RUNTIME_CONFIG=str(B/'freeze/voice/configs/runtime.local.json'))
 os.environ['HYBRID_POLICY_PORT']=str(a.policy_port)
 core,runner,authority=configure(a.out,a.gpu)
 from repair6.clarification_guard import install as install_clarification_guard
 install_clarification_guard(core.RobotState)
 from repair.wording_guard import install as install_wording_guard
 install_wording_guard()
 original_completion=sys.modules['completion'];sys.modules['completion']=sys.modules['gateway_completion'];sys.path.insert(0,str(B/'freeze/voice/robot_gateway'))
 module_spec=importlib.util.spec_from_file_location('g3_http',B/'freeze/voice/robot_gateway/server.py');http=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(http);sys.modules['completion']=original_completion
 from sim_runtime import GeometryRuntime,new_env
 from revision_eval.env import make_libero_env,settle_env
 from policy_backend import SmolHTTPClient
 from grounding import inventory_from_names
 from bridge import SingleOwnerBridge
 from native_execution import NativeExecution,CATALOG
 from speech_routing import native_candidate
 from PIL import Image
 import h5py
 fixture=spec['fixture'];assets=fixture['assets']
 for asset in assets.values():assert hashlib.sha256(Path(asset['path']).read_bytes()).hexdigest()==asset['sha256']
 scene_task=SimpleNamespace(problem_folder='',bddl_file=assets['bddl_file']['path'],language='approved live8787 fixture')
 env,_=make_libero_env(scene_task,SimpleNamespace(env_img_res=256,seed=fixture['scene_seed'],control_mode='relative'))
 env.env.ignore_done=True;env.env.horizon=10000
 from revisionlab.render_context import bind_render_context
 bind_render_context(env)
 with h5py.File(assets['source_hdf']['path'])as f:obs=settle_env(env,f['states'][0].copy(),10)
 rt=GeometryRuntime();positions=rt.monitor(env,0).measure()['all_object_poses'];xyz={name:value['position']for name,value in positions.items()}
 context=authority.state.capture(env);context.update(main_raw_image=obs['agentview_image'],wrist_raw_image=obs['robot0_eye_in_hand_image']);initial=a.out/'initial.npz';np.savez(initial,**context)
 reference=np.asarray(Image.open(assets['reference_image']['path']).convert('RGB'));actual=np.ascontiguousarray(obs['agentview_image'][::-1,::-1]);delta=np.abs(actual.astype(int)-reference.astype(int));assert delta.max()<=2 and delta.mean()<=.001,'Initial scene does not match approved fixture'
 (a.out/'initial_scene.json').write_text(json.dumps(dict(expected=assets['reference_image']['sha256'],actual=hashlib.sha256(Image.fromarray(actual).tobytes()).hexdigest(),maximum_channel_delta=int(delta.max()),mean_delta=float(delta.mean()),state_identity=authority.state.identity(context)),indent=2))
 state=http.state;state.ready=False;state.obs=copy.deepcopy(obs);state.reset_count=spec.get('reset_count',1);state.version=spec.get('initial_version',0);state.mode='loading';state.execution_backend='qwen'
 from response_memo import fingerprint
 class Client(SmolHTTPClient):
  def infer(self,request):
   identity=list(b.token());digest=fingerprint(request)
   b.log('executor_input',identity=identity,request_sha256=digest,prompt=request['prompt'],conditioning_mode=request.get('conditioning_mode','symbolic'),policy_call_index=request['evaluation_call_index'])
   response=super().infer(request);response.update(paired_request_sha256=digest,paired_response_memo_hit=False,paired_action_sha256=fingerprint(np.asarray(response['actions'],np.float32)))
   b.log('executor_output',identity=identity,request_sha256=digest,action_count=len(response['actions']),action_sha256=response['paired_action_sha256'])
   return response
 client=Client(port=a.policy_port);metadata=client.get_server_metadata();state.policy_metadata=metadata
 case=copy.deepcopy(json.loads((B/'g2/fixed32.json').read_text())[0]);case.update(case_id=state.episode,source_task=spec.get('source_task',0),target_task=0,kind='revision',group='G3',initial_state_file=str(initial),snapshot_file=str(initial),initial_xyz=xyz,fixed_switch_step=0,previous_instruction='',public_user_instruction='',instruction='',policy_seed=7)
 (a.out/'benchmark_identity.private.json').write_text(json.dumps(dict(benchmark_case_id=spec['case_id'],episode_id=state.episode)))
 objective_context=[None]
 def contract(target,revision=False):
  if objective_context[0]is not None:return dict(case_id=case['case_id'],clauses=objective_context[0].clauses,budget=spec.get('task_control_budget',1200))
  clauses=[];clause=lambda **kw:dict(source='case.instruction.G3_private_evaluator',**kw)
  if revision and spec.get('restore'):
   name={'bowl':'akita_black_bowl_1','wine_bottle':'wine_bottle_1'}[spec['restore']];clauses.append(clause(id='restore',kind='restore_episode_start',object=name,reference='source_episode_start',reference_position=xyz[name],stable_required=True,withdraw_required=False))
  clauses.append(clause(id='target',kind='native_target',task_id=target,goal_kind='return_released_only'if revision and spec.get('return_only')else'libero_native'))
  if revision and spec.get('restore')and not spec.get('return_only'):clauses.append(clause(id='order_restore_target',kind='completion_order',before='restore',after='target'))
  if revision and spec.get('preserve_bowl'):
   current=rt.monitor(env,0).measure()['all_object_poses']['akita_black_bowl_1']['position'];clauses.append(clause(id='preserve_bowl',kind='preserve_position',object='akita_black_bowl_1',reference_position=current))
  return dict(case_id=case['case_id'],clauses=clauses,budget=1200)
 private=a.out/'private_contracts.json';private.write_text(json.dumps([contract(0)]));os.environ['HYBRID_CONTRACT_FILE']=str(private);runner.CONTRACT_FILE=private
 from g22.return_release import install as install_release
 # C3r owns the stalled-return review; no duplicate G22 insertion
 from continuation.dispatched_policy_index import install as install_dispatch_index
 install_dispatch_index(SingleOwnerBridge)
 from t3repair.integration import install as install_t3_repairs
 install_t3_repairs(SingleOwnerBridge)
 from repair6.completion import install as install_completion
 install_completion(SingleOwnerBridge)
 from entryfix.support import install as install_support
 install_support(SingleOwnerBridge)
 from entryfix.lifecycle import install as install_lifecycle
 install_lifecycle(SingleOwnerBridge)
 from c3r.integration import install as install_c3r
 install_c3r(SingleOwnerBridge)
 from unified.hooks import install_bridge as install_shared
 install_shared(SingleOwnerBridge)
 class Bridge(SingleOwnerBridge):
  def apply(self,action,phase):
   from unified.switch_action_budget import SwitchActionBudget
   budget=getattr(self,'switch_action_budget',None)
   if budget is None:
    budget=self.switch_action_budget=SwitchActionBudget(self.root/'request_budget.json',self.log)
   policy=phase in ('authorized_kernel_control','authorized_native_control','source_policy')
   if not budget.before(self.state,self.control_steps,policy):
    from g2.bridge import EpisodeStopped
    raise EpisodeStopped()
   owner=(self.state.task_id,self.state.version)
   result=super().apply(action,'source_policy'if phase=='authorized_native_control'else 'async_wait_hold'if phase=='evaluator_terminal_hold'else phase)
   budget.after(policy)
   if hasattr(self,'audit'):self.audit.record(phase,owner)
   return result
  def commit_acceptance(self,decision):
   committed=super().commit_acceptance(decision)
   if committed:
    self.state.agent_execution['completion_receipt']=dict(ready=False,consecutive_verified_physics_frames=0,required_physics_frames=40)
    from hold_gate import PoseHold
    self.pose=PoseHold(self.obs,self.env.env.robots[0].controller)
    self.state.agent_execution['source']='current_selected_instruction_physical_supervisor'
   return committed
 b=Bridge(env,obs,state,a.out,case,runner,authority);b.route='idle';b.install_hooks();b.build_run_function();b.native=None;b.native_goal_hold=False;b.task=None;b.task_count=0;b.task_start_control=0;b.task_started=0;b.fixture_hold=False;b.fixture_used=False;b.source_phase_streak=0;b.stopping=False;b.last_archived=None
 # Preserve episode memory across new tasks; only a new semantic task renews takeover.
 def begin_instruction(points,image,frame):
  if getattr(points,'g3_takeover_task',None)==state.task_id:return
  frame=max(b.engine_start_step,points.scene.frame,b.control_steps)
  points.update_evidence(frame,{},b.cache_reader.memory_camera_id());b.points_class.begin_instruction(points,image,frame);points.g3_takeover_task=state.task_id
 b.saved_points=runner.Points(a.out/'episode_memory/points',episode_id=state.episode,episode_frame_at_takeover=0)
 b.saved_points.begin_instruction=lambda image,frame:begin_instruction(b.saved_points,image,frame)
 b.saved_points.initialize_episode(actual,{},b.cache_reader.memory_camera_id())
 from depth_sensor import read_depth
 initial_depth,initial_calibration=read_depth(env)
 initial_rgbd=a.out/'episode_start_observed_rgbd_live.npz'
 np.savez_compressed(initial_rgbd,depth=initial_depth,calibration=json.dumps(initial_calibration))
 b.initial_observed_rgbd_file=str(initial_rgbd)
 from repair6.recorder import Recorder
 b.audit=Recorder(a.out,b);b.scoring_active=False;b.audit.record()
 from repair6.cached_logging import install as install_cached_logging
 install_cached_logging(b)
 state.scene_inventory=inventory_from_names(name for category in('objects','fixtures')for names in env.env.parsed_problem[category].values()for name in names)
 state.scene_memory_status=dict(state='ready',current_identity=True,version_matches=True,source='F28d_M1_episode_memory',episode_id=state.episode)
 state.execution_readiness=dict(phase='ready',ready=True,policy_ready=True,detector_ready=True,episode_memory_ready=True,current_observation_ready=True,execution_core='F28d_R4_live');state.observed_at=time.time();state.ready=True;state.mode='idle';state.execution_profile='symbolic'
 base_snapshot=state.snapshot
 def snapshot():
  result=base_snapshot();from repair6.public_execution import bind as bind_execution;result=bind_execution(result);result['execution_budget']=dict(authorized_control_steps=max(0,b.control_steps-b.task_start_control),control_limit=b.live_control_limit,base_control_allowance=b.live_base_control_budget,scope='current_task_cumulative; only explicit exhausted resume extends allowance');result['execution_kernel']='C3r';result['runtime_revision']='audio-c3r-prereval-repairs-v8-20261114';result['scene_inventory']=None;result['native_scheduler']='prefetch-frame-aligned-v1';result['c3r_profile']=__import__('os').environ['C3R_PROFILE'];result['note']='C3r hosted04 four roles; observed intermediate completion; observable-only memory validity; simulator final benchmark acceptance only';return result
 state.snapshot=snapshot
 original_command=state.command
 intake={};original_interaction=state.record_interaction
 def record_interaction(body):
  with state.lock:
   receipt=original_interaction(body)
   if not receipt.get('duplicate'):
    intake[body['input_id']]=dict(episode_id=state.episode,task_id=state.task_id,semantic_revision=state.task_intent_revision,version=state.version,mode=state.mode,text=body['text'],monotonic=time.monotonic())
   return receipt
 state.record_interaction=record_interaction
 def command(name,args,request_id):
  with state.lock:
   before=b.token()
   from g22.completion_race import bind
   args=bind(b,name,args,intake)
   try:receipt=original_command(name,args,request_id)
   except Exception as error:b.log('voice_tool_rejected',tool=name,error=str(error),request_id=request_id);raise
  b.log('voice_tool_receipt',tool=name,args=args,request_id=request_id,before_identity=list(before),after_identity=list(b.token()),receipt=receipt)
  if name=='robot_resume' and state.mode=='running' and b.fixture_hold:
   b.fixture_hold=False;b.log('controlled_source_window_released_on_actual_resume')
  if isinstance(receipt,dict) and isinstance(receipt.get('qa_evidence'),dict):receipt['qa_evidence']['drawer_facts']=None
  return receipt
 state.command=command
 from repair6.waiting_prefetch import install as install_waiting_prefetch
 # Current-identity evidence preparation is installed by common C3r hooks.
 from continuation.authorized_resume import install as install_authorized_resume
 install_authorized_resume(b,state,spec)
 class Handler(http.Handler):
  def do_GET(self):
   if self.path=='/evaluator/inspect':
    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})
    # Only the owner publishes this immutable dict. The monitor never acquires
    # either simulation lock and never touches MuJoCo from an HTTP thread.
    sample=b.audit.last
    from repair.telemetry import inspect as inspect_snapshot
    return self.respond(200,inspect_snapshot(sample))
   if self.path=='/evaluator/status':
    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})
    return self.respond(200,dict(physics_step=b.physics_steps,control_step=b.control_steps,simulation_time=float(env.sim.data.time),physical_state_sha256=b.state_hash(),fixture_hold=b.fixture_hold,task_count=b.task_count,task_control_steps=b.control_steps-b.task_start_control,io_role=None if b.io is None else b.io['role'],source_phase_reached=b.source_phase_streak>=3,task_id=state.task_id,mode=state.mode))
   return super().do_GET()
  def do_POST(self):
   if self.path in('/evaluator/release_window','/evaluator/hold'):
    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})
    with state.lock:
     if self.path.endswith('release_window'):b.fixture_hold=False;b.log('evaluator_fixture_window_released',not_a_user_command=True)
     else:
      if state.mode=='paused':return self.respond(409,{'error':'explicit_pause_forbids_env_step'})
      b.audit.hold_remaining=40;b.log('evaluator_terminal_hold_requested',physics_ticks=40,not_stage_completion=True)
    return self.respond(200,{'accepted':True})
   if self.path=='/evaluator/finish':
    if not self.authenticated():return self.respond(401,{'error':'authentication_required'})
    b.stopping=True;return self.respond(200,{'accepted':True})
   return super().do_POST()
 server=http.GatewayHTTPServer(('127.0.0.1',a.port),http.Handler if spec.get('serve_live')else Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 (a.out/'READY.json').write_text(json.dumps(dict(episode_id=state.episode,metadata=metadata,port=a.port,execution_core='F28d_R4_live',actual_owner='simulation_main_thread'),indent=2))
 from native_prefetch.scheduler import NativePrefetchMixin
 class Native(NativePrefetchMixin,NativeExecution):
  def _handoff_ready(self):
   from unified.native_handoff import ready
   return ready(state,b.acceptance_decision,b.token()[:3])
  def _infer(self,observation,*args):
   result=super()._infer(observation,*args);result['observed_at']=observation['_capture_monotonic'];return result
  def _finish(self,state,already_satisfied=False):
   # The Native target is a candidate. The same independent current-contract
   # acceptance owns the final receipt for Native and Symbolic routes.
   self._status(state,'target_candidate_waiting_for_release_and_current_acceptance')

 def archive():
  if not b.task or b.last_archived==b.task:return
  folder=a.out/'tasks'/b.task;folder.mkdir(parents=True,exist_ok=True)
  with gzip.open(folder/'trace.json.gz','wt')as f:json.dump(dict(measurements=b.measurements,metric_initial=b.initial),f)
  score=b.score();(folder/'result.json').write_text(json.dumps(dict(task_id=b.task,instruction=b.case['public_user_instruction'],route=b.route,metrics=score,controls=b.control_steps-b.task_start_control,world_step=b.physics_steps,mode=state.mode,completion_status=state.completion_status),indent=2));b.last_archived=b.task
 def activate():
  archive()
  if b.native:b.native.close();b.native=None
  b.task=state.task_id;b.task_count+=1;from continuation.authorized_resume import new_task;new_task(b);b.task_start_control=b.control_steps;b.task_started=time.monotonic();b.fixture_hold=False;b.native_goal_hold=False;b.last_archived=None
  state.agent_execution=dict(phase='planning',task_id=state.task_id,semantic_revision=state.task_intent_revision,completion_current_verified=False,source='current_task_activation')
  previous_instruction=b.case.get('public_user_instruction','');previous_target=b.case.get('target_task',0)
  b.case.update(kind='normal'if b.task_count==1 else'revision',public_user_instruction=state.instruction,instruction=state.instruction,current_instruction=state.instruction,instruction_original=state.instruction,previous_instruction=previous_instruction,source_task=previous_target)
  source=b.task_count==1 and bool(spec.get('context_turns'))
  from continuation.live.objectives import compile_objective,UnsupportedObjective,OBJECT_TASK
  current={name:value['position']for name,value in rt.monitor(env,0).measure()['all_object_poses'].items()}
  try:objective=compile_objective(state.instruction,xyz,current,b.source.measure()['articulation'],case['case_id'],previous_instruction=previous_instruction,source_task_start_xyz=xyz if b.task_count==2 else None,current_binary_state={'turn_on_stove':bool(b.cache_reader.snapshot['native_goal_relations']['turn_on_stove'])})
  except UnsupportedObjective as error:
   b.scoring_active=False;b.live_objective_error=str(error);state.failure_detail=dict(code='unsupported_current_goal_verifier',detail=str(error),recovery='完整要求未被删除；当前终验尚不能可靠覆盖该表达，需要澄清或补充支持。');state._hold('needs_review','unsupported_current_goal_verifier');b.log('current_goal_verifier_rejected',reason=str(error));return
  objective_context[0]=objective;target=objective.target_task
  b.return_only=objective.return_only;b.completion_gate=None;b.live_close_only=objective.close_only;b.live_open_only=objective.open_only;b.custom_goal_predicate=objective.custom_predicate
  if objective.restore_object:b.source=rt.monitor(env,OBJECT_TASK[objective.restore_object])
  from continuation.live.scoped_score import score as current_score
  b.score=lambda:current_score(b)

  b.case['target_task']=target;b.target=rt.monitor(env,target);b.contract=contract(target,not source);b.initial=dict(articulation=b.source.measure()['articulation'],native_goal=bool(rt.frame(b.target,target)['goal']));b.measurements=[];b.acceptance=None;b.acceptance_decision=None;b.terminal_reason=None;b.stop_reason=None;b.restart_count=0;b.scoring_active=True
  private.write_text(json.dumps([b.contract],indent=2));assert b.run_function.__globals__['CONTRACT_FILE']==private
  b.terminal=authority.published.StopController(b.case,b.contract,b.rules)
  width=float(np.abs(b.obs['robot0_gripper_qpos']).sum());skill,reason=native_candidate(state,b.task_count==1,'none'if width>=.065 else'unknown')
  if skill:
   b.route='native';state.execution_profile='native_libero_goal';memory=SimpleNamespace(reader=b.cache_reader)
   reader=None
   b.native=Native(env,memory,client,a.out/'native'/b.task,skill,goal_reader=reader)
   b.engine_start_step=max(b.control_steps,b.saved_points.scene.frame);b.saved_points.begin_instruction(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1]),b.engine_start_step)
  else:
   b.route='symbolic';state.execution_profile='symbolic';b.saved_recovery=None;b.approved_events=[]
   b.log('episode_observation_history_retained',new_task_id=state.task_id,previous_observed_frame=getattr(b.saved_mon,'last',None),plan_and_completion_reset=True,source='observed_RGBD_proprio_only')
   if hasattr(b,'original_takeover_images'):del b.original_takeover_images
   import planner
   b.planner=planner.Planner();from g21.observed_goal_guard import ADDENDUM
   b.planner.system+='\n'+ADDENDUM;b.start(client,resume=True)
  state.event('execution_profile_selected',dict(execution_profile=state.execution_profile,reason=reason,execution_core='F28d_R4_live'));b.log('g3_task_activated',task_id=b.task,route=b.route,instruction=state.instruction)
  b.audit.record()
 def jpeg():
  images=[]
  for key in('agentview_image','robot0_eye_in_hand_image'):
   f=io.BytesIO();Image.fromarray(np.ascontiguousarray(b.obs[key][::-1,::-1])).save(f,format='JPEG',quality=85);images.append(f.getvalue())
  with state.lock:state.jpeg,state.wrist_jpeg=images
 def close_signal(*_):b.stopping=True
 signal.signal(signal.SIGTERM,close_signal);signal.signal(signal.SIGINT,close_signal)
 tick=time.monotonic();last_image=0.;started=time.monotonic()
 try:
  while not b.stopping and(spec.get('serve_live')or time.monotonic()-started<spec.get('service_lifetime_s',1600)):
   now=time.monotonic()
   if http.priority_stop_enabled:http.priority_stop.drain(state.command)
   # Before the first task there is no user-authorized motion. Advancing a
   # neutral gripper actuator during voice startup changes the approved initial
   # observation. Keep the physical initialization intact; do not pause an
   # already-running task, freeze execution time, or alter any task deadline.
   if b.task_count==0 and state.task_id is None and state.mode=='idle':
    if now-last_image>.2:jpeg();last_image=now
    time.sleep(.002);continue
   if spec.get('held_source_entity')and b.task_count==spec.get('source_window_task_count',1)and state.mode=='running'and not b.fixture_used:
    entity=spec['held_source_entity'];facts=b.cache_reader.snapshot
    if getattr(b,'fixture_checked_physics',-1)!=b.physics_steps:
     b.fixture_checked_physics=b.physics_steps
     b.source_phase_streak=b.source_phase_streak+1 if facts['held_object']==entity and not facts['objects'][entity]['supported']else 0
    if b.source_phase_streak>=3:
     from hold_gate import PoseHold
     b.pose=PoseHold(b.obs,env.env.robots[0].controller);b.fixture_hold=True;b.fixture_used=True;state.queue.clear()
     if b.native:b.native.invalidate(state)
     b.log('controlled_source_window_latched',entity=entity,world_clock_continues=True)
   if b.fixture_hold and state.task_id==b.task and state.mode=='running'and now>=tick:
    with state.lock:
     if b.env_lock.acquire(blocking=False):
      try:b.apply(b.pose.action(b.obs),'async_wait_hold');tick=time.monotonic()+.05
      finally:b.env_lock.release()
    if now-last_image>.2:jpeg();last_image=now
    time.sleep(.002);continue
   gate=getattr(b,'completion_gate',None)
   if gate and gate.holding and tuple(gate.subject)==b.token()[:3]and state.mode=='running'and now>=tick:
    with state.lock:
     if b.env_lock.acquire(blocking=False):
      try:b.apply(b.pose.action(b.obs),'async_wait_hold');tick=time.monotonic()+.05
      finally:b.env_lock.release()
    if now-last_image>.2:jpeg();last_image=now
    time.sleep(.002);continue
   if b.audit.hold_remaining and now>=tick and state.mode!='paused':
    with state.lock:
     if b.env_lock.acquire(blocking=False):
      try:b.apply(b.pose.action(b.obs),'evaluator_terminal_hold');b.audit.hold_remaining-=1;tick=time.monotonic()+.05
      finally:b.env_lock.release()
    if now-last_image>.2:jpeg();last_image=now
    time.sleep(.002);continue
   if b.env_lock.acquire(blocking=False):
    try:b.audit.passive()
    finally:b.env_lock.release()
   if state.task_id!=b.task and state.mode=='running'and not(b.thread and b.thread.is_alive()):activate()
   if state.task_id!=b.task and b.thread and b.thread.is_alive():b.pump(True)
   elif b.route=='symbolic'and b.task and state.task_id==b.task:
    stepped=b.pump(now>=tick)
    from terminal_observation import tick as terminal_hold_tick
    if not stepped:stepped=terminal_hold_tick(b,state,now>=tick)
    if stepped:tick=time.monotonic()+.05
    if b.worker_done.is_set()and state.mode=='running'and b.kernel_error=='retired_generation'and b.restart_count<2:
     b.restart_count+=1;b.start(client,resume=True)
    elif b.worker_done.is_set()and state.mode=='running'and not b.terminal_reason:
     detail=b.kernel_error or(b.kernel_result or{}).get('error')or(b.kernel_result or{}).get('status')or'F28d_worker_stopped'
     state.failure_detail=dict(code='f28d_execution_stopped',detail=str(detail)[-1200:],recovery='执行内核已停止；请查看隔离运行日志，不要将此报错归为动作模型失败。');state._hold('needs_review','F28d_execution_stopped');b.log('symbolic_worker_stopped',detail=detail)
   elif now>=tick:
    if b.env_lock.acquire(blocking=False):
     try:
      with state.lock:
       if state.mode!='paused':
        if b.native and state.task_id==b.task and not b.fixture_hold and not b.native_goal_hold and state.mode=='running':
         snap=copy.deepcopy(b.obs);snap['_capture_monotonic']=b.capture_monotonic
         from g22.native_wait import tick as native_tick
         native_tick(b,b.native,state,snap)
        action=state.next_action()if state.mode=='running'and not b.fixture_hold and not b.native_goal_hold else None;policy=action is not None
        b.apply(action if policy else b.pose.action(b.obs),'authorized_native_control'if policy else'async_wait_hold')
        if b.native:b.native.record_applied_action(state,policy)
        if b.route=='native'and b.physics_steps%4==0:
         p=b.saved_points;p.update_evidence(b.physics_steps,{},b.cache_reader.memory_camera_id());p.observe(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1]),b.physics_steps)
        if b.task_count==1 and spec.get('phase')and b.native:
         facts=b.cache_reader.snapshot;item=facts['objects']['bowl'];phase=spec['phase'];valid=facts['held_object']=='bowl'and not item['supported']if phase=='M2'else bool(rt.frame(rt.monitor(env,1),1)['goal'])and item['supported']and not item['robot_contact']
         b.source_phase_streak=b.source_phase_streak+1 if valid else 0
         if b.source_phase_streak>=3 and not b.fixture_hold and not b.fixture_used:
          from hold_gate import PoseHold
          b.pose=PoseHold(b.obs,env.env.robots[0].controller);b.fixture_hold=True;b.fixture_used=True;state.queue.clear();b.native.invalidate(state);b.log('common_fixture_observation_window',phase=phase,world_clock_continues=True)
     finally:b.env_lock.release()
    tick=time.monotonic()+.05
   with state.lock:
    if state.task_id==b.task and state.mode=='running'and(b.control_steps-b.task_start_control>=b.live_control_limit or now-b.task_started>b.live_wall_allowance_s):state._hold('budget_exhausted','G3_shared_1200_control_or_900_wall_budget')
   if state.mode=='completed'and state.completion_status=='verified':
    completion_score=b.score()
    state.agent_execution['completion_current_verified']=bool(b.acceptance_decision and b.acceptance_decision.get('accepted') and tuple(b.acceptance_decision.get('subject',[]))==b.token()[:3] and completion_score.get('instruction_adjusted',{}).get('success') and completion_score.get('final_release_evidence',{}).get('passed')is True)
    from unified.terminal_feedback import CompletionReceiptWindow
    if not hasattr(b,'completion_receipt_window'):b.completion_receipt_window=CompletionReceiptWindow()
    state.agent_execution['completion_receipt']=b.completion_receipt_window.observe(b.token(),b.physics_steps,state.agent_execution['completion_current_verified'])
    if b.route=='native':
     from unified.native_handoff import ready as native_handoff_ready
     state.native_handoff_ready=native_handoff_ready(state,b.acceptance_decision,b.token()[:3])
    from unified.deferred_tick import advance_verified_queue
    advance_verified_queue(state)
   if now-last_image>.2:jpeg();last_image=now
   time.sleep(.002)
 except BaseException:
  import traceback
  (a.out/'RUNTIME_ERROR.txt').write_text(traceback.format_exc());raise
 finally:
  if state.mode=='running':state._hold('cancelled','G3_evaluation_finished')
  if b.native:b.native.close()
  if state.reset_pending:state.event('episode_ended',dict(reason='operator_reset_process_handoff'))
  b.close();archive();b.audit.close();env.close();server.shutdown()
  (a.out/'DONE.json').write_text(json.dumps(dict(world_steps=b.physics_steps,controls=b.control_steps,late_results_discarded=b.stale_discarded,reset_count=state.reset_count),indent=2))

if __name__=='__main__':main()
