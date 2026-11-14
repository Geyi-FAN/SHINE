import test,{after}from'node:test';import assert from'node:assert/strict';import{mkdtempSync,writeFileSync,rmSync}from'node:fs';import{tmpdir}from'node:os';import{join}from'node:path';
import{controlIntent,controlToolAllowed}from'../../voice/dist/tools/robot-control-semantics.js';
import{currentResumeReference}from'../../voice/dist/tools/robot-mixed-control.js';
import{independentStop,stopSegmentAllowed}from'../../voice/dist/tools/robot-fast-stop.js';
import{rememberStopLease,selectStopLease}from'../../voice/dist/tools/robot-stop-lease.js';
import{dispatchRobotTool}from'../../voice/dist/tools/robot.js';
import{LiveSession}from'../../voice/dist/orchestrator/live-session.js';
const temp=mkdtempSync(join(tmpdir(),'geyi-control-tests-'));writeFileSync(join(temp,'token'),'fake-test-token');const previousFetch=globalThis.fetch;process.env.ROBOT_GATEWAY_URL='http://127.0.0.1:1';process.env.ROBOT_GATEWAY_TOKEN_FILE=join(temp,'token');process.env.ROBOT_FAST_STOP='1';
after(()=>{globalThis.fetch=previousFetch;rmSync(temp,{recursive:true,force:true})});
for(const t of['Pause the 机器人。','pause的机器人。','Stop，暂停一下。','Stop.','Pause the robot.','请暂停当前任务。'])test('standalone pause '+t,()=>{assert.equal(controlIntent(t),'pause');assert.equal(independentStop(t),true);assert.equal(controlToolAllowed(controlIntent(t),'robot_cancel_task'),false)});
for(const t of['Continue 刚才的任务。','Resume the same 任务。','继续刚才的任务。','继续 the same task.','Continue the task you were doing.'])test('current resume '+t,()=>{assert.equal(currentResumeReference(t),true);assert.equal(controlIntent(t),'resume')});
for(const t of["Don't stop.",'Do not pause the robot.','不要pause。','不要停。','Stop after this task is finished.','完成后再pause。','Cancel the waiting task.','取消waiting任务。','What does stop mean?','如果我说暂停会怎样？','Stop. Put the bowl on the plate.'])test('not an immediate pause '+t,()=>assert.equal(independentStop(t),false));
for(const t of['恢复刚才打开抽屉的任务','Resume the completed earlier drawer task.','Continue the task from yesterday.','不要继续刚才的任务。','继续上一个已经完成的任务。'])test('not a generic current reference '+t,()=>assert.equal(currentResumeReference(t),false));
for(const prefix of["Don't.",'Do not.','如果','不要'])test('split negative '+prefix,()=>assert.equal(stopSegmentAllowed('Stop.',prefix),false));
function mockWorld(){
 const w={episode_id:'e',task_id:'t',task_version:7,state:'paused'},calls=[],accepted=[];let selection='unique',selectedTask='t',afterAccepted,beforeAccepted;
 globalThis.fetch=async(url,init)=>{
  const q=JSON.parse(init.body);calls.push(q);let r;
  if(q.name==='robot_query_memory')r={episode_id:w.episode_id,current_reference:{task_id:w.task_id,task_version:w.task_version},task_selection:{resolution:selection,candidates:selection==='unique'?[{task_id:selectedTask,is_current:true,state:'paused'}]:[{task_id:'t',is_current:true,state:'paused'},{task_id:'old',is_current:false,state:'cancelled'}]}};
  else if(q.name==='robot_get_status')r={...w};
  else if(q.args.episode_id!==w.episode_id||q.args.expected_task_version!==w.task_version)r={status:'rejected',code:'stale_identity',executed:false};
  else {beforeAccepted?.();w.task_version++;w.state=q.name==='robot_pause'?'paused':'running';r={...w,status:'accepted',executed:true};accepted.push(q);afterAccepted?.()}
  return new Response(JSON.stringify(r));
 };
 return{w,calls,accepted,onAccepted:(f)=>afterAccepted=f,beforeAccept:(f)=>beforeAccepted=f,ambiguous:()=>selection='ambiguous',wrongTask:()=>selectedTask='other'};
}
for(const phrase of['Continue 刚才的任务。','继续刚才的任务。'])test('real dispatcher resolves unique current memory '+phrase,async()=>{const x=mockWorld();const r=await dispatchRobotTool('robot_resume',JSON.stringify({episode_id:'e',expected_task_version:7}),'resume:'+phrase,phrase);assert.equal(r.ok,true);assert.equal(x.accepted.length,1);assert.equal(x.accepted[0].name,'robot_resume');assert.equal(x.w.task_id,'t');assert.equal(x.calls[0].name,'robot_query_memory')});
for(const kind of['ambiguous','wrongTask','staleVersion'])test('memory cannot select wrong task '+kind,async()=>{const x=mockWorld();if(kind==='ambiguous')x.ambiguous();if(kind==='wrongTask')x.wrongTask();const r=await dispatchRobotTool('robot_resume',JSON.stringify({episode_id:'e',expected_task_version:kind==='staleVersion'?6:7}),'resume:'+kind,'Continue 刚才的任务。');assert.equal(JSON.parse(r.receipt).code,'historical_task_requires_memory');assert.equal(x.accepted.length,0);assert.equal(x.calls.filter(c=>c.name==='robot_resume').length,0)});
function subject(){
 const x=mockWorld();x.w.state='running';const c={taskInputVersion:2,realtimeGeneration:1,fastStopAudioBytes:64000,fastStopOnsets:[],callId:'fixture',epoch:1,stopping:false,inputMuted:false,realtime:{sendBackendContext(){}}};
 const logs=[],spoken=[];const s=Object.create(LiveSession.prototype);Object.assign(s,{active:c,log:{write:(type,p)=>logs.push({type,...p})},host:{isOutputMuted:()=>false},deliverFixedRobotReceipt:(...a)=>{spoken.push(a);return true}});
 const event={itemId:'asr1',audioStartMs:1000,audioEndMs:1500,receivedAt:Date.now(),text:'Stop，暂停一下。',precedingText:'',precedingReceivedAt:0};s.beginIndependentStop(c,event);return{x,c,s,event,logs,spoken};
}
test('independent Stop survives only transport generation change',async()=>{const{c,s,event,x,spoken,logs}=subject();c.realtimeGeneration++;c.transportRecovering=true;await s.acceptFastStop(c,event);assert.equal(x.accepted.length,1);assert.equal(x.w.state,'paused');assert.equal(spoken.length,1);assert.ok(logs.some(l=>l.source==='independent_audio_lease'&&l.capturedGeneration!==l.currentGeneration))});
test('already consumed independent event cannot be replayed',async()=>{const{c,s,event,x,spoken}=subject();await s.acceptFastStop(c,event);await s.acceptFastStop(c,event);assert.equal(x.accepted.length,1);assert.equal(spoken.length,1)});
test('second explicit pause fragment does not commit the same pause twice',async()=>{const{c,s,event,x}=subject();await s.acceptFastStop(c,event);const second={...event,itemId:'asr2',text:'暂停一下。',receivedAt:Date.now()};s.beginIndependentStop(c,second);await s.acceptFastStop(c,second);assert.equal(x.accepted.length,1)});
test('a newer independent utterance invalidates an old Stop',async()=>{const{c,s,event,x}=subject();s.beginIndependentStop(c,{itemId:'asr2',audioStartMs:1600});await s.acceptFastStop(c,event);assert.equal(x.accepted.length,0)});
test('a newer primary utterance invalidates old Stop',async()=>{const{c,s,event,x}=subject();c.taskInputVersion++;c.fastStopOnsets=[{audioMs:1900,version:3,generation:1}];await s.acceptFastStop(c,event);assert.equal(x.accepted.length,0)});
test('primary VAD for same audio binds the same independent Stop once',async()=>{const{c,s,event,x}=subject();c.taskInputVersion++;c.fastStopOnsets=[{audioMs:1100,version:3,generation:1}];await s.acceptFastStop(c,event);assert.equal(x.accepted.length,1)});
for(const kind of['task','episode'])test('original gateway fence rejects a changed '+kind,async()=>{const{c,s,event,x,spoken}=subject();await c.independentStopLeases[0].identity;if(kind==='task'){x.w.task_id='other';x.w.task_version++}else x.w.episode_id='new';await s.acceptFastStop(c,event);assert.equal(x.accepted.length,0);assert.equal(spoken.length,0);const mutations=x.calls.filter(c=>c.name==='robot_pause');assert.equal(mutations.length,1);assert.equal(mutations[0].args.expected_task_version,7);assert.equal(mutations[0].args.episode_id,'e')});
test('stopping a call invalidates the independent control lease',async()=>{const{c,s,event,x}=subject();c.stopping=true;await s.acceptFastStop(c,event);assert.equal(x.accepted.length,0)});
test('muting input invalidates the control lease',async()=>{const{c,s,event,x}=subject();c.inputMuted=true;await s.acceptFastStop(c,event);assert.equal(x.accepted.length,0)});
test('old audio cannot be rebound to the current task',()=>{const c={taskInputVersion:1,realtimeGeneration:1,fastStopAudioBytes:320000};rememberStopLease(c,{itemId:'old',audioStartMs:0},Promise.resolve({}),Date.now()-20000);assert.equal(selectStopLease(c,{itemId:'old',audioEndMs:1000,receivedAt:Date.now()}),undefined)});

