"""Literal ASR actor, one physics owner, and separated benchmark-only telemetry.

No planner, YOLO, memory manager, semantic router, or speech synthesis is loaded.
Every nonempty finalized transcript replaces conditioning, including questions,
negations and stop requests. Fixture gates and final scoring never write text.
"""
import argparse,concurrent.futures,copy,hashlib,importlib.util,io,json,os,queue,signal,sqlite3,sys,threading,time,uuid
from collections import deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from sim_support import configure,build_env,policy_observation,PoseHold
from action_commit import select_actions

R=Path(__file__).resolve().parents[1]
W=Path('/mnt/disk_4/geyi/audio_switch_benchmark/runtimes/c3r_pi05_744_30k_r15_20261108/runtime')
GOALS=['open_middle','bowl_stove','bottle_cabinet','bowl_drawer','bowl_cabinet','push_plate','cheese_bowl','turn_on_stove','bowl_plate','bottle_rack']
OBJECT={1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',5:'plate',6:'cheese',8:'bowl',9:'wine_bottle'}

def jsonable(x):
 if hasattr(x,'tolist'):return x.tolist()
 if hasattr(x,'item'):return x.item()
 raise TypeError(type(x).__name__)
def write(p,v):
 p=Path(p);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(v,indent=2,default=jsonable));q.replace(p)

def call_policy(url,obs,text,episode,index,seed):
 import urllib.request
 inp=policy_observation(obs);metadata=dict(conditioning_mode=('symbolic'if 'Coordinates:'in text else'complete_task'),prompt=text,evaluation_case_id=episode,evaluation_call_index=index)
 if index==0:metadata['evaluation_seed']=seed
 payload=io.BytesIO();np.savez(payload,**inp,metadata=json.dumps(metadata));started=time.monotonic()
 request=urllib.request.Request(url+'/infer',data=payload.getvalue(),headers={'Content-Type':'application/octet-stream'})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=120)as f:v=json.load(f)
 if v.get('effective_prompt_sha256')!=hashlib.sha256(text.encode()).hexdigest()or v.get('conditioning_mode')!=metadata['conditioning_mode']:raise ValueError('Policy changed actual conditioning')
 audit=os.environ.get('COMMON_CASE_OUTPUT')
 if audit:
  with(Path(audit)/'policy_transport.jsonl').open('a')as af:af.write(json.dumps(dict(case_id=episode,call_index=index,seed=metadata.get('evaluation_seed'),requested_prompt_sha256=hashlib.sha256(text.encode()).hexdigest(),effective_prompt_sha256=v['effective_prompt_sha256'],conditioning_mode=v['conditioning_mode']))+'\n')
 actions=np.asarray(v['actions']);assert actions.shape==(10,7)and np.isfinite(actions).all()
 return v,inp,time.monotonic()-started

class State:
 def __init__(self):
  self.lock=threading.RLock();self.episode=uuid.uuid4().hex;self.task_id=None;self.version=0;self.task_intent_revision=0;self.mode='idle';self.instruction='';self.step=0;self.action_steps=0;self.policy_action=False;self.completion_status={};self.last_error=None;self.failure_detail=None;self.scene_memory_status=dict(state='disabled');self.queue=[]

