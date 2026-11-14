import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync}from'node:fs';
import{tmpdir}from'node:os';import{join}from'node:path';
import{RobotExecutionTracker,executionNoticeCurrent}from'../../voice/dist/tools/robot-execution-feedback.js';
import{LiveSession}from'../../voice/dist/orchestrator/live-session.js';

const active=()=>({episode_id:'episode',task_id:'a',task_intent_revision:1,task_version:1,state:'running',policy_action_steps:1});
test('accepted without actual policy work does not authorize start speech',()=>{
 const t=new RobotExecutionTracker();assert.equal(t.observe({...active(),policy_action_steps:0}),undefined);
 const n=t.observe(active());assert.ok(n);t.admitted(n.key);assert.equal(t.observe(active()),undefined);
});
for(const change of[{state:'paused'},{state:'completed'},{task_id:'b'},{episode_id:'other'},{task_version:2},{task_intent_revision:2},{policy_action_steps:0}])
 test('changed evidence rejects queued execution speech '+JSON.stringify(change),()=>{
  const n=new RobotExecutionTracker().observe(active());assert.equal(executionNoticeCurrent(n,{...active(),...change}),false);
 });
test('pause/resume does not repeat an execution-start announcement',()=>{
 const t=new RobotExecutionTracker();const n=t.observe(active());t.observe({...active(),state:'paused',task_version:2});
 assert.equal(t.observe({...active(),task_version:3}),undefined);
 assert.ok(t.observe({...active(),task_id:'new',task_version:4,task_intent_revision:2}));
});
test('actual LiveSession watcher admits exactly one truthful start per task',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'voice-execution-'));writeFileSync(join(dir,'token'),'local-test');
 const original={fetch:globalThis.fetch,setInterval:globalThis.setInterval,now:Date.now,url:process.env.ROBOT_GATEWAY_URL,token:process.env.ROBOT_GATEWAY_TOKEN_FILE};
 let tick,world={...active(),policy_action_steps:0},now=Date.now();Date.now=()=>now;const spoken=[];
 process.env.ROBOT_GATEWAY_URL='http://127.0.0.1:1';process.env.ROBOT_GATEWAY_TOKEN_FILE=join(dir,'token');
 globalThis.fetch=async()=>new Response(JSON.stringify(world));
 globalThis.setInterval=cb=>{tick=cb;return{unref(){}}};
 const context={stopping:false,pendingToolCalls:new Set(),searches:new Map(),speechInProgress:false,responseInFlight:false};
 const receiver={active:context,host:{isOutputMuted:()=>false,setStatusText(){}},log:{write(){}},startResultSpeech:(c,text,purpose,identity)=>{spoken.push({text,identity});return true}};
 try{
  LiveSession.prototype.watchRobotTerminal.call(receiver,context);
  await tick();assert.equal(spoken.length,0);
  world=active();await tick();await tick();assert.equal(spoken.length,0);
  now+=1000;await tick();assert.equal(spoken.length,1);
  assert.ok(executionNoticeCurrent(spoken[0].identity.executionNotice,world));
  world={...world,state:'paused',task_version:2};await tick();
  world={...world,state:'running',task_version:3};await tick();assert.equal(spoken.length,1);
 }finally{
  globalThis.fetch=original.fetch;globalThis.setInterval=original.setInterval;Date.now=original.now;
  for(const[k,v]of[['ROBOT_GATEWAY_URL',original.url],['ROBOT_GATEWAY_TOKEN_FILE',original.token]])if(v===undefined)delete process.env[k];else process.env[k]=v;
  rmSync(dir,{recursive:true,force:true});
 }
});
