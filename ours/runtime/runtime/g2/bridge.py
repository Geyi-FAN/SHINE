"""Single-owner simulator bridge for the frozen F28d kernel.

The kernel runs in a background thread. During local model HTTP waits only the
Gateway owner may env.step. Explicit user pause forbids ALL physics stepping.
The old kernel's `step` clock counts authorized control/observation actions;
physics ticks during asynchronous waits have a distinct, fully scored clock.
"""
import copy,hashlib,json,queue,threading,time,traceback,sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from g21.private_acceptance import CurrentContractAcceptance

class KernelRetired(BaseException):pass
class EpisodeStopped(BaseException):pass

class RPC:
 def __init__(self,method,args,kwargs,token):self.method=method;self.args=args;self.kwargs=kwargs;self.token=token;self.done=threading.Event();self.value=None;self.error=None

class SimView:
 def __init__(self,bridge):self.bridge=bridge
 def __getattr__(self,name):
  if name=='render':return lambda *a,**kw:self.bridge.rpc('render',a,kw)
  if name in ('step','set_state','reset','forward'):raise RuntimeError('Simulator mutation has one owner')
  return getattr(self.bridge.env.sim,name)
class EnvView:
 def __init__(self,bridge):self.bridge=bridge;self.sim=SimView(bridge)
 def __getattr__(self,name):
  if name in ('reset','set_state','set_init_state','regenerate_obs_from_state'):
   def forbidden(*_a,**_kw):raise RuntimeError('No state writes after start')
   return forbidden
  return getattr(self.bridge.env,name)
 def step(self,action):return self.bridge.rpc('action',(np.asarray(action,float),),{})
 def close(self):pass # Kernel does not own the real environment's lifecycle.

