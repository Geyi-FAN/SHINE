import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync}from'node:fs';
import {waitingReceiptKey}from'../../voice/dist/tools/robot-waiting-receipt-identity.js';
import {LiveSession}from'../../voice/dist/orchestrator/live-session.js';
const actual=JSON.parse(readFileSync(new URL('../fixtures/waiting_completion_receipt.json',import.meta.url),'utf8'));
function world(){const f=structuredClone(actual);return {...f,turn:{inputId:f.inputId,text:'When the bowl is down, put the bowl on top of the cabinet.',status:f.prior,receipt:f.receipt,operation:'robot_schedule_task',version:2,generation:0}};}
test('actual completed predecessor and pending Native release can acknowledge queue immediately',()=>{
 const f=world();assert.ok(waitingReceiptKey(f.turn,f.receipt,'robot_schedule_task',f.callId));
});
test('ordinary still-running same-version scheduled receipt is unchanged',()=>{
 const f=world();f.receipt.state='running';f.receipt.task_version=f.prior.task_version;f.receipt.deferred_task.state='waiting_for_verified_completion';
 assert.ok(waitingReceiptKey(f.turn,f.receipt,'robot_schedule_task',f.callId));
});
for(const field of ['episode','task','intent','input','transaction','version','completion','phase'])test('invalid queue delivery proof is rejected: '+field,()=>{
 const f=world(),r=f.receipt;
 if(field==='episode')r.episode_id='different';
 if(field==='task')r.task_id='different';
 if(field==='intent')r.task_intent_revision++;
 if(field==='input')r.deferred_task.voice_input_id='different';
 if(field==='transaction')r.deferred_task.transaction_id='different';
 if(field==='version')r.task_version+=1;
 if(field==='completion')r.agent_execution.completion_current_verified=false;
 if(field==='phase')r.deferred_task.state='cancelled';
 assert.equal(waitingReceiptKey(f.turn,r,'robot_schedule_task',f.callId),undefined);
});
test('actual LiveSession fast-delivery path reaches local audio without model speech fallback',()=>{
 const f=world(),context={callId:f.callId,robotTurn:f.turn,taskInputVersion:2,realtimeGeneration:0,latestTaskInputId:f.inputId};
 const session=Object.create(LiveSession.prototype);session.active=context;session.host={isOutputMuted:()=>false};
 const played=[];session.playVerifiedControlAudio=(...args)=>{played.push(args);return true;};
 assert.equal(session.deliverWaitingReceipt(context,f.turn),true);assert.equal(played.length,1);assert.equal(played[0][2],'已排队。');
 context.taskInputVersion++;assert.equal(session.deliverWaitingReceipt(context,f.turn),false);assert.equal(played.length,1);
});
