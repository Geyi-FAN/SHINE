/** T4 first-attempt audio runner: no transcript, task, or Oracle-plan injection. */
import {AudioClient as AudioBenchmarkClient,readWavPcm} from './audio-client.mjs';
import {freshPausedSnapshot,frozenPauseAudit} from './pause-sync.mjs';
import {readFileSync,writeFileSync,appendFileSync,mkdirSync,readdirSync} from 'node:fs';
import {join} from 'node:path';
const delivery=input=>input.delivery_stage||'full';
import {performance} from 'node:perf_hooks';
import {readOnlyJson} from './read-only-http.mjs';
const input=JSON.parse(readFileSync(process.argv[2])),out=process.argv[3],c=input.case,b=input.budgets;
if(!process.env.T4_ROBOT_TOKEN_FILE||!process.env.T4_BROWSER_TOKEN_FILE)throw Error('Set private local T4 token-file paths');
const robotToken=readFileSync(process.env.T4_ROBOT_TOKEN_FILE,'utf8').trim();
const browserToken=readFileSync(process.env.T4_BROWSER_TOKEN_FILE,'utf8').trim();
const base=`http://127.0.0.1:${input.web_port}`,gateway=`http://127.0.0.1:${input.robot_port}`;
mkdirSync(out,{recursive:true});
const pcm=new Map(input.audio.map(a=>[a.utterance_id,readWavPcm(a.file)]));
const stamp=()=>({time:Date.now()/1000,monotonic:performance.now()/1000}),sleep=ms=>new Promise(r=>setTimeout(r,ms));
const row={case_id:c.case_id,script_id:c.script_id,category:'T4',started:stamp(),turns:[],triggers:[],errors:[],
 delivery_stage:delivery(input),test_mode:'T4 controlled causal prefix; real clocked PCM; C3r recovery + R7-T3.2 + NativePrefetch; observed intermediate completion; YOLO/M1',
 precondition_validated:false,key_intent_times:'audio_end_proxy',human_audio_accepted:false,physical_microphone_verified:false};
const events=[];const client=new AudioBenchmarkClient({baseUrl:base,token:browserToken,directory:join(out,'client'),robotCamera:true});
client.on('event',e=>{events.push(e);if(e.type==='host.state')latestHost=e;});
let latestHost,poller,polling=false;
const save=()=>writeFileSync(join(out,'result.json'),JSON.stringify({...row,messages:events},null,2));
let statusInFlight;
async function readJson(url,headers={}) {
 return readOnlyJson(url,{headers,onEvent:e=>appendFileSync(join(out,'transport_retries.jsonl'),JSON.stringify({...stamp(),...e})+'\n')});
}
async function status(){if(statusInFlight)return statusInFlight;statusInFlight=readJson(base+'/api/status');try{return await statusInFlight}finally{statusInFlight=undefined}}
async function privateStatus(){return readJson(gateway+'/evaluator/status',{Authorization:'Bearer '+robotToken})}
function deliveryEvidence(taskId){try{const rows=readFileSync(join(out,'gateway.jsonl'),'utf8').trim().split('\n').map(JSON.parse),request=rows.find(e=>e.kind==='executor_input'&&e.identity?.[1]===taskId),response=request&&rows.find(e=>e.kind==='executor_output'&&e.identity?.[1]===taskId&&e.request_sha256===request.request_sha256&&e.action_count>0),action=response&&rows.find(e=>['action_applied','native_source_action_applied'].includes(e.kind)&&e.identity?.[1]===taskId&&e.time>=response.time);return request&&response&&action?{request,response,action}:false}catch{return false}}
function ticks(){const p=join(out,'recordings',row.episode_id,'control_ticks.jsonl');try{const data=readFileSync(p,'utf8');return data.trim().split('\n').slice(-12).map(x=>JSON.parse(x))}catch{return []}}
async function wait(fn,seconds,label){const began=stamp();while(performance.now()/1000-began.monotonic<Math.max(0,seconds)){
 if(performance.now()/1000-row.started.monotonic>b.case_wall_s)throw Error('case_wall_budget');
 const x=await fn();if(x){row.triggers.push({label,began,ended:stamp(),reached:true});save();return x;}await sleep(150);
 }row.triggers.push({label,began,ended:stamp(),reached:false});save();throw Error('timeout:'+label)}
