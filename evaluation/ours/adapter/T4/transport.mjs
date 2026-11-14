import {frameworkSocket as __preflightFrameworkSocket} from 'file:///mnt/disk_4/geyi/audio_switch_benchmark/preflights/c3r_pi05_32_20261108/adapter/T7/client/framework-socket.mjs';
/** Browser-free audio transport. The clocked sink is NOT a physical speaker. */
import {EventEmitter} from 'node:events';
import {performance} from 'node:perf_hooks';
import {randomUUID,createHash} from 'node:crypto';
import {mkdirSync,appendFileSync,writeFileSync,readFileSync} from 'node:fs';
import {join,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import WebSocket from './vendor/ws/wrapper.mjs';

export function inputFrame(epoch,pcm){
 if(!Buffer.isBuffer(pcm)||pcm.length%2)throw Error('Require PCM16LE samples');
 const b=Buffer.alloc(8+pcm.length);b.writeBigUInt64BE(BigInt(epoch));pcm.copy(b,8);return b;
}
export function outputFrame(b){
 if(b.length<=16||(b.length-16)%2)throw Error('Malformed output PCM frame');
 const epoch=Number(b.readBigUInt64BE()),outputId=Number(b.readBigUInt64BE(8));
 if(!Number.isSafeInteger(epoch)||!Number.isSafeInteger(outputId))throw Error('Unsafe audio identity');
 return {epoch,outputId,pcm:b.subarray(16)};
}
export function wav(pcm,rate){
 const h=Buffer.alloc(44);h.write('RIFF');h.writeUInt32LE(36+pcm.length,4);h.write('WAVEfmt ',8);h.writeUInt32LE(16,16);
 h.writeUInt16LE(1,20);h.writeUInt16LE(1,22);h.writeUInt32LE(rate,24);h.writeUInt32LE(rate*2,28);h.writeUInt16LE(2,32);h.writeUInt16LE(16,34);h.write('data',36);h.writeUInt32LE(pcm.length,40);return Buffer.concat([h,pcm]);
}
export class ClockedPcmSink{
 constructor({directory,send,log,clock=()=>performance.now(),schedule=setTimeout,cancel=clearTimeout}){
  Object.assign(this,{directory,send,log,clock,schedule,cancel});this.records=new Map();this.next=0;
 }
 record(epoch,outputId){
  const key=`${epoch}:${outputId}`;if(!this.records.has(key))this.records.set(key,{key,epoch,outputId,buffers:[],samples:0,jobs:[],started:false,ack:false,finished:false,aborted:false});return this.records.get(key);
 }
 push(epoch,outputId,pcm){
  const p=this.record(epoch,outputId);if(p.aborted)return;
  p.buffers.push(Buffer.from(pcm));p.samples+=pcm.length/2;
  this.log('client.output_pcm_received',{epoch,outputId,samples:pcm.length/2,totalSamples:p.samples,pcm_sha256:createHash('sha256').update(pcm).digest('hex')});
  if(p.samples>24000*600)throw Error('Output audio limit');
  if(p.buffers.length===1)this.log('client.output_first_pcm',{epoch,outputId});
  const start=Math.max(this.clock()+10,this.next);p.end=start+pcm.length/2/24000*1000;this.next=p.end;
  p.jobs.push(this.schedule(()=>{if(p.aborted)return;p.started=true;this.started(p)},Math.ceil(Math.max(0,start-this.clock()))));
  p.jobs.push(this.schedule(()=>this.complete(p),Math.ceil(Math.max(0,p.end-this.clock()))));
 }
 receipt(m){const p=this.record(m.epoch,m.outputId);p.receiptKey=m.receiptKey;p.expected=m.expectedSamples;this.started(p);this.complete(p)}
 finish(m){const p=this.record(m.epoch,m.outputId);p.finished=true;p.expected=m.expectedSamples??p.expected;this.complete(p)}
 started(p){
  if(!p.started||p.aborted||(p.ack&&(!p.receiptKey||p.startReceiptKey===p.receiptKey)))return;
  const bindingUpdate=p.ack;p.ack=true;p.startReceiptKey=p.receiptKey;
  this.log('client.output_clocked_start',{epoch:p.epoch,outputId:p.outputId,sink:'clocked_pcm_receiver'});
  this.send({type:'host.playback_started',epoch:p.epoch,outputId:p.outputId,...(p.receiptKey?{receiptKey:p.receiptKey}:{}),samples:p.samples,callbackWallTime:Date.now()/1000,bindingUpdate});
 }
 complete(p){
  if(p.aborted||p.completed||!p.finished||!p.started||!Number.isInteger(p.expected)||p.samples!==p.expected)return;
  const remaining=p.end-this.clock();
  if(remaining>0){
   if(!p.retry)p.jobs.push(p.retry=this.schedule(()=>{p.retry=null;this.complete(p)},Math.max(1,Math.ceil(remaining))));
   return;
  }
  this.started(p);p.completed=true;this.persist(p);
  this.send({type:'host.playback_completed',epoch:p.epoch,outputId:p.outputId,...(p.receiptKey?{receiptKey:p.receiptKey}:{}),samples:p.samples,expectedSamples:p.expected});
  this.log('client.output_clocked_complete',{epoch:p.epoch,outputId:p.outputId,samples:p.samples});
 }
 persist(p){if(this.directory&&p.buffers.length)writeFileSync(join(this.directory,`output_${p.epoch}_${p.outputId}.wav`),wav(Buffer.concat(p.buffers),24000))}
 clear(){for(const p of this.records.values()){if(p.completed||p.aborted)continue;p.aborted=true;for(const t of p.jobs)this.cancel(t);this.persist(p);this.log('client.output_cancelled',{epoch:p.epoch,outputId:p.outputId,samples:p.samples})}this.next=this.clock()}
}
export function readWavPcm(path){return execFileSync('ffmpeg',['-v','error','-i',path,'-f','s16le','-ar','16000','-ac','1','-'],{maxBuffer:64*1024*1024})}
export class AudioBenchmarkClient extends EventEmitter{
 constructor({baseUrl,token,directory,Socket=WebSocket,robotCamera=false}){
 if(process.env.PF_DISCOVERY_FILE && process.env.PF_GATEWAY_URL){Socket=__preflightFrameworkSocket({discoveryFile:process.env.PF_DISCOVERY_FILE,gatewayUrl:process.env.PF_GATEWAY_URL,robotTokenFile:process.env.PF_ROBOT_TOKEN_FILE,directory});}

  super();Object.assign(this,{baseUrl,token,directory,Socket,robotCamera});mkdirSync(directory,{recursive:true});this.epoch=0;this.input=[];this.closed=false;
  this.sink=new ClockedPcmSink({directory,send:m=>this.send(m),log:(type,data)=>this.log(type,data)});
  writeFileSync(join(directory,'transport.json'),JSON.stringify({transport:'websocket_pcm_no_browser',input_rate:16000,output_rate:24000,input_frame_ms:20,output_sink:'clocked_pcm_receiver_not_physical_speaker',audio_metric_boundary:'first PCM received by client'},null,2));
 }
 log(type,data={}){const row={type,time:Date.now()/1000,monotonic:performance.now()/1000,...data};appendFileSync(join(this.directory,'events.jsonl'),JSON.stringify(row)+'\n');this.emit('event',row);return row}
 send(m){if(this.ws?.readyState===1){this.ws.send(JSON.stringify(m));this.log(m.type,{direction:'sent',...m})}}
 async connect(timeout=45000){
  const u=new URL('/voice',this.baseUrl);u.protocol=u.protocol==='https:'?'wss:':'ws:';u.searchParams.set('session',this.token);
  this.ws=new this.Socket(u,{origin:new URL(this.baseUrl).origin});
  this.ws.on('open',()=>this.send({type:'host.hello',protocolVersion:9,hostVersion:'audio-benchmark-cli-v1',bundleId:'com.alibaba.qwen-live-harness.host',instanceNonce:randomUUID(),capabilities:{outputAudioEndMarkerV1:true},permissions:{microphone:'granted',camera:this.robotCamera?'granted':'not_determined',accessibility:'not_determined',screenRecording:'not_determined'},selfChecks:{audioInput:true,audioOutput:true,globalShortcut:false,appshot:false}}));
  this.ws.on('message',(data,binary)=>{try{
   if(binary){const m=outputFrame(Buffer.from(data));if(m.epoch===this.epoch)this.sink.push(m.epoch,m.outputId,m.pcm);else this.log('client.stale_audio_ignored',{epoch:m.epoch,outputId:m.outputId});return}
   const m=JSON.parse(String(data));if(m.epoch!==undefined&&m.epoch<this.epoch)return;
   if(m.epoch!==undefined&&m.epoch>this.epoch)this.sink.clear();
   if(m.epoch!==undefined)this.epoch=m.epoch;this.log(m.type,{direction:'received',...m});
   if(m.type==='host.welcome')this.send({type:'host.action',action:'new',epoch:this.epoch});
   if(m.type==='host.state'){this.hostState=m.status?.state;if(this.hostState==='listening')this.emit('listening');}
   if(m.type==='host.clear_output')this.sink.clear();
   if(m.type==='host.output_audio_receipt')this.sink.receipt(m);
   if(m.type==='host.output_audio_finished')this.sink.finish(m);
   if(m.type==='host.set_shortcut')this.send({type:'host.shortcut_result',requestId:m.requestId,shortcut:m.shortcut,success:false,error:'Standalone benchmark has no global keyboard shortcut.'});
  }catch(e){this.log('client.protocol_error',{message:e.message});this.close()}});
  this.ws.on('error',e=>this.log('client.socket_error',{message:String(e.message).replaceAll(this.token,'[redacted]')}));
  this.ws.on('close',()=>{this.closed=true;this.sink.clear();clearTimeout(this.inputTimer);if(this.currentClip){clearTimeout(this.currentClip.endTimer);this.currentClip.reject(Error('Audio input interrupted by disconnect'));this.currentClip=null}this.log('client.closed');this.emit('closed')});
  const began=performance.now();let deadline=began;
  const pump=()=>{if(this.closed)return;
   if(this.ws.readyState===1&&this.epoch){
    const clipFrame=this.input.length>0;const part=clipFrame?this.input.shift():Buffer.alloc(640);
    this.ws.send(inputFrame(this.epoch,part));
    if(clipFrame&&this.currentClip){
     const c=this.currentClip;if(!c.sent)this.log('client.input_clip_start',{frames:c.frames,pcm_sha256:c.sha256,source_sha256:c.source_sha256});
     c.sent++;this.log('client.input_frame',{clip_id:c.clip_id,frame_index:c.sent-1,epoch:this.epoch,samples:part.length/2,buffered_bytes:this.ws.bufferedAmount||0});
     if(!this.input.length)c.endTimer=setTimeout(()=>{if(this.currentClip!==c)return;this.log('client.input_clip_end',{frames:c.frames,sent:c.sent,pcm_sha256:c.sha256});this.currentClip=null;c.resolve()},20);
    }
   }
   deadline+=20;if(performance.now()-deadline>40){this.log('client.input_pacing_reset',{late_ms:performance.now()-deadline});deadline=performance.now()+20}
   this.inputTimer=setTimeout(pump,Math.max(0,deadline-performance.now()));
  };pump();
  while(!this.closed&&this.hostState!=='listening'&&performance.now()-began<timeout)await new Promise(r=>setTimeout(r,20));
  if(this.hostState!=='listening')throw Error('Voice readiness timeout');return this;
 }
 startSystemEvents({interval=250,fetcher=fetch}={}){
  if(this.systemPoll)throw Error('System event recording already started');
  const record={cursor:0,episode:null,abort:new AbortController()};this.systemPoll=record;
  const get=async path=>{
   const response=await fetcher(new URL(path,this.baseUrl),{signal:AbortSignal.any([record.abort.signal,AbortSignal.timeout(5000)])});
   if(!response.ok)throw Error(`System event HTTP ${response.status}`);return response.json();
  };
  const poll=async()=>{
   try{
    const status=await get('/api/status');if(this.closed)return;
    this.log('system.status',{status,source:'robot_gateway_http_poll',poll_interval_ms:interval});
    let page;
    do{
     const query=new URLSearchParams({after:String(record.cursor),...(record.episode?{episode:record.episode}:{})});
     page=await get('/api/timeline?'+query);if(this.closed)return;
     if(page.reset)this.log('system.episode_changed',{previous:record.episode,episode_id:page.episode_id});
     for(const event of page.events)this.log('system.task_event',{episode_id:page.episode_id,event,source:'robot_gateway_timeline'});
     record.cursor=page.next_cursor;record.episode=page.episode_id;
    }while(page.has_more&&!this.closed);
   }catch(e){if(!this.closed)this.log('client.system_event_error',{message:e.message})}
   if(!this.closed)record.timer=setTimeout(poll,interval);
  };void poll();return record;
 }
 playPcm(pcm,metadata={}){
  if(this.closed||this.currentClip)throw Error('Client closed or input clip still active');
  const frames=[];for(let i=0;i<pcm.length;i+=640){const b=Buffer.alloc(640);pcm.copy(b,0,i,Math.min(pcm.length,i+640));frames.push(b)}
  if(!frames.length)throw Error('Empty audio');
  const clip_id=String(metadata.turn_id||('clip_'+String(this.clipSequence=(this.clipSequence||0)+1).padStart(3,'0'))).replace(/[^A-Za-z0-9_-]/g,'_');
  writeFileSync(join(this.directory,clip_id+'_input_16k.wav'),wav(pcm,16000));
  return new Promise((resolve,reject)=>{this.currentClip={clip_id,...metadata,frames:frames.length,sent:0,sha256:createHash('sha256').update(pcm).digest('hex'),resolve,reject};this.log('client.input_clip_queued',{...metadata,frames:frames.length,samples:pcm.length/2,pcm_sha256:this.currentClip.sha256});this.input=frames});
 }
 async playWav(path){
  const source=readFileSync(path);const pcm=readWavPcm(path);
  writeFileSync(join(this.directory,'input_last_16k.wav'),wav(pcm,16000));
  return this.playPcm(pcm,{source_sha256:createHash('sha256').update(source).digest('hex')});
 }
 close(){this.closed=true;clearTimeout(this.inputTimer);if(this.systemPoll){clearTimeout(this.systemPoll.timer);this.systemPoll.abort.abort()}if(this.currentClip){clearTimeout(this.currentClip.endTimer);this.currentClip.reject(Error('Client closed during audio input'));this.currentClip=null;this.input=[];}this.sink.clear();this.ws?.close()}
}

if(process.argv[1]===fileURLToPath(import.meta.url)){
 const args=Object.fromEntries(process.argv.slice(2).reduce((a,x,i,all)=>i%2?a:[...a,[x.replace(/^--/,''),all[i+1]]],[]));
 if(!args.url||!args.wav||!args.out)throw Error('Usage: node audio_client.mjs --url http://127.0.0.1:ISOLATED_PORT --wav clip.wav --out evidence --seconds 600 [--token-file private/browser.token]');
 const token=readFileSync(args['token-file']||join(dirname(fileURLToPath(import.meta.url)),'../../private/browser.token'),'utf8').trim();
 const client=new AudioBenchmarkClient({baseUrl:args.url,token,directory:args.out});
 const pcm=readWavPcm(args.wav);writeFileSync(join(args.out,'input_16k.wav'),wav(pcm,16000));
 try{
  const image=await fetch(new URL('/api/frame.jpg',args.url),{signal:AbortSignal.timeout(5000)});
  const data=Buffer.from(await image.arrayBuffer());client.robotCamera=image.ok&&data[0]===255&&data[1]===216;
  client.log('client.camera_capability',{robot_camera:client.robotCamera,source:'gateway_simulator_camera',desktop_capture:false});
  client.startSystemEvents();await client.connect();await client.playPcm(pcm,{source_sha256:createHash('sha256').update(readFileSync(args.wav)).digest('hex')});await new Promise(r=>setTimeout(r,Number(args.seconds||600)*1000));
 }finally{client.close()}
}
