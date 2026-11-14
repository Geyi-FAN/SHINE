"""General transcript Agent + restricted Oracle; one asynchronous action owner.

Private setup/scoring telemetry stays inside inherited recorder. Agent requests
are constructed from an allowlist, never from the case specification or monitor
snapshot. Only the stage selected by the Agent is checked and reported.
"""
import argparse,re,concurrent.futures,copy,hashlib,io,json,os,queue,signal,sys,threading,time,urllib.request,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import numpy as np
import raw_gateway as base
from agent_backend import generate
from oracle_boundary import public_state,stage_event
from speech_backend import synthesize,prepare as prepare_speech,close as close_speech
R=Path(__file__).resolve().parents[1];base.R=R
CATALOG=json.loads((R/'config/OPERATORS.json').read_text())
AGENT_MODEL=json.loads((R/'config/MODELS.json').read_text())['agent']['model']
NATIVE=dict(open_middle=0,bowl_stove=1,bottle_cabinet=2,bowl_drawer=3,bowl_cabinet=4,push_plate=5,cheese_bowl=6,turn_on_stove=7,bowl_plate=8,bottle_rack=9)

def normalize_decision_typography(decision):
 """Normalize only Task's terminal period; never write a plan or envelope."""
 out=copy.deepcopy(decision)
 if out.get('route')=='symbolic'and isinstance(out.get('complete_task'),str):out['complete_task']=out['complete_task'].rstrip().rstrip('.').rstrip()
 return out

