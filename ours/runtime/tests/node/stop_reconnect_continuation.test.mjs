import test from 'node:test';
import assert from 'node:assert/strict';
import {recoveryStopContinuation,selectStopLease}from'../../voice/dist/tools/robot-stop-lease.js';

function context(){
 const c={taskInputVersion:4,realtimeGeneration:1,fastStopAudioBytes:9850*32,
  robotSpeechGuard:{inputId:'old-primary'},
  fastStopOnsets:[{itemId:'old-primary',version:2,generation:0,audioMs:6690}],
  independentStopLeases:[{itemId:'independent',version:1,generation:0,audioMs:6420,startedAt:1000,identity:Promise.resolve({task_id:'original'})}]};
 const continuation=recoveryStopContinuation(c,{itemId:'recovered',recoveredFromInputId:'old-primary'});
 c.fastStopOnsets.push({itemId:'recovered',version:4,generation:1,audioMs:9840,recoveryContinuation:continuation});return c;
}
const event=()=>({itemId:'independent',audioEndMs:9420,receivedAt:4400});
test('reproduce reconnect midway through actual Stop sentence',()=>{
 const c=context(),lease=c.independentStopLeases[0];assert.equal(selectStopLease(c,event(),4400).lease,lease);
 assert.equal(lease.identity,c.independentStopLeases[0].identity);assert.equal(lease.version,1);
});
test('later real utterance still invalidates previous Stop',()=>{
 const c=context();c.fastStopOnsets.push({itemId:'new-real',version:5,generation:1,audioMs:10000});c.taskInputVersion=5;
 assert.equal(selectStopLease(c,event(),4400),undefined);
});
test('no provider link, mismatched speech guard, and same generation cannot create continuation',()=>{
 for(const change of ['link','guard','generation']){
  const c=context();c.fastStopOnsets.pop();
  const e={itemId:'recovered',recoveredFromInputId:'old-primary'};
  if(change==='link')e.recoveredFromInputId='another';
  if(change==='guard')c.robotSpeechGuard.inputId='another';
  if(change==='generation')c.realtimeGeneration=0;
  assert.equal(recoveryStopContinuation(c,e),undefined);
 }
});
test('continuation cannot extend original age or received-audio freshness',()=>{
 const c=context();assert.equal(selectStopLease(c,event(),14001),undefined);
 c.fastStopAudioBytes=13000*32;assert.equal(selectStopLease(c,event(),4400),undefined);
});
test('current input version and generation remain required',()=>{
 const c=context();c.taskInputVersion=5;assert.equal(selectStopLease(c,event(),4400),undefined);
 c.taskInputVersion=4;c.realtimeGeneration=2;assert.equal(selectStopLease(c,event(),4400),undefined);
});
test('bounded recovery chain retains original primary boundary',()=>{
 const c=context();c.robotSpeechGuard.inputId='recovered';c.realtimeGeneration=2;
 const next=recoveryStopContinuation(c,{itemId:'again',recoveredFromInputId:'recovered'});
 assert.equal(next.audioMs,6690);
});
test('unknown or forged continuation type cannot relax newer-onset fence',()=>{
 const c=context();c.fastStopOnsets.at(-1).recoveryContinuation.kind='unknown';
 assert.equal(selectStopLease(c,event(),4400),undefined);
});