class Engine:
 def __init__(self,a):
  self.a=a;self.root=a.out;self.spec=json.loads(a.spec.read_text());self.family=self.spec['evaluation_family'];self.state=State();self.events=[];self.tasks=[];self.q=queue.Queue();self.env_lock=threading.RLock();self.stopping=False;self.errors=[];self.last=None;self.public=None;self.task_count=0;self.physics_steps=0;self.control_steps=0;self.task_start_control=0;self.task_started=None;self.native=None;self.thread=None;self.io=None;self.saved_points=None;self.scoring_active=False;self.fixture_hold=False;self.fixture_used=False;self.source_phase_streak=0;self.source_window_ready=False;self.terminal_hold_ticks=0;self.hold_remaining=0;self.publication_sequence=0;self.inflight=None;self.buffer=[];self.bootstrap=True;self.call_index=0;self.finish_requested=False
  self.root.mkdir(parents=True,exist_ok=True);(self.root/'policy_inputs').mkdir(exist_ok=True);(self.root/'voice/sessions').mkdir(parents=True,exist_ok=True)
  self.logfile=(self.root/'gateway.jsonl').open('w',buffering=1);self.eventfile=(self.root/'task_events.jsonl').open('w',buffering=1)
  (self.root/'gateway').mkdir(exist_ok=True);self.db=sqlite3.connect(self.root/'gateway/episodes.sqlite');self.db.execute('CREATE TABLE events (id TEXT, episode TEXT, time REAL, kind TEXT, version INTEGER, payload TEXT)');self.db.commit()
  self.env,self.obs=build_env(Path('/'),self.spec['fixture'],self.root)
  sys.path[:0]=[str(W/'freeze/f28d/source'),str(W/'freeze/authority_src'),str(W/'freeze/simulation/geometry'),str(W/'vendor/support/metrics'),str(R/'adapter/evaluator_v2'),'/mnt/disk_4/geyi/audio_switch_benchmark/T1/current/adapter/judge']
  # Read-only v2.5 observer. Never select a stage; no values enter call_policy.
  m=importlib.util.spec_from_file_location('pure_benchmark_observer',W/'freeze/f28d/source/completion.py');module=importlib.util.module_from_spec(m);m.loader.exec_module(module)
  xyz={n:self.env.sim.data.body_xpos[self.env.env.obj_body_id[n]].tolist()for n in ['akita_black_bowl_1','cream_cheese_1','wine_bottle_1','plate_1']}
  self.cache_reader=module.Completion(self.env,xyz,self.spec.get('source_task',0),'');self.cache_reader.latest_rows={};self.rules=self.cache_reader.rules
  self.case=dict(initial_xyz=xyz,target_task=self.spec.get('source_task',0))
  self.pose=PoseHold(self.obs,self.env.env.robots[0].controller);self.pool=concurrent.futures.ThreadPoolExecutor(1)
  directory=self.root/'recordings'/self.state.episode;directory.mkdir(parents=True)
  self.tickfile=(directory/'control_ticks.jsonl').open('w',buffering=1);self.physicalfile=(self.root/'physical.jsonl').open('w',buffering=1);self.observations=(directory/'observations.jsonl').open('w',buffering=1);self.pausefile=(self.root/'pause_observations.jsonl').open('w',buffering=1)
  import imageio.v2 as imageio
  self.video=imageio.get_writer(str(directory/'environment.mp4'),fps=10,codec='libx264',quality=6,macro_block_size=None,ffmpeg_params=['-threads','1'])
  self.inputvideo=imageio.get_writer(str(self.root/'policy_input.mp4'),fps=20/3,codec='libx264',quality=6,macro_block_size=None,ffmpeg_params=['-threads','1'])
  self.t4_recorder=None;self.recent=deque(maxlen=12);self.final_events={};self.predecessor_native_seen=False;self.expired_consecutive=0;self.expired_total=0
  if self.family=='T4':
   from t4_private_evidence import TickRecorder
   self.t4_recorder=TickRecorder(self,xyz,self.spec)
   # Use our single file/row writer, retaining the original predicate function.
   self.t4_recorder.stream.close();self.t4_recorder.stream=None
  from entryfix.support import augmented
  mon=self.cache_reader.mon['cheese'];raw_measure=mon.measure;mon.measure=lambda:augmented(mon,raw_measure())
  self.record('initial_observation',False)
  self.t6=None
  if self.family=='T6':
   from t6_eval import Evaluator
   self.t6=Evaluator(self,self.state,self.spec,self.root)
  self.common_prefix=None
  if self.family=='T3'and self.spec.get('t3_prepare_mode')=='replay':
   from prepare_source import SourcePreparer
   self.common_prefix=SourcePreparer(self)
  self.publish();write(self.root/'READY.json',self.public)

 def token(self):return self.state.episode,self.state.task_id,self.state.version,self.state.task_intent_revision
 def log(self,kind,**kw):
  row=dict(kind=kind,time=time.time(),monotonic=time.monotonic(),**kw);self.logfile.write(json.dumps(row,default=jsonable)+'\n');return row
 def event(self,kind,**kw):
  e=dict(id=len(self.events)+1,kind=kind,time=time.time(),monotonic=time.monotonic(),**kw);self.events.append(e);self.eventfile.write(json.dumps(e,default=jsonable)+'\n');self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',(str(e['id']),self.state.episode,e['time'],kind,self.state.version,json.dumps(e,default=jsonable)));self.db.commit();return e
 def state_hash(self):
  h=hashlib.sha256()
  for x in [self.env.sim.data.qpos,self.env.sim.data.qvel,np.asarray([self.env.sim.data.time])]:h.update(np.asarray(x).tobytes())
  return h.hexdigest()
 def record(self,phase,stepped):
  s=self.state;self.cache_reader.observe(self.physics_steps);p=self.cache_reader.snapshot;rows={k:dict(v[-1])for k,v in self.cache_reader.windows.items()if v};self.cache_reader.latest_rows=rows
  extra={}
  try:extra['cheese_stove']=bool(self.env.env._eval_predicate(['on','cream_cheese_1','flat_stove_1_cook_region']))
  except (KeyError,ValueError,AttributeError):extra['cheese_stove']=None
  robot=self.cache_reader.mon['bowl'].robot_geoms
  for label,body in [('cabinet_robot_contact','wooden_cabinet_1'),('stove_robot_contact','flat_stove_1')]:
   bid=int(self.env.env.obj_body_id[body]);bodies=set()
   for j in range(self.env.sim.model.nbody):
    parent=j
    while parent>0 and parent!=bid:parent=int(self.env.sim.model.body_parentid[parent])
    if parent==bid:bodies.add(j)
   gs={j for j in range(self.env.sim.model.ngeom)if int(self.env.sim.model.geom_bodyid[j])in bodies}
   extra[label]=any(c.dist<=.001 and((int(c.geom1)in gs and int(c.geom2)in robot)or(int(c.geom2)in gs and int(c.geom1)in robot))for c in self.env.sim.data.contact[:self.env.sim.data.ncon])
  now=time.monotonic();self.last=dict(time=time.time(),monotonic=now,episode_id=s.episode,step=self.physics_steps,simulation_time=float(self.env.sim.data.time),task_id=s.task_id,version=s.version,mode=s.mode,phase=phase,policy_action=stepped and phase=='source_policy',policy_actions=self.control_steps,control_step=self.control_steps,physical=copy.deepcopy(p),measurements=rows,episode_initial_positions=self.case['initial_xyz'],proprioception={k:self.obs[k].tolist()for k in ['robot0_eef_pos','robot0_eef_quat','robot0_gripper_qpos']},evaluator_extra=extra,task_count=self.task_count,task_started=self.task_started,state_hash=self.state_hash(),fixture_hold=self.fixture_hold,source_phase_reached=self.source_window_ready,hold_remaining=self.hold_remaining,route='agent_'+getattr(self,'route','unknown'),kernel_error=s.last_error)
  if self.family=='T4':
   from t4_private_evidence import contact_facts,source_ready
   self.last['private_fixture']=contact_facts(self,self.spec);self.t4_recorder.recent.append(self.last)
   if self.task_count==1 and not self.fixture_used and source_ready(self.t4_recorder.recent,self.spec):self.freeze_fixture('original_Easy10_predicate')
  self.last['physics_tick']=bool(stepped)
  self.recent.append(self.last)
  line=json.dumps(self.last,default=jsonable)+'\n';self.tickfile.write(line);self.physicalfile.write(line)
  if self.physics_steps%4==0:self.observations.write(json.dumps(dict(time=self.last['time'],episode_id=s.episode,step=self.physics_steps,task_id=s.task_id,version=s.version,mode=s.mode,instruction=s.instruction,completion=s.completion_status,policy_actions=self.control_steps,physical=p),default=jsonable)+'\n')
  if self.physics_steps%2==0:self.video.append_data(np.concatenate([np.ascontiguousarray(self.obs[k][::-1,::-1])for k in ['agentview_image','robot0_eye_in_hand_image']],axis=1))
  if self.family=='T3'and self.task_count==1 and not self.fixture_used and self.source_ready_t3():self.freeze_fixture('original_T3_causal_source_predicate')
  self.publication_sequence+=1

 def source_ready_t3(self):
  t=self.last;p=t['physical'];phase=self.spec.get('phase');source=self.spec['source_task'];obj=OBJECT.get(source)
  if self.spec.get('t3_prepare_mode')=='replay':return False
  if not t['policy_action']or not self.state.task_id or p['native_goal_relations'][GOALS[source]]:return False
  if phase in ['M0','P0']:return p['held_object']=='none'and not p['objects'][obj]['robot_contact']
  if phase=='K0':return p['held_object']=='none'and abs(t['measurements']['bowl']['articulation']['stove']-self.initial_stove)<1e-4
  if phase=='D1':return abs(t['measurements']['bowl']['articulation']['middle'])>self.rules['close']['gap_m']and not p['drawers']['middle']['open']
  if phase in ['M2','C4']:return p['held_object']==obj and not p['objects'][obj]['supported']and(phase!='C4'or p['drawers']['top']['open'])
  if phase=='C0':return p['held_object']=='none'and not p['objects']['bowl']['robot_contact']and abs(t['measurements']['bowl']['articulation']['top'])<=self.rules['close']['gap_m']and t['evaluator_extra']['cabinet_robot_contact']is False
  return False
 def freeze_fixture(self,reason):
  self.fixture_hold=True;self.fixture_used=True;self.source_window_ready=True;self.source_phase_streak=5;self.buffer=[];self.pose=PoseHold(self.obs,self.env.env.robots[0].controller);self.log('private_source_fixture_window',reason=reason,not_a_model_capability=True)

 def publish(self):
  s=self.state;current=None if not s.task_id else dict(task_id=s.task_id,instruction=s.instruction,version=s.version,state=s.mode,action_steps=self.control_steps-self.task_start_control)
  self.public=dict(ready=True,state=s.mode,mode=s.mode,episode_id=s.episode,reset_count=1,task_id=s.task_id,task_version=s.version,task_intent_revision=s.task_intent_revision,version=s.version,instruction=s.instruction,task=current,action_steps=self.control_steps-self.task_start_control,step=self.physics_steps,observation_time=time.time(),completion_status=s.completion_status,last_error=s.last_error,failure_detail=s.failure_detail,execution_profile='raw_transcript_direct_pi05',runtime_revision='asr-direct-T2-T8-v1',execution_kernel='literal_transcript',policy_metadata=self.metadata,execution_budget=dict(authorized_control_steps=self.control_steps-self.task_start_control,control_limit=1200),pending_clarification=None,pending_proposal=None,deferred_task=None,scene_memory_status=dict(state='disabled'),execution_readiness=dict(ready=True,policy_ready=True,phase='ready'),t4_evaluation_adapter='original_Easy10_predicates_baseline_transport_only'if self.family=='T4'else None)
 def inspect(self):
  t=copy.deepcopy(self.last);return dict(sample=t,physics_step=t['step'],control_step=t['policy_actions'],task_elapsed_s=0 if self.task_started is None else max(0,time.monotonic()-self.task_started),simulation_time=t['simulation_time'],physical_state_sha256=t['state_hash'],mode=self.state.mode,task_id=self.state.task_id,task_count=self.task_count,fixture_hold=self.fixture_hold,source_phase_reached=self.source_window_ready,hold_remaining=self.hold_remaining,route='agent_'+getattr(self,'route','unknown'),kernel_error=self.state.last_error)
 def evaluator_status(self):
  x=self.inspect();x.update(publication_sequence=self.publication_sequence,source_window_ready=self.source_window_ready,source_window=self.source_window_ready,terminal_hold_ticks=self.terminal_hold_ticks,task_control_steps=self.control_steps-self.task_start_control,published_monotonic=time.monotonic(),episode_id=self.state.episode,task_version=self.state.version,task_intent_revision=self.state.task_intent_revision,io_role='policy'if self.inflight else None);return x

 def accept(self,text,source,asr=None):
  if not isinstance(text,str)or not text.strip():return dict(accepted=False,reason='empty_transcript')
  s=self.state;s.version+=1;s.task_intent_revision+=1;s.task_id=uuid.uuid4().hex;s.instruction=text;s.mode='running';s.completion_status={};s.last_error=None;s.failure_detail=None
  self.task_count+=1;self.task_start_control=self.control_steps;self.task_started=time.monotonic();self.buffer=[];self.bootstrap=True;self.pose=PoseHold(self.obs,self.env.env.robots[0].controller);self.fixture_hold=False;self.streak=0
  row=dict(task_id=s.task_id,instruction=text,version=s.version,accepted_at=time.time(),source=source);self.tasks.append(row);self.event('task_instruction',task_id=s.task_id,instruction=text,version=s.version,source=source)
  self.log('agent_authorized_conditioning_updated',identity=list(self.token()),prompt=text,agent_authored=True)
  # Benchmark budget phase selection is scorer-only and never changes text.
  self.case['target_task']=self.spec.get('source_task',0)if self.task_count==1 and self.family in ['T2','T3','T4','T7','T8']else self.spec.get('target_task',999)
  return dict(accepted=True,task_id=s.task_id,version=s.version,prompt=text)
 def apply(self,action,phase):
  self.obs,_,_,_=self.env.step(np.asarray(action,float).tolist());self.physics_steps+=1
  if phase=='source_policy':self.control_steps+=1;self.pose=PoseHold(self.obs,self.env.env.robots[0].controller)
  self.state.step=self.physics_steps;self.state.action_steps=self.control_steps;self.record(phase,True)
  if phase=='source_policy':self.log('action_provenance',identity=list(self.token()),actual_vla_action=True,step=self.physics_steps);self.log('action_applied',identity=list(self.token()),step=self.physics_steps)
  return self.obs

 def final_contract_ready(self,native):
  """Private final-stop guard only; never returns a stage to the actor."""
  c=self.spec.get('independent_termination_contract',{});p=self.cache_reader.snapshot
  if self.family=='T7':
   predecessor=c.get('predecessor_task_id')
   if isinstance(predecessor,int)and p['native_goal_relations'][GOALS[predecessor]]:self.predecessor_native_seen=True
   return native and(self.task_count==1 or self.predecessor_native_seen)
  if self.family!='T3'or self.task_count<2:return native
  for clause in c.get('clauses',[]):
   kind=clause['kind'];cid=clause['id'];ok=False
   if kind=='native_target':ok=native
   elif kind=='close_event':ok=p['drawers'][clause['joint']]['closed_confirmed']
   elif kind=='restore_episode_start':
    obj=clause.get('object');obj={'akita_black_bowl_1':'bowl','cream_cheese_1':'cheese','wine_bottle_1':'wine_bottle','plate_1':'plate'}.get(obj,obj)
    ok=p['objects'].get(obj,{}).get('returned_and_released')is True
   elif kind=='completion_order':continue
   elif kind in ['preserve_position','preserve_articulation_state','preserve_containment']:continue
   else:return False
   if ok:self.final_events.setdefault(cid,self.physics_steps)
  for clause in c.get('clauses',[]):
   if clause['kind']=='completion_order':
    before=self.final_events.get(clause['before']);after=self.final_events.get(clause['after'])
    if before is None or after is None or before>=after:return False
   elif clause['kind']not in ['preserve_position','preserve_articulation_state','preserve_containment']and clause['id']not in self.final_events:return False
  return native

 def handle_commands(self):
  while True:
   try:body,done=self.q.get_nowait()
   except queue.Empty:break
   try:
    op=body['op']
    if op=='condition':v=self.accept(body['text'],'literal_asr_transcript',body.get('asr_event'))
    elif op=='finish':self.finish_requested=True;v=dict(accepted=True);self.stopping=True
    elif op=='hold':self.hold_remaining=40;v=dict(accepted=True)
    elif op=='release_window':self.fixture_hold=False;v=dict(accepted=True)
    elif op=='fixture_pause':
     if self.family!='T4'or not self.source_window_ready:raise ValueError('not_a_ready_T4_fixture')
     self.state.mode='paused';self.buffer=[];v=dict(accepted=True,status='accepted',state='paused',episode_id=self.state.episode,task_id=self.state.task_id,task_version=self.state.version,task_intent_revision=self.state.task_intent_revision,source='benchmark_common_fixture_not_model_pause')
    elif op=='t6':v=self.t6.query(body['body'])
    elif op=='setup_tool':
     if self.family!='T6':raise ValueError('typed_setup_only_for_frozen_T6_preparation')
     name=body['body']['name']
     if name=='robot_start_task':v=self.accept(body['body']['args']['instruction'],'benchmark_T6_controlled_setup')
     elif name=='robot_cancel_task':self.state.mode='cancelled';self.buffer=[];v=dict(accepted=True)
     else:raise ValueError('no_such_setup_operation')
    else:raise ValueError('unknown_operation')
    self.publish();done.put((200,v))
   except Exception as e:done.put((409,dict(error=str(e))))

 def run(self):
  s=self.state;tick=time.monotonic();self.streak=0;self.initial_stove=self.last['measurements']['bowl']['articulation']['stove'];started=time.monotonic()
  try:
   while not self.stopping and time.monotonic()-started<self.spec.get('service_lifetime_s',2100):
    self.handle_commands();now=time.monotonic()
    if self.inflight is not None and self.inflight.done()and not self.buffer:
     response,inp,elapsed=self.inflight.result();idx,ver,frame,prompt,identity=self.pending
     try:selected,offset=select_actions(response['actions'],self.bootstrap,self.physics_steps-frame)if ver==s.version and s.mode=='running'and not self.fixture_hold else([],None)
     except ValueError as e:
      if str(e)!='prediction_horizon_expired':raise
      selected=[];offset=self.physics_steps-frame;self.expired_consecutive+=1;self.expired_total+=1;self.log('expired_action_chunk_discarded',call=idx,elapsed_world_frames=offset,consecutive=self.expired_consecutive,rule='never_apply_past_horizon; take_new_observation_on_next_loop')
      if self.expired_consecutive>=10:raise RuntimeError('ten_consecutive_expired_action_chunks')
     else:
      if selected:self.expired_consecutive=0
     if ver==s.version:self.buffer=selected;self.bootstrap=False
     self.log('executor_output',identity=identity,request_sha256=hashlib.sha256((str(idx)+prompt).encode()).hexdigest(),action_count=10,roundtrip_s=elapsed,stale=ver!=s.version,aligned_offset=offset)
     np.savez_compressed(self.root/'policy_inputs'/f'{idx:05d}.npz',**inp,prompt=prompt);self.inputvideo.append_data(np.concatenate([inp['image'],inp['wrist']],axis=1));self.inflight=None
    active=s.mode=='running'and bool(s.instruction)and not self.fixture_hold
    if active and self.inflight is None:
     captured={k:v.copy()if isinstance(v,np.ndarray)else v for k,v in self.obs.items()};self.pending=(self.call_index,s.version,self.physics_steps,s.instruction,list(self.token()));self.log('executor_input',identity=list(self.token()),prompt=s.instruction,policy_call_index=self.call_index,request_sha256=hashlib.sha256((str(self.call_index)+s.instruction).encode()).hexdigest());self.inflight=self.pool.submit(call_policy,self.a.policy,captured,s.instruction,s.episode,self.call_index,int(self.spec.get('policy_seed',7)));self.call_index+=1
    if now<tick:time.sleep(min(.005,tick-now));continue
    tick=max(tick+.05,now+.05)
    if self.t6 and self.t6.pending:self.t6.service();self.publish();continue
    if s.mode=='paused':
     self.publication_sequence+=1;self.publish();continue
    control=active and bool(self.buffer)and not self.hold_remaining
    action=self.buffer.pop(0)if control else self.pose.action(self.obs)
    phase='source_policy'if control else'evaluator_terminal_hold'if self.hold_remaining else'async_wait_hold'
    self.apply(action,phase)
    if self.hold_remaining:self.hold_remaining-=1;self.terminal_hold_ticks+=1
    # Final-only stop on current benchmark goal. This never advances subgoals.
    goal=self.case['target_task'];has_goal=isinstance(goal,int)and 0<=goal<10
    value=has_goal and self.cache_reader.snapshot['native_goal_relations'][GOALS[goal]]
    obj=OBJECT.get(goal)
    if obj and value:
     row=self.cache_reader.windows[obj][-1];value=bool(row['support_contact']and not row['target_contact']and abs(self.obs['robot0_gripper_qpos'][0]-self.obs['robot0_gripper_qpos'][1])>=.04)
    value=self.final_contract_ready(value)
    self.streak=self.streak+1 if active and value else 0
    if self.streak>=5:
     s.mode='completed';s.completion_status=dict(status='final_benchmark_goal_candidate',source='independent_final_only_observer');self.buffer=[];self.event('task_completed',task_id=s.task_id,instruction=s.instruction,source='independent_final_only_observer');self.hold_remaining=40;self.terminal_hold_ticks=0
    budget_path=self.root/'request_budget.json'
    cumulative=self.control_steps-self.task_start_control
    if self.family in ['T2','T8']:cumulative=self.control_steps
    if budget_path.exists():
     b=json.loads(budget_path.read_text());cumulative=self.control_steps-b['start_control']
    if active and(cumulative>=int(self.spec.get('task_control_budget',1200))or(now-self.task_started>=600)):
     s.mode='budget_exhausted';self.buffer=[];self.event('task_budget_exhausted',task_id=s.task_id,action_steps=cumulative);self.hold_remaining=40
    t2budget=self.root/'budget.json'
    if active and self.family=='T2'and t2budget.exists()and now>json.loads(t2budget.read_text())['original_goal_deadline_monotonic']:s.mode='budget_exhausted';self.buffer=[]
    self.publish()
  except BaseException as e:
   import traceback;traceback.print_exc();self.errors.append(repr(e));s.mode='error';s.last_error=repr(e);self.publish();write(self.root/'ENGINE_ERROR.json',dict(error=repr(e),traceback=traceback.format_exc()))
  finally:
   self.pool.shutdown(wait=True);self.video.close();self.inputvideo.close()
   for f in [self.tickfile,self.physicalfile,self.observations,self.pausefile,self.logfile,self.eventfile]:f.close()
   self.db.close();self.env.close();write(self.root/'ENGINE_FINISHED.json',dict(episode_id=s.episode,task_count=self.task_count,policy_actions=self.control_steps,physics_steps=self.physics_steps,errors=self.errors,formal_model='pure_ASR_pi05',final=self.public))