test('committed pause receipt survives a newer same-command ASR fragment',async()=>{
 const{c,s,event,x,spoken}=subject();let secondary;
 x.onAccepted(()=>{x.onAccepted(undefined);secondary={...event,itemId:'asr2',text:'暂停一下。',receivedAt:Date.now()};s.beginIndependentStop(c,secondary)});
 await s.acceptFastStop(c,event);assert.equal(x.accepted.length,1);assert.ok(c.independentPauseReceipt?.receipt);assert.equal(spoken.length,0);
 await s.acceptFastStop(c,secondary);assert.equal(x.accepted.length,1);assert.equal(spoken.length,1);
});

for(const[intent,tool]of[['resume','robot_restore_task'],['resume','robot_revise_task'],['pause','robot_start_task'],['cancel_waiting','robot_schedule_task']])test('standalone '+intent+' cannot replace control with '+tool,()=>assert.equal(controlToolAllowed(intent,tool),false));

for(const t of['不要继续当前任务。','不要恢复刚才的任务。','不要取消等待任务。'])test('negative controls cannot mutate '+t,()=>{assert.equal(controlIntent(t),'protected');for(const tool of['robot_resume','robot_pause','robot_cancel_task','robot_cancel_deferred'])assert.equal(controlToolAllowed(controlIntent(t),tool),false)});
test('actual dispatcher rejects restore instead of standalone current resume',async()=>{const x=mockWorld();const r=await dispatchRobotTool('robot_restore_task',JSON.stringify({episode_id:'e',expected_task_version:7,memory_id:'old'}),'wrong-restore','Continue 刚才的任务。');assert.equal(JSON.parse(r.receipt).code,'robot_control_semantics_mismatch');assert.equal(x.calls.length,0)});

test('second fragment may have captured OLD version before first pause committed; no retry mutation',async()=>{
 const{c,s,event,x,spoken}=subject();let secondary;
 x.beforeAccept(()=>{x.beforeAccept(undefined);secondary={...event,itemId:'asr2',text:'暂停一下。',receivedAt:Date.now()};s.beginIndependentStop(c,secondary)});
 await s.acceptFastStop(c,event);assert.equal(x.accepted.length,1);assert.equal(spoken.length,0);
 await s.acceptFastStop(c,secondary);assert.equal(x.accepted.length,1);assert.equal(spoken.length,1);assert.equal(x.calls.filter(x=>x.name==='robot_pause').length,1);
 assert.ok(x.calls.filter(x=>x.name==='robot_get_status').length>=3);
});
