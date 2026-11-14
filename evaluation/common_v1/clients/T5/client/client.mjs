// T5 causal dialogue: real waveforms and actually played questions; no typed task injection.
// Simulation truth below is evaluator-only and never included in model requests.
import {readFileSync,writeFileSync,appendFileSync,existsSync,readdirSync,openSync,closeSync,fstatSync,readSync,renameSync,mkdirSync} from 'node:fs';
import {join} from 'node:path';
const{AudioClient:AudioBenchmarkClient,readWavPcm}=await import('file:///mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114/actors/'+process.env.COMMON_METHOD+'/code/raw_audio_client.mjs');
import {createWriteStream} from 'node:fs';
import {writeFile,rename} from 'node:fs/promises';
import {performance} from 'node:perf_hooks';
import {questionKind,playedReplies,validProposal} from "../evaluator/t5_dialogue.mjs";
import {selectAudio,explicitCancellationReply} from '../evaluator/acoustic_binding.mjs';
const OUT=process.env.AUDIO_BENCH_OUT,BASE=process.env.AUDIO_BENCH_BASE;
const PROTOCOL=JSON.parse(readFileSync(process.env.AUDIO_BENCH_PROTOCOL||join(process.env.AUDIO_BENCH_DATA,'PROTOCOL.json')));
const B=PROTOCOL.budgets;
const script=JSON.parse(readFileSync(join(process.env.AUDIO_BENCH_DATA,'selected.private.json'))).find(s=>s.case_id===process.env.AUDIO_BENCH_CASE);
const allAudio=JSON.parse(readFileSync(process.env.AUDIO_BENCH_AUDIO));
const audio=selectAudio(allAudio,script);
if(!script||audio.some(a=>a.human_audio_review!=='pass')&&process.env.T5_ALLOW_UNREVIEWED_AUDIO!=='1')throw Error('Unbound script or unaccepted audio');
const mono=()=>Number(process.hrtime.bigint())/1e9, stamp=()=>({time:Date.now()/1000,monotonic:mono()});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const row={case_id:script.case_id,script_id:script.script_id,category:script.category,started:stamp(),
 test_mode:'T5 actual PCM; C3r recovery/R7-T3.2 observed intermediate completion; YOLO/M1; simulator-assisted memory validity',
 physical_metrics_evaluated:!PROTOCOL.interaction_only,
 acoustic_condition:script.acoustic_condition,canonical_case_id:script.canonical_case_id,reference_transcript_injected:false,
 audio_human_review:audio.every(a=>a.human_audio_review==='pass')?'pass':'pending_technical_preflight',
 physical_microphone_verified:false,key_intent_times:'not_annotated; audio_end_proxy',turns:[],triggers:[],errors:[],
 precondition_validated:false,protocol_wall_seconds:B.case_wall_s,protocol_version:PROTOCOL.version};