class Engine(base.Engine):
 def __init__(self,a):
  self.history=[];self.agent_memory={};self.agent_events=[];self.stage_events=[];self.stage=None;self.native_skill=None;self.route='none';self.plan=[];self.agent_future=None;self.agent_pending=None;self.agent_queued=False;self.user_revision=0;self.last_asr=0.;self.stage_counter=0;self.last_stage_observed=-1;self.stage_streak=0;self.policy_template=None;self.deferred=None;self.proposal=None;self.clarification=None;self.speech_events=[];self.speech_jobs=[];self.speech_id=0;self.speech_cancel_id=0;self.public_images=None;self.last_task_authorization_revision=-1;self.last_continuation_notice=None;self.physics_pause_latch=False;self.fixture_pause_active=False
  super().__init__(a)
  self.agent_pool=concurrent.futures.ThreadPoolExecutor(1);self.speech_pool=concurrent.futures.ThreadPoolExecutor(1)
  self.user_speaking=False;self.input_ended_at=0.;self.speech_idle_since=time.monotonic();self.playing_speech=set();self.acceptance_speech_gate=None;self.pending_confirmation_id=None
  prepare_speech()
  (self.root/'speech').mkdir(exist_ok=True);self.voice=(self.root/'voice/sessions/agent.jsonl').open('w',buffering=1)
  import oracle_points
  oracle_points.BRIDGE=self;self.points=oracle_points.OraclePoints(self.root/'oracle_points',self.state.episode,0)
  self.points.initialize_episode(np.ascontiguousarray(self.obs['agentview_image'][::-1,::-1]),{},'main256-to224-fixed-v1')
  self.stage_monitor=self.cache_reader.__class__(self.env,self.case['initial_xyz'],self.spec.get('source_task',0),'')
  self.agent_call_count=0;self.format_rejections=0;self.publish()

 def record(self,phase,stepped):
  super().record(phase,stepped)
  if phase!='T3_private_fixed_preparation_not_method_actions'and self.stage and self.stage['status']=='running'and hasattr(self,'stage_monitor'):
   if self.route=='native':
    key=self.native_skill;ok=self.cache_reader.snapshot['native_goal_relations'].get(key)is True;obj=base.OBJECT.get(NATIVE.get(key))
    if obj and ok:
     row=self.cache_reader.windows[obj][-1];ok=row['support_contact']and not row['target_contact']and abs(self.obs['robot0_gripper_qpos'][0]-self.obs['robot0_gripper_qpos'][1])>=.04
    self.stage_streak=self.stage_streak+1 if ok else 0
    event=dict(outcome='completed')if self.stage_streak>=5 else None
   else:
    event=self.stage_monitor.observe(self.physics_steps)
    if event and event['outcome']=='completed'and any(w in str(self.policy_template)for w in ['disengage','gripper clear']):
     if self.last['evaluator_extra'].get('cabinet_robot_contact'):
      # Keep checking this same Agent-selected goal until its explicit clear
      # condition is met. Never select a next operation here.
      self.stage_monitor.active=dict(CATALOG[self.stage['operation']],operation=self.stage['operation']);event=None
   if event:
    status='completed'if event['outcome']=='completed'else'failed';self.stage.update(status=status,confirmed_step=self.physics_steps)
    clean=stage_event(self.stage);self.stage_events.append(clean);self.buffer=[];self.log('oracle_selected_stage_verdict',**clean);self.event('subgoal_completed'if status=='completed'else'subgoal_failed',task_id=self.state.task_id,operation=self.stage['operation'],source='selected_stage_only')
    self.history.append(dict(role='tool',event='selected_stage_verdict',data=clean));self.request_agent('your_selected_current_stage_verdict')

 def publish(self):
  super().publish();self.public.update(runtime_revision='asr-agent-oracle-v1',execution_kernel='GeneralAgent_SelectedStageOracle',execution_profile='native_libero_goal'if self.route=='native'else'symbolic',pending_proposal=self.proposal,pending_clarification=self.clarification,deferred_task=self.deferred,agent_execution=dict(phase='planning'if self.agent_future else'paused'if self.physics_pause_latch or self.state.mode=='paused'else'executing'if self.stage and self.stage['status']=='running'else'waiting',backend=AGENT_MODEL,current_subgoal=self.stage,oracle_selected_stage_only=True),scene_memory_status=dict(state='oracle_typed_references'))
 def snapshot_for_agent(self):
  s=self.state;state=dict(episode_id=s.episode,task_id=s.task_id,version=s.version,mode=s.mode,instruction=s.instruction,robot_state=base.policy_observation(self.obs)['state'].tolist(),step=self.physics_steps,current_stage=self.stage,completed_events=self.stage_events,deferred_task=self.deferred,pending_proposal=self.proposal,pending_clarification=self.clarification)
  return dict(observation=public_state(state),conversation=copy.deepcopy(self.history[-35:]),memory=copy.deepcopy(self.agent_memory),reason=self.agent_pending)
 def voice_log(self,kind,payload):self.voice.write(json.dumps(dict(type=kind,ts=int(time.time()*1000),payload=payload))+'\n')
 def request_agent(self,reason):self.agent_pending=reason;self.agent_queued=True
 def receive_asr(self,body):
  text=body.get('text','')
  if not text.strip():return dict(received=False,reason='empty_transcript')
  self.user_revision+=1;self.last_asr=time.monotonic();self.history.append(dict(role='user',text=text,time=time.time(),asr_segment=body.get('asr_segment')));self.voice_log('transcript.user',dict(text=text));self.log('actual_asr_transcript',text=text,segment=body.get('asr_segment'))
  # Exact, unambiguous safety controls never wait behind a visual planning call.
  # No task interpretation, reference transcript, or benchmark field is used.
  if self.state.task_id and re.fullmatch(r'\s*(?:stop|pause(?: the robot)?)\s*[.!]?\s*',text,re.I):
   self.speech_cancel_id+=1;self.speech_events.append(dict(id=len(self.speech_events)+1,type='cancel',time=time.time()));self.acceptance_speech_gate=None
   self.commit_agent(dict(intent='pause',task_id=self.state.task_id,say='Paused.',origin='controller_exact_safety_command'))
   # The exact safety request is already fulfilled. An extra cloud no_action
   # round-trip would only block a subsequent real resume under concurrency1.
   return dict(received=True,handled_by='exact_safety_controller',text=text)
  elif re.match(r'\s*(?:(?:first|then)[, ]+)?(?:please\s+)?(?:put|place|open|close|return|move|resume|continue|cancel|when|after|yes\s*,?\s*go ahead)\b',text,re.I):
   # A truthful processing receipt, not task acceptance or a claimed plan.
   # It is released through the same real PCM path; later tool receipts remain
   # independently required within the unchanged authorization deadline.
   self.say('Processing your request.','processing');self.log('processing_receipt_queued',asr_segment=body.get('asr_segment'),claim='actual_received_transcript_only_not_task_acceptance')
  self.request_agent('user_transcript');return dict(received=True,handled_by='Agent_with_exact_safety_pause',text=text)
 def say(self,text,kind='reply'):
  if not text:return
  self.speech_id+=1;identity=dict(task_id=self.state.task_id,version=self.state.version,user_revision=self.user_revision,task_intent_revision=self.state.task_intent_revision)
  future=self.speech_pool.submit(synthesize,text,self.root/'speech'/f'{self.speech_id:03d}.wav');self.speech_jobs.append(dict(id=self.speech_id,text=text,future=future,identity=identity,mode=self.state.mode,kind=kind,cancel_generation=self.speech_cancel_id))
  if kind in ['execute','revise']:self.acceptance_speech_gate=self.speech_id
  self.speech_idle_since=time.monotonic()

 def conversation_quiet(self):
  return not getattr(self,'user_speaking',False) and time.monotonic()-getattr(self,'input_ended_at',0)>.8

 def completion_dialogue_ready(self):
  # Physics keeps stepping normally. Only conversational finalization waits
  # for real speech receipts and a bounded, method-wide turn-taking interval.
  return self.conversation_quiet() and not self.speech_jobs and not self.playing_speech and time.monotonic()-self.speech_idle_since>=1.

 def event(self,kind,**kw):
  if kind=='task_instruction'and getattr(self,'pending_confirmation_id',None):kw['confirmed_proposal_id']=self.pending_confirmation_id
  return super().event(kind,**kw)
 def set_stage(self,out):
  route=out.get('route','symbolic');task=out.get('complete_task')or self.state.instruction
  if route=='native':
   key=out.get('native_skill')
   if key not in NATIVE:raise ValueError('unknown_native_skill')
   template=out.get('policy_prompt_template')
   if template!=task:raise ValueError('native_policy_prompt_must_equal_your_complete_task')
   self.native_skill=key;operation=key;self.plan=[dict(operation=key,goal=task)]
  else:
   plan=out.get('remaining_plan')
   if not isinstance(plan,list)or not plan:raise ValueError('symbolic_plan_required')
   for stage in plan:
    if stage.get('operation')not in CATALOG:raise ValueError('unknown_operator')
   operation=plan[0]['operation'];op=CATALOG[operation]
   if out.get('current_subgoal_template')!=op['template']:raise ValueError('copy_exact_template_for_YOUR_chosen_operation: '+op['template'])
   if out.get('reference')!=op['reference']:raise ValueError('reference_does_not_match_YOUR_chosen_operator')
   expected='Task: '+task+'.\nCurrent subgoal: '+op['template']+'.\nCoordinates: MAIN, 224x224, <y,x> pixels.\n'
   if out.get('policy_prompt_template')!=expected:raise ValueError('invalid_envelope_for_YOUR_chosen_operation; required='+expected)
   template=out['policy_prompt_template'];self.plan=plan;self.stage_monitor.select(dict(op,operation=operation));self.native_skill=None
  self.route=route;self.policy_template=template;self.decision=out;self.stage_counter+=1;self.stage=dict(operation=operation,status='running',entered_step=self.physics_steps,task_id=self.state.task_id,version=self.state.version);self.stage_streak=0;self.buffer=[];self.bootstrap=True;self.log('agent_stage_selected',stage=self.stage,reference=out.get('reference'),template=template);self.event('subgoal_started',task_id=self.state.task_id,operation=operation,source='Agent')

 def speech_mode_allows(self,job):
  return job['kind']in ['qa','no_action','clarify','propose','reply','processing']or job['mode']==self.state.mode or(self.fixture_pause_active and self.state.mode=='paused'and job['kind']in ['execute','revise']and job['mode']=='running')

 def agent_response_is_current(self):
  return self.pending_agent_revision==self.user_revision and self.pending_agent_subject==(*self.token(),self.state.mode)

 def speech_identity_is_current(self,job):
  s=self.state;j=job['identity']
  return j['task_id']==s.task_id and j['user_revision']==self.user_revision and(j['version']==s.version or(job['kind']in ['execute','revise','next_stage','amend','defer','replace_deferred','cancel_deferred']and j.get('task_intent_revision')==s.task_intent_revision and not self.physics_pause_latch))

 def commit_agent(self,out):
  original=out;out=normalize_decision_typography(out)
  if out.get('complete_task')!=original.get('complete_task'):self.log('task_typography_normalized',original=original.get('complete_task'),normalized=out.get('complete_task'),no_plan_or_subgoal_generated=True)
  intent=out.get('intent');s=self.state;receipt=dict(intent=intent,accepted=False)
  if intent in ['pause','resume','cancel','finish','next_stage','amend']and out.get('task_id')not in [None,s.task_id]:raise ValueError('current_task_identity_mismatch')
  if intent in ['execute','revise','next_stage','amend']:
   task=out.get('complete_task')or s.instruction
   if out.get('route')=='native':
    if re.search(r'\b(return|restore|close|keep|preserve)\b|back where',task,re.I):raise ValueError('Native route only supports the ten original whole goals; choose symbolic for return/close/preservation requirements')
    if out.get('native_skill')not in NATIVE or out.get('policy_prompt_template')!=task:raise ValueError('invalid_native_skill_or_native_prompt')
   else:
    plan=out.get('remaining_plan')or[]
    if not plan or plan[0].get('operation')not in CATALOG:raise ValueError('choose_a_public_operator')
    op=CATALOG[plan[0]['operation']];expected='Task: '+task+'.\nCurrent subgoal: '+op['template']+'.\nCoordinates: MAIN, 224x224, <y,x> pixels.\n'
    if out.get('current_subgoal_template')!=op['template']or out.get('reference')!=op['reference']or out.get('policy_prompt_template')!=expected:raise ValueError('Use the exact declared template/reference/envelope for YOUR chosen operator: '+json.dumps(dict(current_subgoal_template=op['template'],reference=op['reference'],policy_prompt_template=expected)))
  if 'memory'in out:self.agent_memory=out['memory']
  if intent in ['execute','revise']:
   task=out.get('complete_task')
   if not isinstance(task,str)or not task.strip():raise ValueError('complete_task_required')
   # Validate language before mutating task identity.
   if out.get('route')=='native'and out.get('native_skill')not in NATIVE:raise ValueError('unknown_native_skill')
   consume=out.get('consume_deferred_id')
   last_user=next((v.get('text','')for v in reversed(self.history)if v.get('role')=='user'),'')
   if s.task_id and s.mode in ['running','paused']and not consume and re.match(r'\s*(?:when|after)\b',last_user,re.I):raise ValueError('temporal authorization must bind the actual still-running predecessor with defer; selected-stage completion does not finalize the whole task. Agent must finish it separately before consuming the queued request.')
   if s.task_id and self.user_revision<=self.last_task_authorization_revision and not consume:raise ValueError('no_new_user_authorization; amend the same task for replanning without resetting its budget')
   if consume and(not self.deferred or consume!=self.deferred['deferred_id'] or s.mode!='completed' or self.deferred['predecessor_task_id']!=s.task_id):raise ValueError('deferred_consumption_not_ready_or_wrong_identity')
   if self.proposal and out.get('confirm_proposal_id')!=self.proposal['id']:raise ValueError('explicitly bind confirm_proposal_id to the latest real proposal, or clarify; do not execute an unrelated proposal')
   if self.stage_monitor.active:self.stage_monitor.active=None
   previous=s.instruction;self.stage_monitor.context['previous_instruction']=previous
   confirmation=self.proposal
   if confirmation:
    self.pending_confirmation_id=confirmation['id'];self.event('proposal_resolved',proposal_id=confirmation['id'],decision='confirm',source='Agent_execute_after_actual_proposal')
   old=super().accept(task,'Agent_authorized_task');self.pending_confirmation_id=None;self.physics_pause_latch=False;self.fixture_pause_active=False;self.last_task_authorization_revision=self.user_revision;self.stage_events=[];self.stage=None;self.proposal=None;self.clarification=None
   self.points.begin_instruction(np.ascontiguousarray(self.obs['agentview_image'][::-1,::-1]),self.physics_steps)
   self.hold_remaining=0;self.terminal_hold_ticks=0;self.set_stage(out);receipt.update(old)
   if consume:
    self.event('deferred_consumed',deferred_id=consume,successor_task_id=s.task_id);self.deferred=None
  elif intent=='amend':
   if not s.task_id or s.mode not in ['running','paused']:raise ValueError('no_active_task_to_amend')
   s.instruction=out['complete_task'];s.version+=1
   for task_row in self.tasks:
    if task_row.get('task_id')==s.task_id:task_row['instruction']=s.instruction
   self.stage_monitor.active=None;self.fixture_hold=False;self.hold_remaining=0;self.terminal_hold_ticks=0;self.set_stage(out);self.event('task_updated',task_id=s.task_id,instruction=s.instruction,version=s.version,reason='Agent_selected_continuation');receipt['accepted']=True
  elif intent=='next_stage':
   if not self.stage or self.stage['status']!='completed':raise ValueError('current_stage_not_complete')
   if out.get('task_id')not in [None,s.task_id]:raise ValueError('task_identity_mismatch')
   s.version+=1;self.hold_remaining=0;self.terminal_hold_ticks=0;self.set_stage(out);receipt['accepted']=True
  elif intent=='finish':
   if s.mode=='paused'or self.physics_pause_latch:raise ValueError('task_is_hard_paused; resume before finalizing, do not unpause implicitly')
   if not self.stage or self.stage['status']!='completed':raise ValueError('cannot_finish_unverified_stage')
   s.mode='completed';self.buffer=[];self.hold_remaining=40;self.terminal_hold_ticks=0;s.completion_status=dict(source='Agent_chosen_stage_verified',status='completed');self.event('task_completed',task_id=s.task_id,instruction=s.instruction,source='Agent_after_own_stage_verdict');receipt['accepted']=True
   if self.deferred:self.request_agent('current_task_completed; your_deferred_task_is_pending')
  elif intent=='pause':
   if not s.task_id:raise ValueError('no_current_task')
   s.mode='paused';self.physics_pause_latch=True;self.fixture_pause_active=False;self.agent_queued=False;self.agent_pending=None;self.last_task_authorization_revision=self.user_revision;s.version+=1;self.buffer=[];self.event('task_paused',task_id=s.task_id,reason=out.get('origin','Agent'));receipt['accepted']=True
  elif intent=='resume':
   if s.mode!='paused'or not s.task_id:raise ValueError('no_paused_task')
   s.mode='running';self.physics_pause_latch=False;self.fixture_pause_active=False;self.last_task_authorization_revision=self.user_revision;s.version+=1;self.fixture_hold=False;self.hold_remaining=0;self.terminal_hold_ticks=0;self.buffer=[];self.bootstrap=True;self.event('task_resumed',task_id=s.task_id,reason='Agent');receipt['accepted']=True
  elif intent=='cancel':
   candidate=self.proposal or self.clarification;self.proposal=None;self.clarification=None;self.last_task_authorization_revision=self.user_revision;s.mode='cancelled'if s.task_id else'idle';s.version+=1;self.buffer=[]
   self.event('task_cancelled'if s.task_id else'proposal_cancelled',task_id=s.task_id,proposal_id=None if not candidate else candidate['id']);receipt['accepted']=True
  elif intent in ['propose','clarify']:
   value=dict(id=uuid.uuid4().hex,instruction=out.get('complete_task'),question=out.get('say'),agent_generated=True)
   if intent=='propose':value['proposal_id']=value['id'];self.proposal=value;self.clarification=None;self.event('proposal_created',proposal_id=value['id'],instruction=value['instruction'],source='Agent_propose')
   else:value['clarification_id']=value['id'];self.clarification=value;self.proposal=None
   receipt['accepted']=True
  elif intent in ['defer','replace_deferred']:
   if out.get('task_id')!=s.task_id or s.mode not in ['running','paused']:raise ValueError('deferred_predecessor_identity_not_current')
   if intent=='replace_deferred':
    if not self.deferred:raise ValueError('no_pending_task_to_replace')
    self.event('deferred_invalidated',deferred_id=self.deferred['deferred_id'],reason='replaced_by_user')
   self.deferred=dict(deferred_id=uuid.uuid4().hex,instruction=out.get('complete_task'),predecessor_task_id=s.task_id,agent_generated=True)
   self.event('deferred_scheduled',**self.deferred);receipt['accepted']=True
  elif intent=='cancel_deferred':
   if not self.deferred:raise ValueError('no_pending_task_to_cancel')
   old=self.deferred;self.deferred=None;self.event('deferred_invalidated',deferred_id=old['deferred_id'],reason='user_cancelled');receipt['accepted']=True
  elif intent in ['qa','no_action','stop_speech']:
   if intent=='stop_speech':self.speech_cancel_id+=1;self.speech_events.append(dict(id=len(self.speech_events)+1,type='cancel',time=time.time()))
   receipt['accepted']=True
  else:raise ValueError('unknown_intent')
  self.history.append(dict(role='assistant',decision=out));self.history.append(dict(role='tool',receipt=receipt));self.log('agent_tool_receipt',receipt=receipt,decision=out)
  if receipt['accepted']:
   self.say(out.get('say'),intent)
   # User interaction can supersede an in-flight completion notification.
   # Re-deliver the SAME completed stage, never choose its successor here.
   if s.mode=='running'and self.stage and self.stage['status']=='completed'and intent not in ['finish','next_stage']:
    notice=(s.task_id,s.version,self.user_revision,self.stage['entered_step'])
    if notice!=self.last_continuation_notice:self.last_continuation_notice=notice;self.request_agent('your_completed_stage_still_needs_your_plan_decision_after_interaction')
  return receipt

 def policy_prompt(self):
  if self.route=='native':return self.policy_template
  self.points.observe(np.ascontiguousarray(self.obs['agentview_image'][::-1,::-1]),self.physics_steps)
  text,marker=self.points.bind(self.decision,self.physics_steps);self.log('oracle_position_bound',marker=marker,prompt=text);return text
 def handle_commands(self):
  while True:
   try:body,done=self.q.get_nowait()
   except queue.Empty:break
   try:
    op=body['op']
    if op=='condition':v=self.receive_asr(body)
    elif op=='input_activity':
     self.user_speaking=bool(body['body']['active'])
     if not self.user_speaking:self.input_ended_at=time.monotonic()
     self.log('actual_input_activity',**body['body']);v=dict(accepted=True)
    elif op=='finish':self.stopping=True;v=dict(accepted=True)
    elif op=='hold':self.hold_remaining=40;v=dict(accepted=True)
    elif op=='fixture_pause':
     if self.family!='T4'or not self.source_window_ready:raise ValueError('not_ready_fixture')
     self.state.mode='paused';self.physics_pause_latch=True;self.fixture_pause_active=True;self.agent_queued=False;self.agent_pending=None;self.buffer=[];v=dict(status='accepted',accepted=True,state='paused',episode_id=self.state.episode,task_id=self.state.task_id,task_version=self.state.version,task_intent_revision=self.state.task_intent_revision)
    elif op=='release_window':self.fixture_hold=False;v=dict(accepted=True)
    elif op=='speech_receipt':
     payload=body['body'];self.log('actual_client_speech_receipt',**payload)
     if payload['type']=='host.playback_started':
      sid=payload['outputId'];job=next((j for j in self.speech_events if j.get('outputId')==sid and j.get('type')=='ready'),None)
      if job:
       self.voice_log('transcript.assistant',dict(text=job['text'],responseId=str(sid),receipt_key='tts_'+str(sid),audioSuppressed=False));self.playing_speech.add(sid)
       if self.acceptance_speech_gate==sid:self.acceptance_speech_gate=None;self.log('acceptance_audio_started_action_admitted',output_id=sid)
     if payload['type']in ['host.playback_completed','host.playback_cancelled']:self.playing_speech.discard(payload['outputId']);self.speech_idle_since=time.monotonic()
     v=dict(accepted=True)
    else:raise ValueError('unsupported_endpoint')
    self.publish();done.put((200,v))
   except Exception as e:done.put((409,dict(error=str(e))))

 def run(self):
  s=self.state;tick=time.monotonic();started=time.monotonic();self.initial_stove=self.last['measurements']['bowl']['articulation']['stove']
  try:
   while not self.stopping and time.monotonic()-started<self.spec.get('service_lifetime_s',2100):
    self.handle_commands();now=time.monotonic()
    for job in self.speech_jobs[:]:
     if not job['future'].done():continue
     self.speech_jobs.remove(job)
     try:
      answer=job['future'].result();self.log('tts_completed',**answer)
      current=self.speech_identity_is_current(job)
      mode_ok=self.speech_mode_allows(job)
      if job['cancel_generation']==self.speech_cancel_id and current and mode_ok:
       self.speech_events.append(dict(id=len(self.speech_events)+1,type='ready',outputId=job['id'],text=job['text'],path=answer['path'],samples=answer['samples'],identity=job['identity'],replyKind=job['kind']));self.speech_idle_since=time.monotonic()
      else:
       self.log('stale_speech_discarded',output_id=job['id'],old_identity=job['identity'],current_task=s.task_id,current_version=s.version)
       if self.acceptance_speech_gate==job['id']:self.acceptance_speech_gate=None
     except Exception as e:
      self.log('tts_error',error=repr(e));self.history.append(dict(role='tool',speech_failed=type(e).__name__))
      if self.acceptance_speech_gate==job['id']:self.acceptance_speech_gate=None;s.mode='needs_review';self.buffer=[];s.failure_detail=dict(code='acceptance_speech_failed_no_action_admitted')
    if self.agent_future is not None and self.agent_future.done()and self.conversation_quiet():
     try:
      out,transport=self.agent_future.result();self.log('agent_response',output=out,transport=transport)
      if self.agent_response_is_current():
       try:self.commit_agent(out);self.format_rejections=0
       except ValueError as e:
        self.format_rejections+=1;self.history.append(dict(role='tool',error=str(e)));self.log('agent_validation_rejected',error=str(e));self.request_agent('repair_your_own_output')
        if self.format_rejections>=3:s.mode='needs_review';self.hold_remaining=40;self.terminal_hold_ticks=0;s.failure_detail=dict(code='agent_output_validation_failed');self.agent_queued=False
      else:
       self.log('stale_agent_output_discarded',pending_subject=self.pending_agent_subject,current_subject=(*self.token(),s.mode));self.agent_queued=self.user_revision!=self.pending_agent_revision or self.pending_agent_reason=='user_transcript'
     except Exception as e:s.mode='error';self.hold_remaining=40;self.terminal_hold_ticks=0;s.last_error=repr(e);self.log('agent_provider_error',error=repr(e));self.errors.append(repr(e));self.agent_queued=False
     self.agent_future=None
    if self.agent_queued and self.agent_future is None and now-self.last_asr>=.15 and self.conversation_quiet()and(self.agent_pending in ['user_transcript','repair_your_own_output']or self.completion_dialogue_ready()):
     context=self.snapshot_for_agent();images=[np.ascontiguousarray(self.obs[k][::-1,::-1])for k in ['agentview_image','robot0_eye_in_hand_image']];self.pending_agent_revision=self.user_revision;self.pending_agent_subject=(*self.token(),s.mode);self.pending_agent_reason=self.agent_pending;self.agent_future=self.agent_pool.submit(generate,context,images,self.root/'agent_calls');self.agent_queued=False;self.agent_call_count+=1
    if self.common_prefix is not None and not self.common_prefix.done:
     self.common_prefix.service();self.publish();time.sleep(.005);continue
    if self.inflight is not None and self.inflight.done()and not self.buffer:
     answer,inp,elapsed=self.inflight.result();idx,ver,frame,prompt,identity=self.pending
     try:actions,offset=base.select_actions(answer['actions'],self.bootstrap,self.physics_steps-frame)if ver==s.version and s.mode=='running'and self.stage and self.stage['status']=='running'and not self.fixture_hold else([],None)
     except ValueError as e:
      if str(e)!='prediction_horizon_expired':raise
      actions=[];offset=self.physics_steps-frame;self.expired_total+=1;self.log('expired_action_chunk_discarded',offset=offset)
     if actions:self.buffer=actions;self.bootstrap=False
     self.log('executor_output',identity=identity,request_sha256=hashlib.sha256((str(idx)+prompt).encode()).hexdigest(),action_count=10,roundtrip_s=elapsed,stale=ver!=s.version,aligned_offset=offset);np.savez_compressed(self.root/'policy_inputs'/f'{idx:05d}.npz',**inp,prompt=prompt);self.inputvideo.append_data(np.concatenate([inp['image'],inp['wrist']],axis=1));self.inflight=None
    active=s.mode=='running'and self.stage is not None and self.stage['status']=='running'and not self.fixture_hold and self.acceptance_speech_gate is None
    if active and self.inflight is None:
     try:
      prompt=self.policy_prompt();captured={k:v.copy()if isinstance(v,np.ndarray)else v for k,v in self.obs.items()};self.pending=(self.call_index,s.version,self.physics_steps,prompt,list(self.token()));self.log('executor_input',identity=list(self.token()),prompt=prompt,policy_call_index=self.call_index,request_sha256=hashlib.sha256((str(self.call_index)+prompt).encode()).hexdigest());self.inflight=self.pool.submit(base.call_policy,self.a.policy,captured,prompt,s.episode,self.call_index,int(self.spec.get('policy_seed',7)));self.call_index+=1
     except ValueError as e:s.mode='needs_review';self.hold_remaining=40;self.terminal_hold_ticks=0;s.failure_detail=dict(code='requested_oracle_point_unavailable',detail=str(e));self.buffer=[];self.log('selected_reference_unavailable',error=str(e))
    if now<tick:time.sleep(min(.005,tick-now));continue
    tick=max(tick+.05,now+.05)
    if s.mode=='paused'or self.physics_pause_latch:
     self.publication_sequence+=1
     if self.family=='T2':self.pausefile.write(json.dumps(dict(time=time.time(),monotonic=now,episode_id=s.episode,task_id=s.task_id,version=s.version,mode=s.mode,physics_step=self.physics_steps,control_step=self.control_steps,simulation_time=float(self.env.sim.data.time),physical_state_sha256=self.state_hash(),held_object=self.cache_reader.snapshot['held_object']))+'\n')
     self.publish();continue
    if self.common_prefix is not None and self.common_prefix.done and self.fixture_hold and self.task_count==1:
     self.publish();time.sleep(.005);continue
    control=active and bool(self.buffer)and not self.hold_remaining;action=self.buffer.pop(0)if control else self.pose.action(self.obs);self.apply(action,'source_policy'if control else'evaluator_terminal_hold'if self.hold_remaining else'async_wait_hold')
    if self.hold_remaining:self.hold_remaining-=1;self.terminal_hold_ticks+=1
    if s.mode=='running'and self.task_started and(self.control_steps-self.task_start_control>=1200 or now-self.task_started>=600):s.mode='budget_exhausted';self.buffer=[];self.hold_remaining=40;s.failure_detail=dict(code='task_budget_exhausted',reason='control_steps'if self.control_steps-self.task_start_control>=1200 else'wall_time');self.event('task_budget_exhausted',task_id=s.task_id,reason=s.failure_detail['reason']);self.say('The task reached its execution budget and has stopped.')
    self.publish()
  except BaseException as e:
   import traceback;traceback.print_exc();self.errors.append(repr(e));s.mode='error';s.last_error=repr(e);self.publish();base.write(self.root/'ENGINE_ERROR.json',dict(error=repr(e),traceback=traceback.format_exc()))
  finally:
   self.pool.shutdown(wait=True);self.agent_pool.shutdown(wait=True);self.speech_pool.shutdown(wait=True);close_speech();self.video.close();self.inputvideo.close();self.voice.close()
   for f in [self.tickfile,self.physicalfile,self.observations,self.pausefile,self.logfile,self.eventfile]:f.close()
   self.db.close();self.env.close();base.write(self.root/'ENGINE_FINISHED.json',dict(episode_id=s.episode,task_count=self.task_count,policy_actions=self.control_steps,physics_steps=self.physics_steps,errors=self.errors,agent_calls=self.agent_call_count,final=self.public))

