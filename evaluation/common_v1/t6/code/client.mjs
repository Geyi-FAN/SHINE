/** One original question waveform; never injects reference text or actions. */
import {readFileSync,writeFileSync,mkdirSync}from'node:fs';
import {join}from'node:path';
import {createHash}from'node:crypto';
import {AudioClient}from'/mnt/disk_4/geyi/audio_switch_benchmark/experiments/asr_agent_oracle_20261108/revisions/cloud01_20261109_r6/code/raw_audio_client.mjs';
const cfg=JSON.parse(readFileSync(process.argv[2]));
const out=process.argv[3];mkdirSync(out,{recursive:true});
const client=new AudioClient({baseUrl:cfg.baseUrl,robotTokenFile:cfg.tokenFile,directory:out});
let gate,started,ended;const events=[];let transportErrors=[];
client.on('event',e=>{events.push(e);if(e.type==='client.input_clip_start')started=e;if(e.type==='client.input_clip_end')ended=e;});
client.on('transport_error',e=>transportErrors.push(e.message));
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function privateQuery(op){const r=await fetch(cfg.baseUrl+'/eval/t6',{method:'POST',headers:{Authorization:'Bearer '+readFileSync(cfg.tokenFile,'utf8').trim(),'Content-Type':'application/json'},body:JSON.stringify({op}),signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('private_gate_HTTP_'+r.status);return r.json();}
try{
 await client.connect();client.startSystemEvents({interval:100});
 const until=Date.now()+90000;
 while(Date.now()<until){gate=await privateQuery('gate');if(gate.passed)break;await sleep(80);}
 writeFileSync(join(out,'QA_READY.json'),JSON.stringify(gate,null,2));
 if(!gate?.passed)throw Error('physical_QA_gate_unavailable');
 const pcm=readFileSync(cfg.pcm);if(createHash('sha256').update(pcm).digest('hex')!==cfg.pcm_sha256)throw Error('PCM_hash_changed');
 const packet=await client.playPcm(pcm,{turn_id:cfg.case_id,source_sha256:cfg.audio_sha256});
 writeFileSync(join(out,'COMMIT.json'),JSON.stringify({case_id:cfg.case_id,packet,gate_identity:gate.identity}));
 await sleep(45000);
 writeFileSync(join(out,'TRIAL.json'),JSON.stringify({case_id:cfg.case_id,status:'observation_complete',audio_started:started?.time,audio_ended:ended?.time,finished:Date.now()/1000,gate,transport_errors:transportErrors},null,2));
}catch(e){
 writeFileSync(join(out,'TRIAL.json'),JSON.stringify({case_id:cfg.case_id,status:started?'committed_trial_error':'setup_unavailable',error:e.message,audio_started:started?.time,audio_ended:ended?.time,finished:Date.now()/1000,gate,transport_errors:transportErrors},null,2));
 if(started)await sleep(45000);
}finally{client.close();await client.flush();}