class SingleOwnerBridge:
 def __init__(self,env,obs,state,root,case,runner,authority):
  from hold_gate import PoseHold
  from sim_runtime import GeometryRuntime
  from completion import Completion
  self.env=env;self.obs=obs;self.state=state;self.root=Path(root);self.case=case;self.runner=runner;self.authority=authority
  self.env_lock=threading.RLock();self.requests=queue.Queue();self.log_lock=threading.Lock();self.io=None;self.thread=None;self.worker_done=threading.Event();self.kernel_result=None;self.kernel_error=None;self.resume_requested=False
  self.physics_steps=0;self.control_steps=0;self.async_hold_steps=0;self.capture_monotonic=time.monotonic();self.capture_sim_time=float(env.sim.data.time)
  self.pose=PoseHold(obs,env.env.robots[0].controller);self.view=EnvView(self);self.ctx=None;self.saved_mon=None;self.saved_points=None;self.saved_recovery=None;self.saved_observed_states=None;self.saved_relations=None;self.approved_events=[]
  self.mon_class=runner.ObservedCompletion;self.points_class=runner.Points;self.recovery_class=runner.RecoveryRuntime
  self.closed=False;self.stop_reason=None;self.last_phase='setup';self.last_token=None;self.policy_capture=None;self.engine_start_step=0;self.generation=0;self.restart_count=0;self.stale_discarded=0;self.policy_calls_attempted=0
  self.rules=runner.load_rules();self.rt=GeometryRuntime();self.source=self.rt.monitor(env,case['source_task']);self.target=self.rt.monitor(env,case['target_task'])
  self.cache_reader=Completion(env,case.get('initial_xyz',{}),case['source_task'],case.get('previous_instruction',''));self.cache_reader.observe(0)
  self.contract=next(c for c in json.loads(Path(__import__('os').environ['HYBRID_CONTRACT_FILE']).read_text())if c['case_id']==case['case_id'])
  self.initial=dict(articulation=self.source.measure()['articulation'],native_goal=bool(self.rt.frame(self.target,case['target_task'])['goal']))
  self.measurements=[];self.terminal=authority.published.StopController(case,self.contract,self.rules);self.terminal_reason=None;self.acceptance=None;self.acceptance_decision=None;self.begin=time.monotonic();self.pause_probes=[];self.scoring_active=True
  self.root.mkdir(parents=True,exist_ok=True);self.root.joinpath('logs').mkdir(exist_ok=True)
  import imageio
  self.video=imageio.get_writer(str(self.root/'gateway_environment.mp4'),fps=10,macro_block_size=16)
 def token(self):return(self.state.episode,self.state.task_id,self.state.task_intent_revision,self.state.version)
 def log(self,kind,**data):
  row=dict(time=time.time(),monotonic=time.monotonic(),kind=kind,physics_step=self.physics_steps,control_step=self.control_steps,simulation_time=float(self.env.sim.data.time),**data)
  with self.log_lock,(self.root/'gateway.jsonl').open('a')as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 def worker_context(self):
  f=sys._getframe()
  while f:
   if f.f_code.co_name=='run'and f.f_locals.get('env')is self.view:self.ctx=f;return f.f_locals
   f=f.f_back
  return {}if self.ctx is None else self.ctx.f_locals
 def rpc(self,method,args,kwargs):
  self.worker_context();r=RPC(method,args,kwargs,self.last_token or self.token());self.requests.put(r)
  self.env_lock.release()
  try:
   while not r.done.wait(.05):
    if self.closed:raise EpisodeStopped()
   if r.error:raise r.error
   return r.value
  finally:self.env_lock.acquire()
 def continuity(self,a,b):
  pos=float(np.linalg.norm(np.asarray(a['robot0_eef_pos'])-np.asarray(b['robot0_eef_pos'])))
  width=float(np.max(np.abs(np.asarray(a['robot0_gripper_qpos'])-np.asarray(b['robot0_gripper_qpos']))))
  main=float(np.abs(a['agentview_image'].astype(np.float32)-b['agentview_image'].astype(np.float32)).mean())
  return dict(eef_translation_m=pos,max_finger_change_m=width,MAIN_raw_mae=main,passed=pos<=.005 and width<=.008 and main<=1.)
 def observed_continuity(self,role,context,old_points,proof):
  """Fallback to image-only typed points and frozen physical prerequisites.
  No simulator object poses, cache points or benchmark labels enter this check.
  """
  mon=context.get('mon');points=context.get('points')
  if mon is None or points is None:return False,{'reason':'no_observed_monitor'}
  from PIL import Image
  image=self.root/'io_current_MAIN.png';Image.fromarray(np.ascontiguousarray(self.obs['agentview_image'][::-1,::-1])).save(image)
  points.proc.stdin.write(json.dumps(dict(image=str(image),frame=self.physics_steps))+'\n');points.proc.stdin.flush()
  while True:
   line=points.proc.stdout.readline()
   if not line:return False,{'reason':'detector_exited'}
   try:prediction=json.loads(line)
   except ValueError:continue
   if isinstance(prediction,dict)and('points'in prediction or'error'in prediction):break
  if 'error'in prediction:return False,{'reason':'detector_error'}
  fresh={(p['entity'],p['keypoint']):p for p in prediction['points']if min(p.get('det_confidence',0),p.get('keypoint_confidence',0))>=mon.settings.confidence}
  old={(p['entity'],p['keypoint']):p for p in old_points if min(p.get('det_confidence',0),p.get('keypoint_confidence',0))>=mon.settings.confidence}
  stage=context.get('validation_stage')or mon.active or((context.get('decision')or{}).get('remaining_plan')or[{}])[0];op=stage.get('operation','')
  from planner import CATALOG
  spec=CATALOG.get(op,{});ref=spec.get('reference');entities={stage.get('object')}
  if ref:entities.add(ref['entity'])
  if op.startswith(('open_','close_')):entities.add(('top'if op.endswith('top')else'middle')+'_handle')
  relevant={key:value for key,value in old.items()if key[0]in entities}
  if not relevant:relevant=old
  deltas={e+'.'+k:float(np.linalg.norm(np.asarray(p['yx224'])-np.asarray(fresh[(e,k)]['yx224'])))for(e,k),p in relevant.items()if(e,k)in fresh}
  width=float(np.abs(self.obs['robot0_gripper_qpos']).sum());previous_width=float(np.abs(context['obs']['robot0_gripper_qpos']).sum())
  def category(w):return 'open'if w>=mon.settings.open_width_m else'closed'if mon.settings.min_width_m<=w<mon.settings.closed_width_m else'empty_closed'if w<mon.settings.min_width_m else'transition'
  stable=bool(deltas)and max(deltas.values())<=mon.settings.stable_radius_px
  passed=stable and proof['eef_translation_m']<=mon.settings.motion_m and category(width)==category(previous_width)
  checks={}
  if role=='verifier'and context.get('require_completion_guards',True):
   obj=stage.get('object');kind=stage.get('kind')
   if kind=='grasp':
    zs=[r['sensor']['eef_xyz'][2]for r in mon.rgb_rows if r.get('sensor')and r['frame']>=mon.entered]
    lift=float(self.obs['robot0_eef_pos'][2])-min(zs)if zs else 0
    checks['closed_grasp_and_lift']=mon.settings.min_width_m<=width<mon.settings.closed_width_m and lift>=mon.settings.lift_m
    from sym_geometry import project
    hand_yx,valid=project(self.env.sim,np.asarray(self.obs['robot0_eef_pos']));target=fresh.get((obj,'K1'))
    checks['current_grasp_object_visible_near_hand']=bool(valid and target and np.linalg.norm(hand_yx-np.asarray(target['yx224']))<=mon.settings.near_hand_px)
   if kind in('return','release')or op in('cheese_bowl','bowl_drawer','bowl_stove','bowl_plate','bowl_cabinet','bottle_cabinet','bottle_rack'):checks['currently_open_release']=width>=mon.settings.open_width_m
   if op.startswith(('open_','close_')):
    from depth_sensor import read_depth,sensed_geometry
    depth,cal=read_depth(self.view);geo=sensed_geometry(list(fresh.values()),depth,cal)
    level='top'if op.endswith('top')else'middle';reference=mon.calibration['closed_handles'][level];xyz=geo.get(level+'_handle.K1')
    gap=None if xyz is None else float(np.dot(np.asarray(xyz)-np.asarray(reference['xyz']),np.asarray(reference['opening_axis'])))
    checks['fresh_drawer_geometry']=gap is not None and(abs(gap)<=.010 if op.startswith('close_')else gap>=.145)
    if not checks['fresh_drawer_geometry']and gap is not None:
     mon.snapshot['drawers'][level]=dict(open=gap>=.145,closed_current=abs(gap)<=.010,closed_confirmed=False)
    if op=='open_middle':
     from sym_geometry import project
     yx,valid=project(self.env.sim,np.asarray(self.obs['robot0_eef_pos']));handle=fresh.get(('middle_handle','K1'));checks['currently_disengaged']=bool(valid and handle and np.linalg.norm(yx-np.asarray(handle['yx224']))>=12)
   if kind in('return','release'):
    reference=points.memory.get(('episode_start'if kind=='return'else'instruction_takeover',obj,'K2'));current=fresh.get((obj,'K2'));checks['current_object_at_historical_reference']=bool(reference and current and np.linalg.norm(np.asarray(current['yx224'])-np.asarray(reference['yx224']))<=mon.settings.return_radius_px)
  passed=passed and all(checks.values())
  details=dict(source='fresh_image_only_YOLO_and_robot_proprio; frozen S1 geometry and thresholds',point_displacements_MAIN224_px=deltas,current_gripper_width_m=width,gripper_category_unchanged=category(width)==category(previous_width),stable_radius_px=mon.settings.stable_radius_px,maximum_robot_motion_m=mon.settings.motion_m,current_checks=checks,passed=passed)
  self.log('current_observation_revalidation',role=role,**details)
  return passed,details
 def network(self,role,function,*args,**kwargs):
  if self.state.mode!='running'or self.last_token!=self.token():raise KernelRetired()
  context=self.worker_context();token=self.token();before=copy.deepcopy(self.obs);start=time.monotonic();self.pose=__import__('hold_gate').PoseHold(self.obs,self.env.env.robots[0].controller)
  old_points=copy.deepcopy(list(context.get('points').current.values()))if context.get('points')is not None else[]
  self.io=dict(role=role,token=token,started=start,control_frame=context.get('step',self.control_steps),capture_monotonic=self.capture_monotonic,physics_frame=self.physics_steps)
  self.log('io_started',role=role,identity=list(token),observation_capture_monotonic=self.capture_monotonic)
  self.env_lock.release()
  try:answer=function(*args,**kwargs)
  finally:self.env_lock.acquire()
  job=self.io;self.io=None
  if self.closed or self.terminal_reason:raise EpisodeStopped()
  if token!=self.token()or self.state.mode!='running':
   self.stale_discarded+=1;self.log('io_result_discarded',role=role,old_identity=list(token),current_identity=list(self.token()),reason='task_or_control_generation_changed');raise KernelRetired()
  proof=self.continuity(before,self.obs)
  if role=='policy'and time.monotonic()-job['capture_monotonic']>3.:
   self.stale_discarded+=1;self.log('io_result_discarded',role=role,reason='actual_capture_older_than_3s');raise KernelRetired()
  if role in('planning','wording','verifier','recovery')and not proof['passed']:
   validation_context=dict(context)
   if role=='planning':
    try:validation_context['validation_stage']=json.loads(answer['choices'][0]['message']['content'])['remaining_plan'][0]
    except Exception:pass
   if role=='verifier':
    try:validation_context['require_completion_guards']=json.loads(answer['choices'][0]['message']['content']).get('status')=='completed'
    except Exception:validation_context['require_completion_guards']=True
   acceptable,details=self.observed_continuity(role,validation_context,old_points,proof)
   proof['observed_revalidation']=details;proof['passed']=acceptable
  if role in('planning','wording','verifier','recovery')and not proof['passed']:
   self.stale_discarded+=1;self.log('io_result_discarded',role=role,reason='observed_state_changed_during_io',observed_continuity=proof);raise KernelRetired()
  # The main-thread renderer supplied the newest real observation. Preserve its
  # capture time; never replace it by this HTTP receipt time.
  loop_obs=context.get('obs')
  if isinstance(loop_obs,dict)and loop_obs is not self.obs:loop_obs.clear();loop_obs.update(copy.deepcopy(self.obs))
  self.last_token=token
  self.log('io_finished',role=role,identity=list(token),seconds=time.monotonic()-start,observed_continuity=proof,capture_monotonic=job['capture_monotonic'])
  return answer
 def command(self,name,**args):
  with self.state.lock:
   before=self.token();self._command_index=getattr(self,'_command_index',0)+1
   receipt=self.state.command(name,dict(episode_id=self.state.episode,expected_task_version=self.state.version,**args),'g2:'+str(self._command_index))
   if name=='robot_resume':self.resume_requested=True
   self.log('tool_receipt',tool=name,args=args,before_identity=list(before),after_identity=list(self.token()),receipt=receipt)
   return receipt
 def state_hash(self):
  arrays=[np.asarray(self.env.sim.get_state().flatten(),np.float64),np.asarray(self.env.sim.data.ctrl,np.float64),np.asarray(self.env.sim.model.body_pos,np.float64).ravel(),np.asarray(self.env.sim.model.body_quat,np.float64).ravel()]
  return hashlib.sha256(b''.join(a.tobytes()for a in arrays)).hexdigest()
 def install_hooks(self):
  import planner,task_language,visual_verifier,recovery_observer,text_transport,local_transport
  from g21.observed_goal_guard import install as install_goal_guard
  if __import__('os').environ.get('G21_PROGRESS_GUARD','1')=='1':install_goal_guard(planner)
  original_text=text_transport.request_json;original_verify=local_transport.verifier_request_json;original_recovery=local_transport.recovery_request_json
  def text(req,timeout=90):
   role=text_transport.classify(json.loads(req.data));return self.network(role,original_text,req,timeout=timeout)
  planner.request_json=text;task_language.request_json=text
  visual_verifier.request_json=lambda req,timeout=90:self.network('verifier',original_verify,req,timeout=timeout)
  recovery_observer.request_json=lambda req,timeout=90:self.network('recovery',original_recovery,req,timeout=timeout)
  original_new=self.runner.new_env;original_restore=self.runner.restore
  self.runner.new_env=lambda *a,**kw:self.view
  self.runner.restore=lambda *_a,**_kw:copy.deepcopy(self.obs)
  self.runner.capture=lambda _env:self.authority.state.capture(self.env)
  self.runner.identity=self.authority.state.identity
  bridge=self
  class ExternalTerminal:
   def __init__(self,*a,**kw):pass
   def check(self,*a,**kw):return dict(final_agent_stage=bool(bridge.terminal_reason),stop=bool(bridge.terminal_reason),passed=bool(bridge.terminal_reason and bridge.score().get('instruction_adjusted',{}).get('success',False)),source='Gateway_private_published_StopController',frame=bridge.physics_steps)
  self.runner.SwitchTerminal=ExternalTerminal
  self.runner.evaluate_episode=lambda *_a,**_kw:self.score()
  self.runner.metric_evidence=self.authority.published.evidence
  import policy_backend
  policy_backend.build_replay_smol_inputs=lambda obs,text,*_a:policy_backend.build_smol_inputs(obs,text)
  # Retain typed memory across user pause/resume without resetting the world.
  orig_points=self.points_class
  class GatewayPoints(orig_points):
   def observe(p,image,frame,time_source='current',camera_id=None):
    if time_source!='current'and any(k[0]==time_source for k in p.memory):return
    if time_source=='current'and frame>p.scene.frame:p.update_evidence(frame,{},bridge.cache_reader.memory_camera_id())
    return super(GatewayPoints,p).observe(image,frame,time_source,camera_id)
   def update_evidence(p,frame,facts,camera):
    if frame<p.scene.frame:return
    actual={}if bridge.physics_steps>0 else facts
    return super(GatewayPoints,p).update_evidence(frame,actual,camera)
   def begin_instruction(p,image,frame):
    if bridge.generation>1:return # same-task resume; takeover memory is immutable
    if bridge.engine_start_step>p.scene.frame:p.update_evidence(bridge.engine_start_step,{},bridge.cache_reader.memory_camera_id())
    return super(GatewayPoints,p).begin_instruction(image,bridge.engine_start_step)
   def bind(p,decision,frame):
    text,marker=super(GatewayPoints,p).bind(decision,frame)
    marker['legacy_engine_age_clock']=marker.get('age_clock');marker['age_clock']='authorized_control_steps; async physics clock logged separately'
    marker['current_physics_step']=bridge.physics_steps
    return text,marker
  def points_factory(*a,**kw):
   if self.saved_points is None:self.saved_points=GatewayPoints(*a,**kw)
   else:
    import shutil
    folder=Path(a[0]);folder.mkdir(parents=True,exist_ok=True)
    for pattern in ('*_episode_start.png','*_instruction_takeover.png'):
     for image in self.saved_points.folder.glob(pattern):shutil.copyfile(image,folder/image.name)
    self.saved_points.folder=folder;self.saved_points.scene.path=folder/'memory_events.jsonl'
   return self.saved_points
  self.runner.Points=points_factory
  def mon_factory(*a,**kw):
   if self.saved_mon is None:self.saved_mon=self.mon_class(*a,**kw)
   else:
    self.saved_mon.active=None;self.saved_mon.events=copy.deepcopy(self.approved_events)
    # Task takeover K2 is new, episode-start K2 remains immutable. This is typed
    # point memory, never simulator object pose or a next-stage answer.
    self.saved_mon.history=copy.deepcopy(kw.get('history',self.saved_mon.history))
   if not getattr(self.saved_mon,'_g21_capture_installed',False):
    mon=self.saved_mon;original_select=mon.select
    def select(stage):
     self.capture_stage_context(mon,stage)
     return original_select(stage)
    mon.select=select;mon._g21_capture_installed=True
   return self.saved_mon
  self.runner.ObservedCompletion=mon_factory
  original_verifier=self.runner.VisualVerifier
  class GatewayVerifier(original_verifier):
   def configure(v,episode_main,takeover_main,takeover_wrist,user_message):
    if not hasattr(bridge,'original_takeover_images'):bridge.original_takeover_images=(copy.deepcopy(takeover_main),copy.deepcopy(takeover_wrist))
    return super(GatewayVerifier,v).configure(episode_main,*bridge.original_takeover_images,user_message)
  self.runner.VisualVerifier=GatewayVerifier
  original_observed_states=self.runner.__dict__.get('ObservedStateMemory')
  from observed_state_memory import ObservedStateMemory
  from planning_relation_memory import PlanningRelationMemory
  import observed_state_memory,planning_relation_memory
  def state_memory(*a,**kw):
   if self.saved_observed_states is None:self.saved_observed_states=ObservedStateMemory(*a,**kw)
   return self.saved_observed_states
  def relations(*a,**kw):
   if self.saved_relations is None:self.saved_relations=PlanningRelationMemory(*a,**kw)
   return self.saved_relations
  observed_state_memory.ObservedStateMemory=state_memory;self.runner.PlanningRelationMemory=relations
  def recovery_factory(*a,**kw):
   Path(a[0]).mkdir(parents=True,exist_ok=True)
   if self.saved_recovery is None:self.saved_recovery=self.recovery_class(*a,**kw)
   return self.saved_recovery
  self.runner.RecoveryRuntime=recovery_factory
  # History reconstruction is setup-only, not a reset of the live environment.
  import episode_history
  oldhistory=episode_history.load_initial_object_history;self.history=None
  def history(*a,**kw):
   # The episode journal and initial RGB-D are already captured by the owner.
   if self.history is None:
    self.history=dict(source='live_observed_episode_memory',episode_id=self.state.episode,
     camera_transform_id=self.saved_points.camera_id,facts={},render_image_mae=0.,seconds=0.,
     initial_observed_rgbd_file=getattr(self,'initial_observed_rgbd_file',None))
   return self.history
  episode_history.load_initial_object_history=history
 def start(self,client,resume=False):
  if self.thread and self.thread.is_alive():raise RuntimeError('Previous kernel still active')
  self.generation+=1
  self.engine_start_step=max(self.control_steps,(getattr(self.saved_mon,'last',-1)+1)if resume else 0,(getattr(getattr(self.saved_points,'scene',None),'frame',-1)+1)if resume else 0)
  self.worker_done.clear();self.kernel_result=None;self.kernel_error=None;self.last_token=self.token();self.io=None
  root=self.root/'kernels'/('g%03d'%self.generation)
  class Client:
   def get_server_metadata(_):return client.get_server_metadata()
   def infer(_,req):
    wire=copy.deepcopy(req);logical_call=req['evaluation_call_index'];wire['evaluation_call_index']=self.policy_calls_attempted
    if self.policy_calls_attempted>0:wire.pop('evaluation_seed',None)
    self.policy_calls_attempted+=1
    answer=self.network('policy',client.infer,wire)
    answer=dict(answer,evaluation_call_index=logical_call)
    return answer
  import planner
  if not hasattr(self,'planner'):
   self.planner=planner.Planner()
   if __import__('os').environ.get('G21_PROGRESS_GUARD','1')=='1':
    from g21.observed_goal_guard import ADDENDUM
    self.planner.system+='\n'+ADDENDUM
  bridge=self
  class GatewayPlanner:
   def generate(_,inp):
    inp['episode_id']=bridge.state.episode;inp['task_version']=bridge.state.task_intent_revision
    # Only the actual authorized task is forwarded; no private contract.
    inp['user_message']=bridge.state.instruction
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integration'))
    from adapter import F28dExecutionAdapter,Identity
    ident=Identity(bridge.state.episode,bridge.state.task_id,bridge.state.task_intent_revision,bridge.state.version,'kernel',bridge.engine_start_step)
    inp=F28dExecutionAdapter().planner_input(inp,ident)
    from unified.nonoracle_boundary import audit_planner
    audit_planner(inp,bridge)
    return bridge.planner.generate(inp)
  def kernel():
   self.env_lock.acquire()
   try:
    # range offset preserves cumulative authorized action budget on resume.
    result=self.run_function(self.case,GatewayPlanner(),Client(),root,1200+self.engine_start_step)
    self.kernel_result=result
   except KernelRetired:self.kernel_error='retired_generation'
   except EpisodeStopped:self.kernel_error='episode_stopped'
   except BaseException:self.kernel_error=traceback.format_exc()
   finally:
    self.env_lock.release();self.worker_done.set()
  self.thread=threading.Thread(target=kernel,name='f28d-gateway-kernel',daemon=True);self.thread.start();self.log('kernel_started',identity=list(self.last_token),generation=self.generation,resume=resume)
 def build_run_function(self):
  # Only the outer range starts at the preserved control index. Source algorithm,
  # prompts, recovery and model calls are otherwise the frozen formal runner.
  import ast,inspect
  tree=ast.parse(inspect.getsource(self.runner.run));changed=0
  for node in ast.walk(tree):
   if isinstance(node,ast.For)and isinstance(node.target,ast.Name)and node.target.id=='step'and isinstance(node.iter,ast.Call)and isinstance(node.iter.func,ast.Name)and node.iter.func.id=='range':
    node.iter.args=[ast.Attribute(value=ast.Name(id='GATEWAY_BRIDGE',ctx=ast.Load()),attr='engine_start_step',ctx=ast.Load()),ast.Name(id='budget',ctx=ast.Load())];changed+=1
  assert changed==1;ast.fix_missing_locations(tree);namespace=dict(self.runner.__dict__,GATEWAY_BRIDGE=self);exec(compile(tree,str(self.root/'generated_kernel.py'),'exec'),namespace);self.run_function=namespace['run']
  (self.root/'generated_kernel.py').write_text(ast.unparse(tree)+'\n')
 def score(self):
  if not self.measurements:return {}
  return self.authority.extensions.evaluate_episode(dict(measurements=self.measurements,metric_initial=self.initial),self.case,self.contract,self.rules)
 def capture_stage_context(self,mon,stage):
  if not stage.get('operation','').startswith('close_'):return
  folder=self.root/'stage_contexts';folder.mkdir(exist_ok=True)
  stem='g%03d_f%06d_%s'%(self.generation,mon.last,stage['operation']);path=folder/(stem+'.npz')
  if path.exists():return
  context=self.authority.state.capture(self.env)
  context.update(main_raw_image=self.obs['agentview_image'].copy(),wrist_raw_image=self.obs['robot0_eye_in_hand_image'].copy())
  np.savez_compressed(path,**context)
  live=self.worker_context();decision=copy.deepcopy(live.get('decision'))
  meta=dict(case_id=self.case['case_id'],task_instruction=self.state.instruction,stage=copy.deepcopy(stage),decision=decision,observed_state=copy.deepcopy(mon.snapshot),completed_events=copy.deepcopy(mon.events),physics_step=self.physics_steps,control_step=self.control_steps,state_identity=self.authority.state.identity(context),capture_only_no_live_state_restore=True,original_case=self.case)
  path.with_suffix('.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
  self.log('diagnostic_stage_context_saved',operation=stage['operation'],file=str(path),state_identity=meta['state_identity'])
 def commit_acceptance(self,decision):
  if self.terminal_reason or self.state.mode!='running' or tuple(decision['subject'])!=self.token()[:3]:return False
  passed=decision['accepted'] is True;self.terminal_reason=decision['reason'];self.acceptance_decision=copy.deepcopy(decision)
  self.state._hold('completed'if passed else'needs_review','independent_current_contract_terminal')
  self.state.completion_status='verified'if passed else'failed'
  self.state.agent_execution=dict(phase='completed'if passed else'failed',completion_current_verified=passed,source='independent_current_contract_v1',task_id=self.state.task_id,semantic_revision=self.state.task_intent_revision)
  self.state.event('task_completed'if passed else'task_needs_review',dict(benchmark_terminal=decision['reason'],passed=passed,acceptance_schema=decision['schema']))
  self.log('benchmark_terminal',reason=decision['reason'],passed=passed,acceptance=decision)
  return True
 def measure(self,phase):
  sm=self.source.measure();tm=self.target.measure();goal=self.rt.frame(self.target,self.case['target_task']);ev=self.authority.published.evidence(self.env,self.case,self.contract)
  adjusted=bool(goal['goal'])
  for site,x in ev.get('regions',{}).items():adjusted=adjusted or bool(self.runner.region_contains(x,self.rules['target_regions'][site]['margin_m']))
  row=dict(step=len(self.measurements)+1,world_physics_step=self.physics_steps,phase='policy',actual_phase=phase,engine_control_step=self.control_steps,simulation_time=float(self.env.sim.data.time),source=sm,target=tm,goal_frame=goal,metric_evidence=ev,adjusted_goal=adjusted)
  self.measurements.append(row)
  if self.acceptance is None:self.acceptance=CurrentContractAcceptance(self.case,self.contract,self.rules,self.initial,self.score,self.terminal)
  decision=self.acceptance.observe(row,self.token()[:3])
  if decision:self.commit_acceptance(decision)
 def apply(self,action,phase):
  # Caller owns state.lock and env_lock. No other method may step physics.
  if self.state.mode=='paused':raise AssertionError('Hard pause cannot env.step')
  self.obs,_,_,_=self.env.step(np.asarray(action,float).tolist());self.physics_steps+=1;self.state.step=self.physics_steps;self.state.obs=self.obs;self.state.observed_at=time.time();self.capture_monotonic=time.monotonic();self.capture_sim_time=float(self.env.sim.data.time)
  if phase=='async_wait_hold':self.async_hold_steps+=1
  else:self.control_steps+=1
  if phase in('authorized_kernel_control','source_policy'):
   self.log('action_applied'if phase=='authorized_kernel_control'else'native_source_action_applied',identity=list(self.token()),action=np.asarray(action).tolist(),completed_events=self.approved_events)
  self.cache_reader.observe(self.physics_steps)
  if self.scoring_active:self.measure(phase)
  if self.physics_steps%2==0:self.video.append_data(np.concatenate([self.obs['agentview_image'][::-1,::-1],self.obs['robot0_eye_in_hand_image'][::-1,::-1]],axis=1))
 def pump(self,allow_tick=True):
  with self.state.lock:
   if not self.env_lock.acquire(blocking=False):return False
   try:
    if not self.requests.empty():
     r=self.requests.get_nowait()
     if r.method=='action'and not allow_tick and self.state.mode=='running'and not self.terminal_reason:
      self.requests.put(r);return False
     try:
      if r.method=='render':r.value=self.env.sim.render(*r.args,**r.kwargs)
      elif r.method=='action':
       if self.terminal_reason or self.closed:raise EpisodeStopped()
       if self.state.mode!='running'or r.token!=self.token():self.stale_discarded+=1;raise KernelRetired()
       # Snapshot proposed stage/events only after current-generation validation.
       context={}if self.ctx is None else self.ctx.f_locals;mon=context.get('mon');decision=context.get('decision')
       if mon is not None:self.approved_events=copy.deepcopy(mon.events)
       self.state.queue=[(self.state.version,np.asarray(r.args[0],float))];action=self.state.next_action();assert action is not None
       self.apply(action,'authorized_kernel_control');r.value=(copy.deepcopy(self.obs),0.,False,{})
       if decision and self.state.mode=='running'and not self.terminal_reason:self.state.agent_execution=dict(phase='executing',generation=self.generation,operation=decision['remaining_plan'][0]['operation'],subgoal=decision['current_subgoal_template'],planner_backend='F28d-local-four-roles')
      else:raise ValueError(r.method)
     except BaseException as e:r.error=e
     finally:r.done.set()
     return r.method=='action'
    if allow_tick and self.io and self.state.mode=='running'and not self.terminal_reason:
     self.apply(self.pose.action(self.obs),'async_wait_hold');return True
    return False
   finally:self.env_lock.release()
 def close(self):
  self.closed=True
  deadline=time.monotonic()+305
  while self.thread and self.thread.is_alive()and time.monotonic()<deadline:
   self.pump(False);self.thread.join(.02)
  self.video.close()
