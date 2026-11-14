/** Parent can be busy reading evidence; audio WS remains on its own clock. */
import{Worker}from'node:worker_threads';import{EventEmitter}from'node:events';
import{createWriteStream,mkdirSync}from'node:fs';import{join}from'node:path';
import{performance}from'node:perf_hooks';
import{AudioBenchmarkClient}from'./transport.mjs';
export{readWavPcm}from'./transport.mjs';
export class AudioClient extends EventEmitter{
 constructor(options){super();Object.assign(this,options);mkdirSync(options.directory,{recursive:true});this.closed=false;this.pending=new Map();this.seq=0;this.sink={records:new Map()};this.systemStream=createWriteStream(join(options.directory,'system_events.jsonl'),{flags:'w'});
  this.worker=new Worker(new URL('./audio-worker.mjs',import.meta.url),{workerData:options});
  this.worker.on('message',m=>{
   if(m.reply){const p=this.pending.get(m.reply);this.pending.delete(m.reply);if(p)m.error?p.reject(Error(m.error)):p.resolve(m.value)}
   if(m.event){const e=m.event;if(e.type==='host.state')this.hostState=e.status?.state;
    if(e.type==='client.closed'){this.closed=true;for(const[id,p]of this.pending)if(['play','connect'].includes(p.op)){p.reject(Error('Audio WS disconnected'));this.pending.delete(id)}}
    if(e.epoch!==undefined)this.epoch=e.epoch;
    if(e.outputId!==undefined){const key=`${e.epoch}:${e.outputId}`,p=this.sink.records.get(key)||{};Object.assign(p,e);if(e.type==='client.output_clocked_start')p.started=true;if(e.type==='client.output_clocked_complete')p.completed=true;if(e.type==='client.output_cancelled')p.aborted=true;this.sink.records.set(key,p)}
    this.emit('event',e);
   }
  });
  this.worker.on('error',e=>{for(const p of this.pending.values())p.reject(e);this.pending.clear();this.emit('transport_error',e)});
 }
 call(op,data={}){const id=++this.seq;return new Promise((resolve,reject)=>{this.pending.set(id,{resolve,reject,op});this.worker.postMessage({op,id,...data})})}
 async connect(){await this.call('connect');return this}
 playPcm(pcm,metadata={}){return this.call('play',{pcm,metadata})}
 log(type,data={}){const e={type,time:Date.now()/1000,monotonic:Number(process.hrtime.bigint())/1e9,system_monotonic:Number(process.hrtime.bigint())/1e9,...data};this.systemStream.write(JSON.stringify(e)+'\n');this.emit('event',e);return e}
 startSystemEvents(options){return AudioBenchmarkClient.prototype.startSystemEvents.call(this,options)}
 close(){if(this.systemPoll){clearTimeout(this.systemPoll.timer);this.systemPoll.abort.abort()}this.worker.postMessage({op:'close'});this.closed=true}
 async flush(){await this.call('flush');await new Promise(r=>this.systemStream.end(r));await this.worker.terminate()}
}
