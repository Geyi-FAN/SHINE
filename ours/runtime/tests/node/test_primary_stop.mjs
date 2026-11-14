import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync,writeFileSync,rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { LiveSession } from '../../voice/dist/orchestrator/live-session.js';
import { rememberStopLease } from '../../voice/dist/tools/robot-stop-lease.js';
const folder=mkdtempSync(join(tmpdir(),'t3-primary-stop-'));
writeFileSync(join(folder,'token'),'test-only');
const original=globalThis.fetch;
process.env.ROBOT_GATEWAY_URL='http://127.0.0.1:1';process.env.ROBOT_GATEWAY_TOKEN_FILE=join(folder,'token');
after(()=>{globalThis.fetch=original;rmSync(folder,{recursive:true,force:true});});
function world(){
 const calls=[],notes=[];
 globalThis.fetch=async(url,init)=>{
  const q=JSON.parse(init.body);calls.push(q);
  return new Response(JSON.stringify({status:'accepted',executed:true,state:'paused',episode_id:'e',task_id:'old',task_version:2,request_id:q.request_id}));
 };
 const turn={inputId:'full-user',version:2,generation:0};
 const context={callId:'call',epoch:1,taskInputVersion:2,realtimeGeneration:0,latestTaskInputId:'full-user',robotTurn:turn,
  fastStopOnsets:[{version:2,generation:0,startedAt:Date.now(),identity:Promise.resolve({episode_id:'e',task_id:'old',task_version:1,state:'running'})}],
  realtime:{sendBackendContext:x=>notes.push(x)}};
 const session=Object.create(LiveSession.prototype);
 Object.assign(session,{active:context,log:{write(){}}});
 return{calls,notes,context,turn,session};
}
test('actual main-ASR fallback pauses once without consuming the new-task turn',async()=>{
 const w=world();await w.session.acceptPrimaryCompoundStop(w.context,{text:'Stop! Please put the bowl on the plate.'},w.turn);
 assert.equal(w.calls.length,1);assert.equal(w.calls[0].name,'robot_pause');
 assert.equal(w.calls[0].args.expected_task_version,1);assert.equal(w.turn.attempted,undefined);assert.equal(w.turn.receipt,undefined);
 assert.equal(w.context.fastStop.receipt.state,'paused');assert.equal(w.notes.length,1);
});
test('already committed auxiliary pause cannot repeat',async()=>{
 const w=world();w.context.fastStop={version:2,generation:0,receipt:{state:'paused'}};
 await w.session.acceptPrimaryCompoundStop(w.context,{text:'Stop. Put the bowl on the plate.'},w.turn);assert.equal(w.calls.length,0);
});
for(const phrase of ['Put the bowl on the plate.',"Don't stop. Put the bowl on the plate.",'If I say stop, pause.','Stop.'])test('does not acquire compound authority: '+phrase,async()=>{
 const w=world();await w.session.acceptPrimaryCompoundStop(w.context,{text:phrase},w.turn);assert.equal(w.calls.length,0);
});
test('new user input while awaiting onset identity invalidates the fallback',async()=>{
 const w=world();let done;w.context.fastStopOnsets[0].identity=new Promise(r=>done=r);
 const work=w.session.acceptPrimaryCompoundStop(w.context,{text:'Stop. Put the bowl on the plate.'},w.turn);
 w.context.taskInputVersion=3;done({episode_id:'e',task_id:'old',task_version:1,state:'running'});await work;
 assert.equal(w.calls.length,0);
});
for (const compound of [true,false])test('auxiliary stop: compound has one goal acknowledgement; pure stop still speaks '+compound,async()=>{
 const w=world(),event={itemId:'asr',text:compound?'Stop! Please put the bowl on the plate.':'Stop.',audioStartMs:0,audioEndMs:3500,receivedAt:Date.now()};
 w.context.fastStopAudioBytes=3500*32;
 w.context.fastStopOnsets[0].audioMs=0;
 rememberStopLease(w.context,event,w.context.fastStopOnsets[0].identity);
 let spoken=0;w.session.deliverFixedRobotReceipt=()=>{spoken++;return true;};
 await w.session.acceptFastStop(w.context,event);
 assert.equal(w.calls.length,1);assert.equal(w.calls[0].name,'robot_pause');
 assert.equal(w.context.fastStop.receipt.state,'paused');assert.equal(spoken,compound?0:1);
});

test('actual independent-prefix path survives same-input provider reconnect once',async()=>{
 const w=world(),event={itemId:'asr',text:'Stop! Put the bowl on the stove.',audioStartMs:5670,audioEndMs:9420,receivedAt:Date.now()};
 const identity=w.context.fastStopOnsets[0].identity;
 w.context.taskInputVersion=1;w.context.fastStopAudioBytes=9850*32;
 const lease=rememberStopLease(w.context,{itemId:'asr',audioStartMs:6420},identity);
 w.context.taskInputVersion=4;w.context.realtimeGeneration=1;
 w.context.fastStopOnsets=[{itemId:'recovered',version:4,generation:1,audioMs:9840,
   recoveryContinuation:{kind:'same_input_transport_recovery_v1',fromItemId:'source',toItemId:'recovered',audioMs:6690}}];
 await w.session.acceptFastStop(w.context,event);
 assert.equal(w.calls.length,1);assert.equal(w.calls[0].name,'robot_pause');
 assert.equal(w.calls[0].args.expected_task_version,1);
 assert.equal(w.context.fastStop.receipt.state,'paused');assert.equal(lease.used,true);
 await w.session.acceptFastStop(w.context,event);assert.equal(w.calls.length,1);
});

test('actual redecoded Stop first is accepted without waiting for later task clauses',async()=>{
 const w=world(),old=process.env.ROBOT_FAST_STOP;process.env.ROBOT_FAST_STOP='1';
 w.context.fastStopAudioBytes=13780*32;w.context.fastStopOnsets[0].audioMs=12620;
 w.session.deliverFixedRobotReceipt=()=>true;
 try{
  await w.session.acceptLegacyFastStop(w.context,{itemId:'verified-real-audio',text:'Stop first.',audioStartMs:12420,audioEndMs:13780,receivedAt:Date.now()});
  assert.equal(w.calls.length,1);assert.equal(w.calls[0].name,'robot_pause');assert.equal(w.calls[0].args.expected_task_version,1);
  assert.equal(w.context.fastStop.receipt.state,'paused');assert.equal(w.turn.attempted,undefined);
 }finally{if(old===undefined)delete process.env.ROBOT_FAST_STOP;else process.env.ROBOT_FAST_STOP=old;}
});