async function listening(){await wait(()=>client.hostState==='listening',45,'voice_listening')}
async function play(turn,prelude=false){
 const a=input.audio.find(a=>a.utterance_id===turn.utterance_id);if(!a||a.text!==turn.text)throw Error('waveform mismatch');
 await listening();const t={turn_id:turn.turn_id,text:turn.text,audio_id:a.utterance_id,audio_sha256:a.sha256,prelude,before:await status(),before_tick:ticks().at(-1),began:stamp(),messages_start:events.length};
 row.turns.push(t);save();t.audio_started_wall=Date.now()/1000;t.audio_started_monotonic=performance.now()/1000;
 const actual=await client.playPcm(pcm.get(a.utterance_id),{turn_id:turn.turn_id,source_file:a.file,source_sha256:a.sha256});
 t.audio_started_wall=actual.start.time;t.audio_started_monotonic=actual.start.system_monotonic;t.worker_audio=actual;
 t.audio_ended_wall=actual.end.time;t.audio_ended_monotonic=actual.end.system_monotonic;t.audio_seconds=t.audio_ended_wall-t.audio_started_wall;t.audio_finished=stamp();save();return t;
}
function heard(turn){
 const ends=events.filter(e=>e.type==='host.playback_completed'&&e.direction==='sent'&&e.time>=turn.audio_ended_wall);
 return ends.flatMap(end=>{const begin=events.find(e=>e.type==='host.playback_started'&&e.direction==='sent'&&e.epoch===end.epoch&&e.outputId===end.outputId);
  if(!begin)return [];const caption=events.filter(e=>e.type==='host.state'&&e.status?.caption&&e.time<=begin.time+.2&&begin.time-e.time<2).at(-1)?.status.caption;
  return caption?[{text:caption,begin,end}]:[];
 });
}
async function settle(turn){
 try{await wait(()=>events.some(e=>e.type==='host.playback_completed'&&e.direction==='sent'&&e.time>=turn.audio_ended_wall)&&client.hostState==='listening'&&![...client.sink.records.values()].some(p=>p.started&&!p.completed&&!p.aborted),b.qa_complete_answer_from_audio_end_s,'reply_'+turn.turn_id)}catch(e){row.errors.push(e.message);turn.reply_timeout=true}
 turn.heard=heard(turn);turn.after=await status();turn.finished=stamp();save();
}
function questionSlot(text){const obj=/which (?:object|item|one)|what (?:object|item)|bowl.{0,35}(?:or|还是).{0,30}(?:bottle|酒瓶)|哪个|哪一个|什么物|指的是|指哪个|碗.{0,20}(?:还是|或).{0,20}(?:酒瓶|瓶)|酒瓶.{0,20}(?:还是|或).{0,20}碗/i.test(text);
 const pos=/which (?:position|location)|where.{0,30}(?:return|back)|starting position|initial position|哪个位置|原来.{0,8}位置/i.test(text);
 return obj&&pos?'both':obj?'object':pos?'position':null;}