def main():
 p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--gpu',type=int,default=6);p.add_argument('--policy',default='http://127.0.0.1:49441');a=p.parse_args();configure(a.out,a.gpu)
 import urllib.request
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(a.policy+'/metadata',timeout=10)as f:metadata=json.load(f)
 assert metadata['complete_task_input_supported']is True and metadata['checkpoint_step']==30000 and metadata['trajectories']==744 and metadata['state_dimension']==8 and metadata['action_horizon']==10
 assert metadata['archive_sha256']=='57315913541eb81f40678a75121e15c55c2622bbbe496a75ead7903f61820588' and metadata['normalization_sha256']=='b3a44bb2810436fb62917decaea58bd4d9110255df527dea21e8fd40c960bd84'
 Engine.metadata=metadata;b=Engine(a);token=(R/'private/robot.token').read_text().strip();browser=(R/'private/browser.token').read_text().strip()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def respond(self,code,v):
   raw=json.dumps(v,default=jsonable).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  def auth(self):return self.headers.get('Authorization')in ['Bearer '+token,'Bearer '+browser]
  def do_GET(self):
   path=self.path.split('?')[0]
   if path in ['/status','/api/status']:return self.respond(200,copy.deepcopy(b.public))
   if path in ['/timeline','/api/timeline']:
    from urllib.parse import parse_qs,urlsplit
    after=int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0]);return self.respond(200,dict(events=[e for e in b.events if e['id']>after],episode_id=b.state.episode,next_cursor=len(b.events),has_more=False,reset=False))
   if path in ['/tasks','/api/tasks']:return self.respond(200,dict(tasks=b.tasks,episode_id=b.state.episode))
   if path.startswith('/evaluator/')and not self.auth():return self.respond(401,dict(error='authentication_required'))
   if path=='/evaluator/inspect':return self.respond(200,b.inspect())
   if path=='/evaluator/status':return self.respond(200,b.evaluator_status())
   if path=='/evaluator/t6'and b.t6:return self.respond(200,b.t6.query(dict(op='inspect')))
   return self.respond(404,dict(error='unsupported_endpoint'))
  def do_POST(self):
   if not self.auth():return self.respond(401,dict(error='authentication_required'))
   try:
    n=int(self.headers.get('Content-Length',0));body=json.loads(self.rfile.read(n)or b'{}');path=self.path
    if path=='/conditioning':
     if set(body)-{'text','asr_segment','asr_session','asr_event'}:raise ValueError('unexpected_actor_input')
     command=dict(op='condition',**body)
    elif path in ['/evaluator/finish','/evaluator/hold','/evaluator/release_window','/evaluator/pause']:command=dict(op=path.rsplit('/',1)[-1].replace('pause','fixture_pause'))
    elif path=='/eval/t6'and b.t6:command=dict(op='t6',body=body)
    elif path=='/tool'and b.family=='T6':command=dict(op='setup_tool',body=body)
    else:return self.respond(404,dict(error='no_model_tools'))
    done=queue.Queue(1);b.q.put((command,done));code,value=done.get(timeout=10);return self.respond(code,value)
   except Exception as e:return self.respond(409,dict(error=str(e)))
 server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 def stop(*_):b.stopping=True
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop);b.run();server.shutdown()

if __name__=='__main__':main()
