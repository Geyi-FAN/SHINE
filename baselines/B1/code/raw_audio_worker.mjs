/** Independent 20 ms input clock. Sends PCM only to the frozen ASR server. */
import {parentPort,workerData as o} from 'node:worker_threads';
import {mkdirSync} from 'node:fs';
import {writeFile} from 'node:fs/promises';
import {join} from 'node:path';
import {createHash} from 'node:crypto';
import {ClockedPcmSink} from '/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114/actors/B1/adapter/T2/vendor/G22_audio_client.mjs';
import WebSocket from '/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114/actors/B1/adapter/T2/vendor/ws/wrapper.mjs';
const stamp=()=>({time:Date.now()/1000,monotonic:Number(process.hrtime.bigint())/1e9,system_monotonic:Number(process.hrtime.bigint())/1e9});
mkdirSync(o.directory,{recursive:true});
const records=[],pendingFiles=[];
function log(type,data={}){const e={type,...stamp(),epoch:1,...(type.startsWith('client.input_')?{direction:'sent'}:{}),...data};records.push(e);parentPort.postMessage({event:e});return e;}
let ws,ready=false,closed=false,timer,clip=null,deadline=0,queue=Promise.resolve();
let resolveDone;const receiverDone=new Promise(resolve=>{resolveDone=resolve;});
function activity(active,clip_id){void fetch(new URL('/input_activity',o.baseUrl),{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+o.token},body:JSON.stringify({active,clip_id,...stamp()}),signal:AbortSignal.timeout(6000)}).catch(e=>log('client.input_activity_error',{message:e.message}));}
let speechCursor=0,speechTimer;const speechMeta=new Map();
const sink=new ClockedPcmSink({directory:o.directory,send:m=>{
 const meta=speechMeta.get(m.outputId);
 m={...m,replyKind:meta?.replyKind||'unknown'};
 if(m.type==='host.playback_started'&&meta)log('host.state',{direction:'received',status:{state:'speaking',caption:meta.text}});
 log(m.type,{direction:'sent',...m});
 void fetch(new URL('/speech_receipt',o.baseUrl),{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+o.token},body:JSON.stringify(m)}).catch(e=>log('client.receipt_error',{message:e.message}));
 if(m.type==='host.playback_completed')setTimeout(()=>{if([...sink.records.values()].every(p=>p.completed||p.aborted))log('host.state',{direction:'received',status:{state:'listening'}});},20);
},log:(type,data)=>log(type,data)});
async function speechPoll(){if(closed)return;try{
 const response=await fetch(new URL('/speech_events?after='+speechCursor,o.baseUrl),{signal:AbortSignal.timeout(5000)});const page=await response.json();
 for(const e of page.events){speechCursor=e.id;
  if(e.type==='cancel'){
   const cancelled=[...sink.records.values()].filter(p=>!p.completed&&!p.aborted);sink.clear();
   for(const p of cancelled){const m={type:'host.playback_cancelled',epoch:p.epoch,outputId:p.outputId,samples:p.samples};log(m.type,{direction:'sent',...m});void fetch(new URL('/speech_receipt',o.baseUrl),{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer '+o.token},body:JSON.stringify(m)}).catch(e=>log('client.receipt_error',{message:e.message}));}
   log('host.clear_output',{direction:'received'});log('host.state',{direction:'received',status:{state:'listening'}});continue;
  }
  if(e.type!=='ready')continue;
  const r=await fetch(new URL('/speech_audio/'+e.outputId,o.baseUrl));if(!r.ok)throw Error('speech_PCM_unavailable');const pcm=Buffer.from(await r.arrayBuffer());if(pcm.length!==e.samples*2)throw Error('speech_PCM_length_mismatch');
  speechMeta.set(e.outputId,e);log('host.state',{direction:'received',status:{state:'speaking',caption:e.text}});
  log('host.output_audio_receipt',{direction:'received',epoch:1,outputId:e.outputId,expectedSamples:e.samples,receiptKey:'tts_'+e.outputId,text:e.text,replyKind:e.replyKind||'unknown'});
  sink.push(1,e.outputId,pcm);sink.receipt({epoch:1,outputId:e.outputId,receiptKey:'tts_'+e.outputId,expectedSamples:e.samples});
  log('host.output_audio_finished',{direction:'received',epoch:1,outputId:e.outputId,expectedSamples:e.samples});sink.finish({epoch:1,outputId:e.outputId,expectedSamples:e.samples});
 }
}catch(e){if(!closed)log('client.speech_poll_error',{message:e.message});}if(!closed)speechTimer=setTimeout(speechPoll,100);}

function wav(pcm){const b=Buffer.alloc(44);b.write('RIFF');b.writeUInt32LE(36+pcm.length,4);b.write('WAVEfmt ',8);b.writeUInt32LE(16,16);b.writeUInt16LE(1,20);b.writeUInt16LE(1,22);b.writeUInt32LE(16000,24);b.writeUInt32LE(32000,28);b.writeUInt16LE(2,32);b.writeUInt16LE(16,34);b.write('data',36);b.writeUInt32LE(pcm.length,40);return Buffer.concat([b,pcm]);}
function reply(id,value,error){parentPort.postMessage({reply:id,value,error});}
function pump(){
 if(closed)return;
 if(ready&&ws.readyState===1){
  const frame=Buffer.alloc(640);
  if(clip){
   const c=clip;if(c.sent===0){c.start=log('client.input_clip_start',{clip_id:c.clip_id,frames:c.frames,source_sha256:c.source_sha256,pcm_sha256:c.sha});activity(true,c.clip_id);}
   c.pcm.copy(frame,0,c.sent*640,Math.min(c.pcm.length,(c.sent+1)*640));
   ws.send(frame);log('client.input_frame',{clip_id:c.clip_id,frame_index:c.sent,epoch:1,samples:320,buffered_bytes:ws.bufferedAmount});c.sent++;
   if(c.sent===c.frames){clip=null;setTimeout(()=>{const end=log('client.input_clip_end',{clip_id:c.clip_id,frames:c.frames,sent:c.sent,pcm_sha256:c.sha});activity(false,c.clip_id);reply(c.id,{start:c.start,end});},20);}
  }else ws.send(frame);
 }
 deadline+=20;const now=Number(process.hrtime.bigint())/1e6;
 if(now-deadline>40){log('client.input_pacing_reset',{late_ms:now-deadline});deadline=now+20;}
 timer=setTimeout(pump,Math.max(0,deadline-now));
}
async function condition(m){
 // Neither expected text nor object/task labels enter this request.
 const response=await fetch(new URL('/conditioning',o.baseUrl),{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+o.token},body:JSON.stringify({text:m.text,asr_segment:m.segment,asr_session:ws.asrSession,asr_event:m}),signal:AbortSignal.timeout(10000)});
 if(!response.ok)throw Error('raw_conditioning_http_'+response.status);
 log('asr.transcript',{direction:'received',text:m.text,segment:m.segment,receipt:await response.json()});
}
parentPort.on('message',async m=>{try{
 if(m.op==='connect'){
  ws=new WebSocket(process.env.RAW_ASR_URL||'ws://127.0.0.1:49640');
  ws.on('message',(data,binary)=>{if(binary){log('client.protocol_error',{message:'ASR returned unexpected binary'});return;}const x=JSON.parse(String(data));
   if(x.kind==='ready'){ws.asrSession=x.session;ready=true;log('asr.ready',{metadata:x.metadata,session:x.session});log('host.state',{status:{state:'listening'},meaning:'actual_ASR_receiver_ready_not_spoken_acknowledgement'});deadline=Number(process.hrtime.bigint())/1e6;pump();void speechPoll();reply(m.id,true);}
   if(x.kind==='transcript')queue=queue.then(()=>condition(x)).catch(e=>{log('client.conditioning_error',{message:e.message});parentPort.postMessage({fatal:e.message});});
   if(x.kind==='done')resolveDone(x);
  });
  ws.on('error',e=>{log('client.socket_error',{message:e.message});parentPort.postMessage({fatal:e.message});});
  ws.on('close',()=>{resolveDone({socket_closed:true});if(!closed){closed=true;clearTimeout(timer);log('client.closed',{unexpected:true});}});
 }else if(m.op==='play'){
  if(!ready||closed||clip)throw Error('ASR not ready or clip already active');
  const pcm=Buffer.from(m.pcm);if(!pcm.length||pcm.length%2)throw Error('invalid PCM');
  const clip_id=String(m.metadata.turn_id||'clip_'+m.id).replace(/[^A-Za-z0-9_-]/g,'_');
  const sha=createHash('sha256').update(pcm).digest('hex');pendingFiles.push({path:join(o.directory,clip_id+'_input_16k.wav'),data:wav(pcm)});
  log('client.input_clip_queued',{...m.metadata,clip_id,frames:Math.ceil(pcm.length/640),samples:pcm.length/2,pcm_sha256:sha});
  clip={id:m.id,pcm,clip_id,frames:Math.ceil(pcm.length/640),sent:0,sha,source_sha256:m.metadata.source_sha256};
 }else if(m.op==='close'){
  closed=true;clearTimeout(timer);clearTimeout(speechTimer);sink.clear();if(clip){reply(clip.id,null,'input interrupted');clip=null;}
  if(ws?.readyState===1)ws.send(JSON.stringify({kind:'end'}));log('client.closed',{requested:true});
 }else if(m.op==='flush'){
  const done=await Promise.race([receiverDone,new Promise(resolve=>setTimeout(()=>resolve({timeout:true}),30000))]);
  await queue;if(done?.timeout)log('client.receiver_finalization_timeout');
  await Promise.all(pendingFiles.map(x=>writeFile(x.path,x.data)));
  await writeFile(join(o.directory,'events.jsonl'),records.map(x=>JSON.stringify(x)).join('\n')+'\n');
  ws?.close();reply(m.id,true);
 }
}catch(e){reply(m.id,null,e.message);}});