let pendingResult=null,resultWriter=null;
const persist=()=>{pendingResult=JSON.stringify(row,null,2);if(!resultWriter)resultWriter=(async()=>{while(pendingResult!==null){const data=pendingResult;pendingResult=null;await writeFile(join(OUT,'result.tmp'),data);await rename(join(OUT,'result.tmp'),join(OUT,'result.json'))}})().finally(()=>{resultWriter=null})};
const voiceStream=createWriteStream(join(OUT,'voice_events.jsonl'));
const statusStream=createWriteStream(join(OUT,'status.jsonl'));
const closeStream=s=>new Promise((resolve,reject)=>{s.once('error',reject);s.end(resolve)});
async function status(){const r=await fetch(BASE+'/api/status',{signal:AbortSignal.timeout(6000)});if(!r.ok)throw Error('status HTTP '+r.status);return r.json()}
function tail(file,bytes=100000){if(!existsSync(file))return [];const fd=openSync(file,'r');try{const size=fstatSync(fd).size,offset=Math.max(0,size-bytes),b=Buffer.alloc(size-offset);readSync(fd,b,0,b.length,offset);return b.toString('utf8').split('\n').flatMap(l=>{try{return [JSON.parse(l)]}catch{return []}})}finally{closeSync(fd)}}
const ticks=()=>row.episode_id?tail(join(OUT,'recordings',row.episode_id,'control_ticks.jsonl')):[];
const physical=()=>ticks().at(-1);
function voiceEvents(){const d=join(OUT,'voice/sessions');return existsSync(d)?readdirSync(d).filter(f=>f.endsWith('.jsonl')).flatMap(f=>readFileSync(join(d,f),'utf8').split('\n').flatMap(line=>{try{return [JSON.parse(line)]}catch{return []}})):[]}
async function wait(fn,seconds,label){const began=stamp(),deadline=mono()+seconds;while(mono()<deadline){if(mono()-row.started.monotonic>B.case_wall_s)throw Error('case_wall_budget_exhausted');const r=await fn();if(r){row.triggers.push({label,began,ended:stamp(),reached:true});persist();return r}await sleep(100)}row.triggers.push({label,began,ended:stamp(),reached:false});persist();throw Error('timeout:'+label)}
let voiceFailure=null,pollingStopped=false;const statusRequests=new Set();
let messages=[],active=new Set(),pcm=[],hostState='',page,poller,firstAgentAudio=null;
if(!process.env.T5_BROWSER_TOKEN_FILE)throw Error('Set private T5_BROWSER_TOKEN_FILE');
const token=readFileSync(process.env.T5_BROWSER_TOKEN_FILE,'utf8').trim();
const clips=new Map(audio.map(a=>[a.utterance_id,readWavPcm(a.file)]));
let client;
import{connectBeforeAudio}from'./connection_admission.mjs';
row.connection_admission=[];
function createConnection(attempt){
 const current=new AudioBenchmarkClient({baseUrl:BASE,token,directory:join(OUT,'client'),robotCamera:true});client=current;
 const flush=current.flush.bind(current);current.flushed=false;current.flush=async()=>{if(current.flushed)return;await flush();current.flushed=true};
 current.startSystemEvents();
 current.on('event',m=>{if(m.type==='gateway.error')current.preAudioError=String(m.message);});
 const connectedAt=Date.now();
 current.getPrivateTransportFailure=()=>voiceEvents().filter(e=>e.type==='error'&&e.ts>=connectedAt&&e.payload?.source==='realtime').map(e=>e.payload?.message||e.payload?.code||'').join(' ');
 attachConnection(current,attempt);return current;
}
function attachConnection(current,attempt){
current.on('event',m=>{m.connection_attempt=attempt;messages.push(m);if(current===client){if(m.type==='host.state')hostState=m.status?.state;if(m.type==='gateway.error')voiceFailure=String(m.message);if(m.type==='host.playback_started')active.add(m.epoch+':'+m.outputId);if(m.type==='host.playback_completed')active.delete(m.epoch+':'+m.outputId);if(m.type==='host.clear_output')active.clear();}voiceStream.write(JSON.stringify(m)+'\n');});
}
async function play(text,id,{prelude=false,...extra}={}){
 const matches=audio.filter(a=>a.text===text);if(matches.length!==1)throw Error('Missing/ambiguous authored clip:'+text);const clip=matches[0];
 const t={...extra,turn_id:id,text,audio_id:clip.utterance_id,audio_sha256:clip.sha256,prelude,before:await status(),before_tick:physical(),messages_start:messages.length,began:stamp()};
 row.turns.push(t);persist();
 const beganIndex=messages.length;
 await client.playPcm(clips.get(clip.utterance_id),{turn_id:id,source_file:clip.file,source_sha256:clip.sha256});
 const ev=messages.slice(beganIndex),begin=ev.find(m=>m.type==='client.input_clip_start'),end=ev.findLast(m=>m.type==='client.input_clip_end');
 if(!begin||!end)throw Error('Missing actual PCM send timestamps');
 t.audio_seconds=clips.get(clip.utterance_id).length/2/16000;t.audio_started_wall=begin.time;t.audio_started_monotonic=begin.monotonic;
 t.audio_ended_wall=end.time;t.audio_ended_monotonic=end.monotonic;
 t.audio_finished=stamp();persist();return t;
}
async function settle(t,limit=B.qa_complete_answer_from_audio_end_s){
 const question=false; // Every T1 utterance is a complete action request, including polite questions.
 try{await wait(async()=>{const recent=messages.slice(t.messages_start);const complete=recent.some(m=>m.direction==='sent'&&m.type==='host.playback_completed'&&m.monotonic>=t.audio_ended_monotonic);const caption=heardCaption(t).caption;const substantive=!question||(caption&&!/^(?:正在(?:查看|确认|分析)|请稍等|我先(?:看看|查看)|i(?:'m| am) checking)/i.test(caption));if(complete&&substantive&&hostState==='listening'&&active.size===0)return true;return false},limit,'reply_'+t.turn_id)}
 catch(e){if(!e.message.startsWith('timeout:reply_'))throw e;t.reply_deadline_missed=true;row.errors.push(e.message)}
 t.after=await status();t.after_tick=physical();t.finished=stamp();t.messages_end=messages.length;persist();
}
async function finishPhysical(){
 const auth=row.authorization_turn;
 row.physical_metrics_evaluated=true;
 row.physical_execution={eligible:script.private_contract.physical_eligible,goal_action_budget:B.per_physical_goal_action_steps,goal_wall_s:B.per_physical_goal_wall_s,terminal_hold_physical_steps:B.terminal_hold_steps};
 if(!script.private_contract.physical_eligible||!auth){
  row.physical_execution.reason=script.private_contract.physical_eligible?'authorization_missing':'negative_no_physical_goal';
  await sleep(B.negative_observation_s*1000);return;
 }
 let s=await status();
 if(!s.task_id){
  const limit=Math.max(0,auth.audio_ended_monotonic+B.valid_command_accept_from_audio_end_s-mono());
  try{s=await wait(async()=>{const current=await status();return current.task_id?current:false},limit,'authorized_task_acceptance');}
  catch(e){row.errors.push(e.message);row.physical_execution.reason='task_not_accepted';await sleep(B.negative_observation_s*1000);return;}
 }
 const terminal=new Set(['completed','error','needs_review','budget_exhausted','cancelled']);
 const remaining=Math.max(0,auth.audio_ended_monotonic+B.per_physical_goal_wall_s-mono());
 try{
  const ended=terminal.has(s.state)?s:await wait(async()=>{const current=await status();return terminal.has(current.state)?current:false},remaining,'task_terminal');
  row.physical_execution.reason='executor_terminal';row.physical_execution.terminal_state=ended.state;
  row.physical_execution.terminal_at=stamp();row.physical_execution.control_steps_at_terminal=ended.policy_action_steps;
 }catch(e){
  row.errors.push(e.message);row.physical_execution.reason='goal_wall_budget_exhausted';row.physical_execution.deadline_reached=stamp();persist();return;
 }
 const initial=physical();row.physical_execution.hold_start_step=initial?.step;
 try{
  const final=await wait(()=>{const tick=physical();return tick&&tick.step>=initial.step+B.terminal_hold_steps?tick:false},30,'terminal_hold_40_real_steps');
  row.physical_execution.hold_end_step=final.step;row.physical_execution.hold_observed=true;
 }catch(e){row.errors.push(e.message);row.physical_execution.hold_observed=false;}
 persist();
}

async function setupState(){
 const s=await status(),t=physical();
 if(s.task_id||s.state!=='idle'||!t||t.physical.held_object!=='none')throw Error('idle_precondition_invalid');
 const goal=script.private_contract.goal;if(goal&&t.physical.native_goal_relations[goal]!==false)throw Error('initial_target_not_false');
 if(s.pending_proposal||s.pending_clarification||s.deferred_task)throw Error('dialogue_state_not_empty');
 row.precondition_evidence={status:s,tick:t};
}
function heardCaption(turn){
 const complete=messages.filter(m=>m.direction==='sent'&&m.type==='host.playback_completed'&&m.monotonic>=turn.audio_ended_monotonic).at(-1);
 const begin=complete&&messages.find(m=>m.direction==='sent'&&m.type==='host.playback_started'&&m.epoch===complete.epoch&&m.outputId===complete.outputId);
 return {complete,caption:begin&&messages.filter(m=>m.type==='host.state'&&m.status?.caption&&m.monotonic<=begin.monotonic&&begin.monotonic-m.monotonic<.5).at(-1)?.status.caption||''};
}
function lastReply(turn){return playedReplies(messages,voiceEvents(),turn.audio_ended_wall).at(-1);}
async function questionAfter(turn,expected=null){
 await settle(turn);
 const choose=async()=>{
  const replies=playedReplies(messages,voiceEvents(),turn.audio_ended_wall);
  const reply=replies.find(r=>questionKind(r.text));
  if(!reply)return false; // A spoken "please wait" is not a clarification.
  if(reply.time>turn.audio_ended_wall+B.clarification_question_from_audio_end_s)throw Error('clarification_question_first_audio_late');
  if(reply.completed_time>turn.audio_ended_wall+B.qa_complete_answer_from_audio_end_s)throw Error('clarification_question_completed_late');
  const s=await status(),kind=questionKind(reply.text);
  if(expected!==null&&!validProposal(reply,s.pending_proposal,expected))throw Error('latest_correct_proposal_not_played');
  return {...reply,question:reply.text,kind,pending_proposal_id:s.pending_proposal?.proposal_id,pending_clarification_id:s.pending_clarification?.clarification_id};
 };
 const already=await choose();if(already)return already;
 return wait(choose,Math.max(0,turn.audio_ended_monotonic+B.qa_complete_answer_from_audio_end_s-mono()),'actual_useful_question');
}
async function clarificationDialogue(){
 let previous=await play(script.turns[0].text,script.turns[0].turn_id);
 const missing=new Set(script.private_contract.missing_slots);let optional=0;
 for(let n=0;n<B.max_clarification_questions_per_request+1;n++){
  const s=await status();
  if(!missing.size&&!s.pending_proposal&&s.task_id){await settle(previous);break;}
  const proof=await questionAfter(previous);
  if(proof.kind==='confirmation'){
   if(missing.size||optional)throw Error('confirmation_before_resolution_or_repeated');
   const s=await status();
   if(!validProposal(proof,s.pending_proposal,script.private_contract.target_task_id))throw Error('incorrect_optional_proposal');
   await sleep(1500);const answer=script.optional_confirmation;
   previous=await play(answer.text,script.script_id+'_C01',{optional_confirmation:true,confirmation:true,trigger_evidence:proof});optional++;
   row.authorization_turn=previous;await settle(previous);break;
  }
  if(n>=B.max_clarification_questions_per_request)throw Error('clarification_limit');
  if(!missing.size)throw Error('unnecessary_further_clarification');
  const answer=script.answer_branches[proof.kind];if(!answer)throw Error('unsupported_question_branch');
  await sleep(1500);
  previous=await play(answer.text,script.script_id+'_A'+String(n+1).padStart(2,'0'),{answer_branch:proof.kind,trigger_evidence:proof});
  for(const key of proof.kind==='both'?['object','destination']:[proof.kind])missing.delete(key);
  if(!missing.size)row.authorization_turn=previous;
  persist();
  await settle(previous);
  const now=await status();
  if(!missing.size&&!now.pending_proposal)break;
 }
 if(missing.size)throw Error('unresolved_slots');
}
async function fixedDialogue(){
 let previous;
 for(let i=0;i<script.turns.length;i++){
  const turn=script.turns[i];let proof=null;
  if(i){
   const trigger=turn.trigger;
   if(trigger.includes('confirmation_question_actually_played')){
    const expected=trigger.includes('initial')?script.private_contract.initial_candidate_task_id:script.private_contract.target_task_id;
    proof=await questionAfter(previous,expected===null?script.private_contract.initial_candidate_task_id:expected);
    await sleep(1500);
   }else if(trigger==='first_authorized_acceptance_receipt_actually_played_plus_1.5s'){
    await settle(previous);const s=await status(),reply=lastReply(previous);
    if(!s.task_id||!reply)throw Error('first_confirmation_not_accepted_or_spoken');
    proof={...reply,question:reply.text,task_id:s.task_id,kind:'acceptance_receipt'};await sleep(1500);
   }else if(trigger==='negative_receipt_actually_played_and_no_action_observed_for_2s'){
    await settle(previous);if(!lastReply(previous))throw Error('negative_receipt_not_spoken');await sleep(2000);
   }else if(trigger==='truthful_cancel_receipt_actually_played_plus_1.5s'){
    await settle(previous);const s=await status(),reply=lastReply(previous);if(s.pending_proposal||s.task_id||!reply)throw Error('cancellation_not_committed_or_spoken');const text=String(reply.text||'');if(!explicitCancellationReply(text))throw Error('truthful_explicit_cancellation_receipt_not_played');proof={...reply,kind:'verified_cancellation_receipt',question:reply.text};row.cancel_receipt_verified=proof;persist();await sleep(1500);
   }else throw Error('unsupported_t5_trigger:'+trigger);
  }
  previous=await play(turn.text,turn.turn_id,{trigger_evidence:proof,requires_question:!!(proof&&proof.kind==='confirmation'),confirmation:!!(proof&&proof.kind==='confirmation'&&((['F05','F06'].includes(script.family_id)&&i===2)||(['F07','F08'].includes(script.family_id)&&i===1)))});
  const f=script.family_id;
  if((['F05','F06','F09'].includes(f)&&i===2)||(['F07','F08'].includes(f)&&i===1))row.authorization_turn=previous;
  persist();
 }
 await settle(previous);
}
async function dialogue(){
 try{if(script.answer_branches)await clarificationDialogue();else await fixedDialogue();}
 catch(e){row.dialogue_error=e.message;row.errors.push('dialogue:'+e.message);persist();}
 await finishPhysical();
}

try{
 row.initial=await status();row.episode_id=row.initial.episode_id;row.executor=row.initial.policy_metadata;
 if(row.initial.task_id||row.initial.reset_count!==1)throw Error('Not a fresh episode');
 poller=setInterval(()=>{const request=(async()=>{try{const s=await status();if(!pollingStopped)statusStream.write(JSON.stringify({...stamp(),status:s})+'\n')}catch(e){if(!pollingStopped)row.errors.push('status_poll:'+e.message)}})().finally(()=>statusRequests.delete(request));statusRequests.add(request)},300);
 client=await connectBeforeAudio({create:createConnection,snapshot:status,turnCount:()=>row.turns.length,
  record:e=>{row.connection_admission.push(e);persist()},
  archive:async attempt=>{const dir=join(OUT,'preaudio_connections');if(!existsSync(dir))mkdirSync(dir,{recursive:true});renameSync(join(OUT,'client'),join(dir,'attempt_'+String(attempt).padStart(2,'0')));hostState='';voiceFailure=null;active.clear();}});hostState=client.hostState;
 await setupState();row.precondition_validated=true;row.main_started=stamp();persist();
 await dialogue();row.run_status='completed_observation';
}catch(e){row.run_status='failed_or_unreached';row.errors.push(e.message)}
finally{
 pollingStopped=true;clearInterval(poller);await Promise.allSettled([...statusRequests]);row.finished=stamp();
 try{row.final=await status();row.final_tick=physical();row.timeline=await(await fetch(BASE+'/api/timeline')).json();row.tasks=await(await fetch(BASE+'/api/tasks')).json()}catch(e){row.errors.push('final:'+e.message)}
 row.messages=messages;row.microphone={source:'real-time PCM client; no physical microphone',input_stream_active:!!client&&!client.closed};if(client&&!client.flushed){client.close();await client.flush();}persist();if(resultWriter)await resultWriter;await closeStream(voiceStream);await closeStream(statusStream);
 console.log(row.case_id,row.run_status,row.final?.state,row.errors);
}