try{
 row.initial=await wait(async()=>{const s=await status();return s.ready===true?s:false;},45,'system_ready_before_audio');row.episode_id=row.initial.episode_id;row.executor=row.initial.policy_metadata;
 if(row.initial.task_id||row.initial.reset_count!==1)throw Error('not_fresh_episode');
 client.startSystemEvents();await client.connect();
 // The voice module marker is checked against the connected session before audio.
 await wait(()=>{const dir=join(out,'voice/sessions');try{return readdirSync(dir).filter(n=>n.endsWith('.jsonl')).some(n=>readFileSync(join(dir,n),'utf8').split('\n').filter(Boolean).map(JSON.parse).some(e=>e.type==='realtime.protocol'&&e.payload?.type==='t07.voice_lifecycle_patch'&&e.payload?.version==='played-control-listening-v1'));}catch{return false;}},3,'actual_voice_patch_identity');
 poller=setInterval(async()=>{if(polling)return;polling=true;try{appendFileSync(join(out,'status.jsonl'),JSON.stringify({...stamp(),status:await status()})+'\n')}catch(e){row.errors.push('status_poll:'+e.message)}finally{polling=false}},500);
 if(c.context_turns.length){
  const first=await play(c.context_turns[0],true);
  if(delivery(input)==='source'){
   const accepted=await wait(async()=>{const s=await status();return s.task_id?s:false},Math.max(1,first.audio_ended_wall+b.valid_command_accept_from_audio_end_s-Date.now()/1000),'source_task_acceptance');row.source_task_id=accepted.task_id;
   row.delivery=await wait(()=>deliveryEvidence(accepted.task_id),Math.max(1,first.audio_ended_wall+b.first_new_action_from_audio_end_s-Date.now()/1000),'source_actual_executor_action');row.run_status='source_delivered_core_unassessed';
   throw Object.assign(Error('delivery_complete'),{deliveryComplete:true});
  }
  row.phase_trigger=await wait(async()=>{const s=await status(),p=await privateStatus();if(!s.task_id&&Date.now()/1000>first.audio_ended_wall+b.valid_command_accept_from_audio_end_s)throw Error('source_command_not_accepted');
   if(['needs_review','budget_exhausted','cancelled','error'].includes(s.state))throw Error('source_failed:'+s.state);
   return p.source_window_ready&&p.source_window?{status:s,evaluator:p,tick:ticks().at(-1)}:false;
  },b.precondition_wall_s,'source_'+c.private_contract.source_stage);
  row.source_task_id=row.phase_trigger.status.task_id;
  const response=await fetch(gateway+'/evaluator/pause',{method:'POST',headers:{Authorization:'Bearer '+robotToken},signal:AbortSignal.timeout(7000)});
  row.fixture_pause={...stamp(),receipt:await response.json()};if(!response.ok)throw Error('common_pause_rejected');
  const previousSequence=row.phase_trigger.evaluator.publication_sequence;
  row.fixture_pause.synchronization={previous_publication_sequence:previousSequence,expected_episode_id:row.fixture_pause.receipt.episode_id,expected_task_id:row.fixture_pause.receipt.task_id,expected_task_version:row.fixture_pause.receipt.task_version,timeout_s:2,samples:[]};
  const before=await wait(async()=>{
   const s=await privateStatus();row.fixture_pause.synchronization.samples.push(s);
   return freshPausedSnapshot(s,row.fixture_pause.receipt,previousSequence)?s:false;
  },2,'pause_owner_publication_synced');
  await sleep(250);const after=await privateStatus();
  row.fixture_pause.audit=frozenPauseAudit(before,after);
  if(!row.fixture_pause.audit.passed)throw Error('common_pause_did_not_freeze_physics');
  await settle(first);const retained=await privateStatus();if(!retained.source_window)throw Error('source_state_not_retained');
  row.precondition_evidence={status:await status(),tick:ticks().at(-1),confirmed_window:ticks(),fixture_version:'easy10_verified_precontact_or_M4_true_hard_pause'};
 }else{
  const s=await status();if(s.task_id||s.state!=='idle')throw Error('negative_not_fresh_idle');row.precondition_evidence={status:s,tick:ticks().at(-1)};
 }
 row.precondition_validated=true;row.main_started=stamp();save();let turn=await play(c.query_turn);await settle(turn);
 row.clarification_branches=[];
 for(let n=0;Object.keys(c.clarification_answers).length&&n<b.max_clarification_questions_per_request;n++){
  const s=await status();if(s.task_id&&s.task_id!==row.source_task_id)break;
  const question=heard(turn).map(q=>({...q,slot:questionSlot(q.text)})).filter(q=>q.slot).at(-1);
  if(!question)throw Error('no_actually_spoken_matching_clarification');const answer=c.clarification_answers[question.slot];if(!answer)throw Error('no_reviewed_answer_for_actual_question:'+question.slot);
  row.clarification_branches.push({question:question.text,slot:question.slot,output_id:question.begin.outputId,...stamp()});save();await sleep(b.user_reply_delay_after_question_s*1000);
  turn=await play({turn_id:c.script_id+'_A'+(n+1),text:answer.text,utterance_id:answer.utterance_id});await settle(turn);
 }
 if(c.physical_eligible){
  row.authorization_anchor=turn.turn_id;
  const accepted=await wait(async()=>{const s=await status();if(s.task_id&&s.task_id!==row.source_task_id)return s;if(s.pending_clarification||s.pending_proposal)return {unresolved:true,state:s};return false;},Math.max(1,turn.audio_ended_wall+b.valid_command_accept_from_audio_end_s-Date.now()/1000),'new_task_acceptance');
  if(accepted.unresolved)row.unresolved=accepted;
  else{
   row.accepted_task_id=accepted.task_id;save();
   if(delivery(input)==='switch'){row.delivery=await wait(()=>deliveryEvidence(accepted.task_id),Math.max(1,turn.audio_ended_wall+b.first_new_action_from_audio_end_s-Date.now()/1000),'switch_actual_executor_action');row.run_status='switch_delivered';throw Object.assign(Error('delivery_complete'),{deliveryComplete:true});}
   row.terminal=await wait(async()=>{const s=await status();return ['completed','needs_review','budget_exhausted','cancelled','error'].includes(s.state)?s:false;},Math.max(0,turn.audio_ended_wall+b.per_physical_goal_wall_s-Date.now()/1000),'new_task_terminal');
   await wait(async()=>{const s=await privateStatus();return s.terminal_hold_ticks>=40?s:false;},25,'forty_physical_terminal_hold');
   const began=row.terminal?.observation_time??Date.now()/1000;await wait(()=>{const plays=events.filter(e=>e.type==='host.playback_completed'&&e.direction==='sent'&&e.time>=began-3);return plays.length&&client.hostState==='listening';},30,'terminal_receipt_audio').catch(e=>row.errors.push(e.message));
  }
 }else await sleep(b.negative_observation_s*1000);
 row.run_status='completed_observation';
}catch(e){if(!e.deliveryComplete){row.run_status='failed_or_unreached';row.errors.push(e.message)}}
finally{
 clearInterval(poller);row.finished=stamp();try{row.final=await status();row.final_tick=ticks().at(-1);row.timeline=await(await fetch(base+'/api/timeline')).json();row.tasks=await(await fetch(base+'/api/tasks')).json()}catch(e){row.errors.push('final:'+e.message)}
 row.messages=events;save();client.close();await client.flush();try{await fetch(gateway+'/evaluator/finish',{method:'POST',headers:{Authorization:'Bearer '+robotToken},signal:AbortSignal.timeout(5000)})}catch{}
}
console.log(JSON.stringify({case_id:c.case_id,entered:row.precondition_validated,status:row.run_status,errors:row.errors}));
