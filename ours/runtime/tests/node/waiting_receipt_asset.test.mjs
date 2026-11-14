import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {LiveSession} from '../../voice/dist/orchestrator/live-session.js';

function fixture() {
 const status={state:'running',episode_id:'episode',task_id:'source',task_version:1,task_intent_revision:1};
 const turn={status,inputId:'input',version:1,generation:1,text:"Push the plate in front of the stove when you're done.",operation:'robot_schedule_task',receipt:{...status,status:'scheduled',executed:false,deferred_task:{episode_id:'episode',predecessor_task_id:'source',voice_input_id:'call:input',state:'waiting_for_verified_completion',deferred_id:'pending',transaction_id:'pending',transaction_revision:1}}};
 const context={epoch:1,callId:'call',robotTurn:turn,taskInputVersion:1,realtimeGeneration:1,latestTaskInputId:'input',injector:{notePlaybackStarted(){}}};
 const sent=[];
 const receiver={active:context,options:{providers:{speech:{endpoint:'https://dashscope.aliyuncs.com',model:'qwen3.8-omni-flash-realtime',voice:'Tina'}}},abortResultSpeech(){},log:{write(){}},host:{isOutputMuted:()=>false,clearOutput(){},setCaption(){},sendOutputAudio:(epoch,audio)=>{sent.push(audio.length);return true},tagOutputAudio:()=>1,setCallState(){},finishOutputAudio(){}},playVerifiedControlAudio:LiveSession.prototype.playVerifiedControlAudio};
 return {context,turn,receiver,sent};
}
test('actual waiting callback emits one local PCM receipt without provider continuation',()=>{
 const previous=process.env.ROBOT_RECEIPT_AUDIO_DIR;
 process.env.ROBOT_RECEIPT_AUDIO_DIR=fileURLToPath(new URL('../../config/receipt_seed',import.meta.url));
 try {
  const f=fixture();assert.equal(LiveSession.prototype.deliverWaitingReceipt.call(f.receiver,f.context,f.turn),true);
  assert.equal(f.sent.length,1);assert.ok(f.sent[0]>0);
  assert.equal(LiveSession.prototype.deliverWaitingReceipt.call(f.receiver,f.context,f.turn),false);assert.equal(f.sent.length,1);
 }finally{if(previous===undefined)delete process.env.ROBOT_RECEIPT_AUDIO_DIR;else process.env.ROBOT_RECEIPT_AUDIO_DIR=previous}
});
for(const mutate of [f=>f.context.latestTaskInputId='other',f=>f.turn.receipt.deferred_task.voice_input_id='old:input',f=>f.turn.receipt.task_version=2,f=>f.context.speechInProgress=true])
 test('waiting speech cannot borrow stale or mismatched authority '+mutate.toString(),()=>{
  const f=fixture();mutate(f);assert.equal(LiveSession.prototype.deliverWaitingReceipt.call(f.receiver,f.context,f.turn),false);assert.equal(f.sent.length,0);
 });
