/** Compatibility surface for frozen benchmark clients. No dialogue/tools/TTS. */
import {Worker} from 'node:worker_threads';
import {EventEmitter} from 'node:events';
import {mkdirSync,appendFileSync,writeFileSync,readFileSync} from 'node:fs';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
export function readWavPcm(path){return execFileSync('ffmpeg',['-v','error','-i',path,'-f','s16le','-ar','16000','-ac','1','-'],{maxBuffer:64*1024*1024});}
export class AudioClient extends EventEmitter{
 constructor(options){super();options={...options};options.baseUrl??=options.gatewayUrl;if(!options.token&&options.robotTokenFile)options.token=readFileSync(options.robotTokenFile,'utf8').trim();Object.assign(this,options);mkdirSync(this.directory,{recursive:true});this.closed=false;this.pending=new Map();this.seq=0;this.epoch=1;this.sink={records:new Map()};this.systemRecords=[];
  writeFileSync(join(this.directory,'transport.json'),JSON.stringify({transport:'independent_realtime_PCM_Whisper',frame_ms:20,output_audio:false,agent:false,oracle_inputs:false}));
  this.worker=new Worker(new URL('./raw_audio_worker.mjs',import.meta.url),{workerData:options});
  this.worker.on('message',m=>{if(m.reply){const p=this.pending.get(m.reply);this.pending.delete(m.reply);if(p)m.error?p.reject(Error(m.error)):p.resolve(m.value);}if(m.event){if(m.event.type==='host.state')this.hostState=m.event.status.state;if(m.event.type==='client.closed'&&m.event.unexpected)this.closed=true;this.emit('event',m.event);}if(m.fatal){for(const p of this.pending.values())p.reject(Error(m.fatal));this.pending.clear();this.emit('transport_error',Error(m.fatal));}});
  this.worker.on('error',e=>{for(const p of this.pending.values())p.reject(e);this.pending.clear();this.emit('transport_error',e);});
 }
 call(op,data={}){const id=++this.seq;return new Promise((resolve,reject)=>{this.pending.set(id,{resolve,reject});this.worker.postMessage({op,id,...data});});}
 async connect(){await Promise.race([this.call('connect'),new Promise((_,j)=>{this.readyTimer=setTimeout(()=>j(Error('ASR readiness timeout')),45000);})]);clearTimeout(this.readyTimer);return this;}
 playPcm(pcm,metadata={}){return this.call('play',{pcm,metadata});}
 async get(path,signal){const r=await fetch(new URL(path,this.baseUrl),{headers:{Authorization:'Bearer '+this.token},signal:signal||AbortSignal.timeout(6000)});if(!r.ok)throw Error('gateway_http_'+r.status);return r.json();}
 log(type,data={}){const e={type,time:Date.now()/1000,monotonic:Number(process.hrtime.bigint())/1e9,...data};this.systemRecords.push(e);this.emit('event',e);return e;}
 startSystemEvents({interval=250}={}){const poll=async()=>{if(this.closed)return;try{const r=await fetch(new URL('/api/status',this.baseUrl),{signal:AbortSignal.timeout(5000)});this.log('system.status',{status:await r.json(),source:'raw_gateway_http_poll'});}catch(e){if(!this.closed)this.log('client.system_event_error',{message:e.message});}if(!this.closed)this.pollTimer=setTimeout(poll,interval);};void poll();}
 close(){this.closed=true;clearTimeout(this.pollTimer);clearTimeout(this.readyTimer);this.worker.postMessage({op:'close'});}
 async flush(){await this.call('flush');writeFileSync(join(this.directory,'system_events.jsonl'),this.systemRecords.map(x=>JSON.stringify(x)).join('\n')+'\n');await this.worker.terminate();}
}
export {AudioClient as AudioBenchmarkClient};
