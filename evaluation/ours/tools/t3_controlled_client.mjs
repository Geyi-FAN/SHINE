/** Real PCM only. Private observations schedule audio, never enter Agent input. */
import{readFileSync,writeFileSync,mkdirSync,existsSync}from'node:fs';
import{join,dirname}from'node:path';import{fileURLToPath}from'node:url';import{createHash}from'node:crypto';
import{AudioClient,readWavPcm}from'/mnt/disk_4/geyi/audio_switch_benchmark/preflights/c3r_pi05_32_20261108/adapter/shared/t8_adapter/audio-client.mjs';
const B='/mnt/disk_2/geyi/voice_c3r_integration_20261102',spec=JSON.parse(readFileSync(process.argv[2])),out=process.argv[3];
const preflight=process.argv.includes('--preflight'),protocol=spec.protocol,budgets=protocol.budgets;
const root='/mnt/disk_4/geyi/audio_switch_benchmark/preflights/c3r_pi05_32_20261108/adapter/shared/freeze/voice',token=readFileSync(join(root,'private/robot.token'),'utf8').trim();
const base=`http://127.0.0.1:${spec.web_port}`,gateway=`http://127.0.0.1:${spec.gateway_port}`;
const manifest=JSON.parse(readFileSync(spec.audio_manifest));
const clips=['source_audio_id','switch_audio_id'].map(k=>{const a=manifest.find(a=>a.utterance_id===spec[k]);if(!a||createHash('sha256').update(readFileSync(a.file)).digest('hex')!==a.sha256)throw Error('frozen_waveform_mismatch');return{...a,pcm:readWavPcm(a.file)}});
const clock=()=>({time:Date.now()/1000,monotonic:Number(process.hrtime.bigint())/1e9}),sleep=ms=>new Promise(r=>setTimeout(r,ms));
const row={schema:'T3-controlled-source-original-PCM-v2',case_id:spec.case_id,category:'T3',mode:'audio_cli_controlled_source_v2',started:clock(),turns:[],messages:[],triggers:[],errors:[],precondition_validated:false,typed_benchmark_task_injection:false,physical_microphone_verified:false,scope:preflight?'independent C0 engineering preflight; excluded from formal120':'user-authorized controlled-source development; fixedI00; original frozen acoustic corpus; first attempt per trial; independent of old natural-source protocol'};
const client=new AudioClient({baseUrl:base,token:readFileSync(join(root,'private/browser.token'),'utf8').trim(),directory:join(out,'client'),robotCamera:true});
client.on('event',e=>{if(e.direction||e.type.startsWith('client.'))row.messages.push(e)});client.on('transport_error',e=>row.errors.push('audio_worker:'+e.message));
function save(){writeFileSync(join(out,'result.partial.json'),JSON.stringify(row,null,2))}
async function get(path,post=false){const r=await fetch(gateway+path,{method:post?'POST':'GET',headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(6000)});if(!r.ok)throw Error(`gateway:${path}:${r.status}`);return r.json()}
async function status(){const r=await fetch(base+'/api/status',{signal:AbortSignal.timeout(6000)});if(!r.ok)throw Error('web_status:'+r.status);return r.json()}
async function inspect(){return get('/evaluator/inspect')}
async function wait(fn,seconds,label){const began=clock();while(clock().monotonic-began.monotonic<seconds){if(client.closed)throw Error('voice_disconnected:'+label);if(clock().monotonic-row.started.monotonic>budgets.case_wall_s)throw Error('case_wall_timeout');const x=await fn();if(x){row.triggers.push({label,reached:true,began,ended:clock()});save();return x}await sleep(100)}row.triggers.push({label,reached:false,began,ended:clock()});throw Error('timeout:'+label)}
const names=['open_middle','bowl_stove','bottle_cabinet','bowl_drawer','bowl_cabinet','push_plate','cheese_bowl','turn_on_stove','bowl_plate','bottle_rack'];
const object={1:'bowl',2:'wine_bottle',3:'bowl',4:'bowl',5:'plate',6:'cheese',8:'bowl',9:'wine_bottle'},rules=spec.rules;
function trigger(t){
 if(!t||t.task_id!==row.source_task_id||!['running','verifying'].includes(t.mode)||t.policy_actions<1||t.physical.native_goal_relations[names[spec.source_task]]!==false)return false;
 const p=t.physical,obj=object[spec.source_task];
 if(['M0','P0'].includes(spec.phase))return p.held_object==='none'&&!p.objects[obj].robot_contact;
 if(spec.phase==='K0')return p.held_object==='none'&&Math.abs(t.measurements.bowl.articulation.stove-row.initial_tick.measurements.bowl.articulation.stove)<1e-4;
 if(spec.phase==='D1')return Math.abs(t.measurements.bowl.articulation.middle)>rules.close.gap_m&&!p.drawers.middle.open;
 if(['M2','C4'].includes(spec.phase))return p.held_object===obj&&!p.objects[obj].supported&&(spec.phase!=='C4'||p.drawers.top.open);
 if(spec.phase==='C0')return p.held_object==='none'&&!p.objects.bowl.robot_contact&&Math.abs(t.measurements.bowl.articulation.top)<=rules.close.gap_m&&t.evaluator_extra?.cabinet_robot_contact===false;
 throw Error('unsupported_phase:'+spec.phase);
}
async function play(index){
 const a=clips[index],turn={turn_id:index?'U1':'U0',text:index?spec.spoken_text:spec.source_text,audio_id:a.utterance_id,audio_sha256:a.sha256,audio_seconds:a.pcm.length/32000,before:await status(),began:clock()};
 if(index)turn.stop_segment_end_s=a.stop_segment_end_s;
 row.turns.push(turn);save();const p=await client.playPcm(a.pcm,{turn_id:turn.turn_id,source_file:a.file,source_sha256:a.sha256});
 Object.assign(turn,{audio_started_wall:p.start.time,audio_started_monotonic:p.start.system_monotonic,audio_ended_wall:p.end.time,audio_ended_monotonic:p.end.system_monotonic});save();return turn;
}
try{
 row.initial=await status();row.episode_id=row.initial.episode_id;row.executor=row.initial.policy_metadata;row.initial_tick=(await inspect()).sample;
 if(row.initial.state!=='idle'||row.initial.task_id||row.initial.reset_count!==1||row.initial_tick.physical.held_object!=='none'||row.initial_tick.physical.native_goal_relations[names[spec.source_task]]!==false)throw Error('initial_precondition_invalid');
 client.startSystemEvents();await client.connect();await play(0);
 row.source_task_id=(await wait(async()=>{const s=await status();return s.task_id?s:false},20,'source_acceptance')).task_id;
 row.trigger_tick=await wait(async()=>{const prepared=join(out,'SOURCE_PREPARATION.json');if(!existsSync(prepared))return false;row.controlled_preparation=JSON.parse(readFileSync(prepared));if(!row.controlled_preparation.passed)throw Error('fixed_preparation_not_validated');const s=await inspect(),t=s.sample;if(['completed','needs_review','error','budget_exhausted','cancelled'].includes(t.mode))throw Error('source_terminal_before_trigger:'+t.mode);return trigger(t)?t:false},budgets.precondition_wall_s,'causal_source_trigger');row.precondition_validated=true;save();
 writeFileSync(join(out,'request_budget.json'),JSON.stringify({episode_id:row.episode_id,start_control:row.trigger_tick.policy_actions,max_action_steps:1200,source:'causal trigger before switch waveform; no control command'}));
 const u=await play(1),accepted=await wait(async()=>{const s=await status();return s.task_id&&s.task_id!==row.source_task_id?s:false},Math.max(0,u.audio_ended_wall+20-clock().time),'new_instruction_acceptance');
 row.new_task_id=accepted.task_id;row.accepted_instruction=accepted.instruction;row.new_instruction_acceptance=clock();save();
 if(preflight){
  row.first_new_vla=await wait(async()=>{const p=join(out,'gateway.jsonl');if(!existsSync(p))return false;const xs=readFileSync(p,'utf8').split('\n').filter(Boolean).flatMap(x=>{try{return[JSON.parse(x)]}catch{return[]}});return xs.find(x=>x.kind==='action_provenance'&&x.actual_vla_action&&x.identity?.[1]===row.new_task_id)||false},120,'new_task_actor_request_and_actual_vla_action');
  row.preflight_passed=true;row.run_status='preflight_first_new_action_only';
 }else{
  await wait(async()=>{const s=await status();return ['completed','needs_review','error','budget_exhausted','cancelled'].includes(s.state)?s:false},Math.max(0,u.audio_ended_wall+budgets.per_physical_goal_wall_s-clock().time),'task_terminal');
  const before=await inspect();
  if(before.mode==='paused')throw Error('terminal_observation_forbidden_by_user_pause');
  await get('/evaluator/hold',true);
  row.terminal_hold=await wait(async()=>{const s=await inspect();return s.hold_remaining===0&&s.physics_step>=before.physics_step+40?s:false},30,'40_new_real_physics_ticks');
  row.run_status='completed_observation';
 }
 // Capture actual queued terminal speech, not just its printed transcript.
 await sleep(3500);for(let i=0;i<100;i++){const pending=[...client.sink.records.values()].some(x=>x.started&&!x.completed&&!x.aborted);if(!pending&&client.hostState==='listening')break;await sleep(100)}
}catch(e){row.errors.push(e.stack||String(e));row.run_status='failed_or_unreached'}
finally{
 row.finished=clock();try{row.final=await status();row.final_tick=(await inspect()).sample;row.timeline=await(await fetch(base+'/api/timeline')).json()}catch(e){row.errors.push('final:'+e.message)}
 client.close();try{await client.flush()}catch(e){row.errors.push('flush:'+e.message)}
 writeFileSync(join(out,'result.json'),JSON.stringify(row,null,2));
 try{await get('/evaluator/finish',true)}catch{}
 console.log(row.case_id,row.final?.state,row.errors);
}
