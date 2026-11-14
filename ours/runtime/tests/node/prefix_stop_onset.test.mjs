import test from 'node:test';
import assert from 'node:assert/strict';
import {selectPrefixStopLease,selectStopLease} from '../../voice/dist/tools/robot-stop-lease.js';
function setup() {
 const onset={audioMs:7400,startedAt:1000,version:1,generation:0,itemId:'current-audio'};
 return {onset,context:{taskInputVersion:4,realtimeGeneration:0,speechAudioTotal:10400*32,
   fastStopOnsets:[{audioMs:10600,startedAt:1000,version:4,generation:0}],independentStopLeases:[onset]}};
}
test('reproduce real failure: later primary fragment cannot exclude initial Stop',()=>{
 const {context,onset}=setup();assert.equal(selectPrefixStopLease(context,4000),onset);
 assert.equal(selectPrefixStopLease(context,4000).audioMs,7400);
});
test('stale primary input cannot block a fresh independent audio onset',()=>{
 const {context,onset}=setup();context.fastStopOnsets[0]={audioMs:4000,startedAt:1000,version:0,generation:0};
 assert.equal(selectPrefixStopLease(context,4000),onset);
});
test('earlier valid primary onset wins when independent VAD started late',()=>{
 const {context}=setup();context.fastStopOnsets[0].audioMs=7300;
 assert.equal(selectPrefixStopLease(context,4000),context.fastStopOnsets[0]);
});
test('consumed or already-probed onset cannot be decoded twice',()=>{
 for(const field of ['used','prefixProbeStarted']){const {context,onset}=setup();onset[field]=true;assert.equal(selectPrefixStopLease(context,4000),undefined)}
});
test('too short, too old audio, and old wall-clock lease are rejected',()=>{
 for(const total of [10399,11401]){const {context}=setup();context.speechAudioTotal=total*32;assert.equal(selectPrefixStopLease(context,4000),undefined)}
 const {context}=setup();assert.equal(selectPrefixStopLease(context,14001),undefined);
});
test('committed input boundary cannot be borrowed as prefix audio',()=>{
 const {context}=setup();context.stopPrerollFloorBytes=7500*32;assert.equal(selectPrefixStopLease(context,4000),undefined);
});
test('selection does not consume lease or mutate task identity',()=>{
 const {context,onset}=setup();const before=JSON.stringify(context);selectPrefixStopLease(context,4000);
 assert.equal(JSON.stringify(context),before);assert.equal(onset.used,undefined);
});
test('choosing a prefix does not bypass newer-turn mutation fence',()=>{
 const {context,onset}=setup();context.fastStopAudioBytes=15000*32;
 context.fastStopOnsets[0].audioMs=14000;
 assert.equal(selectPrefixStopLease({...context,speechAudioTotal:10400*32},4000),onset);
 assert.equal(selectStopLease(context,{itemId:onset.itemId,audioEndMs:10400,receivedAt:4000},4000),undefined);
});