def main():
 p=argparse.ArgumentParser();p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=49601);p.add_argument('--gpu',type=int,default=2);p.add_argument('--policy',default='http://127.0.0.1:49541');a=p.parse_args();base.configure(a.out,a.gpu)
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(a.policy+'/metadata',timeout=10)as f:Engine.metadata=json.load(f)
 b=Engine(a);token=(R/'private/robot.token').read_text().strip();browser=(R/'private/browser.token').read_text().strip()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def reply(self,code,v,binary=False):
   data=v if binary else json.dumps(v,default=base.jsonable).encode();self.send_response(code);self.send_header('Content-Type','application/octet-stream'if binary else'application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
  def do_GET(self):
   from urllib.parse import urlsplit,parse_qs
   path=urlsplit(self.path).path
   if path in ['/status','/api/status']:return self.reply(200,copy.deepcopy(b.public))
   if path in ['/api/timeline','/timeline']:
    n=int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0]);return self.reply(200,dict(events=[x for x in b.events if x['id']>n],next_cursor=len(b.events),episode_id=b.state.episode,has_more=False,reset=False))
   if path in ['/api/tasks','/tasks']:return self.reply(200,dict(tasks=b.tasks))
   if path in ['/api/frame.jpg','/qa_frame.jpg']:
    from PIL import Image
    out=io.BytesIO();Image.fromarray(np.ascontiguousarray(b.obs['agentview_image'][::-1,::-1])).save(out,format='JPEG');return self.reply(200,out.getvalue(),True)
   if path=='/evaluator/inspect':return self.reply(200,b.inspect())
   if path=='/evaluator/status':return self.reply(200,b.evaluator_status())
   if path=='/speech_events':
    n=int(parse_qs(urlsplit(self.path).query).get('after',['0'])[0]);return self.reply(200,dict(events=[{k:v for k,v in x.items()if k!='path'}for x in b.speech_events if x['id']>n]))
   if path.startswith('/speech_audio/'):
    sid=int(path.rsplit('/',1)[-1]);row=next((x for x in b.speech_events if x.get('outputId')==sid and x['type']=='ready'),None)
    if row:
     import wave
     with wave.open(row['path'],'rb')as f:return self.reply(200,f.readframes(f.getnframes()),True)
   return self.reply(404,dict(error='unsupported_endpoint'))
  def do_POST(self):
   if self.headers.get('Authorization')not in ['Bearer '+token,'Bearer '+browser]:return self.reply(401,dict(error='authentication_required'))
   body=json.loads(self.rfile.read(int(self.headers.get('Content-Length',0)))or b'{}');path=self.path
   if path=='/conditioning':command=dict(op='condition',**body)
   elif path=='/input_activity':command=dict(op='input_activity',body=body)
   elif path=='/speech_receipt':command=dict(op='speech_receipt',body=body)
   elif path in ['/evaluator/finish','/evaluator/hold','/evaluator/release_window','/evaluator/pause']:command=dict(op=path.rsplit('/',1)[-1].replace('pause','fixture_pause'))
   else:return self.reply(404,dict(error='unsupported_tool'))
   done=queue.Queue(1);b.q.put((command,done))
   try:code,value=done.get(timeout=10);return self.reply(code,value)
   except queue.Empty:return self.reply(504,dict(error='owner_not_responding'))
 server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);threading.Thread(target=server.serve_forever,daemon=True).start();signal.signal(signal.SIGTERM,lambda *_:setattr(b,'stopping',True));signal.signal(signal.SIGINT,lambda *_:setattr(b,'stopping',True));b.run();server.shutdown()
if __name__=='__main__':main()
