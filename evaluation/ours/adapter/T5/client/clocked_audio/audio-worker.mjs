/** Dedicated WS/audio clock. No simulator polling or synchronous logging here. */
import {parentPort,workerData}from'node:worker_threads';
import{createWriteStream}from'node:fs';import{writeFile}from'node:fs/promises';
import{join}from'node:path';
import{createHash}from'node:crypto';import{performance}from'node:perf_hooks';
import{AudioBenchmarkClient,wav}from"../common/audio_client.mjs";
let closing=null;
const writes=[],stream=createWriteStream(join(workerData.directory,'events.jsonl'),{flags:'w'});
let active=null;
class Client extends AudioBenchmarkClient{
 log(type,data={}){const row={type,time:Date.now()/1000,monotonic:Number(process.hrtime.bigint())/1e9,system_monotonic:Number(process.hrtime.bigint())/1e9,...data};stream.write(JSON.stringify(row)+'\n');parentPort.postMessage({event:row});if(active&&type==='client.input_clip_start')active.start=row;if(active&&type==='client.input_clip_end')active.end=row;return row}
}
const client=new Client(workerData);
client.sink.push=function(epoch,outputId,pcm){
  const p=this.record(epoch,outputId);if(p.aborted)return;
  p.buffers.push(Buffer.from(pcm));p.samples+=pcm.length/2;
  this.log('client.output_pcm_received',{epoch,outputId,samples:pcm.length/2,totalSamples:p.samples,pcm_sha256:createHash('sha256').update(pcm).digest('hex')});
  if(p.samples>24000*600)throw Error('Output audio limit');
  if(p.buffers.length===1)this.log('client.output_first_pcm',{epoch,outputId});
  const chunkSamples=pcm.length/2,chunkOffset=p.samples-chunkSamples,chunkHash=createHash('sha256').update(pcm).digest('hex');
  const start=Math.max(this.clock()+10,this.next);p.end=start+pcm.length/2/24000*1000;this.next=p.end;
  p.jobs.push(this.schedule(()=>{if(p.aborted)return;this.log('client.output_chunk_clocked_start',{epoch:p.epoch,outputId:p.outputId,sample_offset:chunkOffset,samples:chunkSamples,pcm_sha256:chunkHash});p.started=true;this.started(p)},Math.ceil(Math.max(0,start-this.clock()))));
  p.jobs.push(this.schedule(()=>this.complete(p),Math.ceil(Math.max(0,p.end-this.clock()))));
 };
client.sink.persist=p=>{if(p.buffers.length)writes.push(writeFile(join(workerData.directory,`output_${p.epoch}_${p.outputId}.wav`),wav(Buffer.concat(p.buffers),24000)))};
parentPort.on('message',async m=>{try{
 if(m.op==='connect'){
  await client.connect();
  const send=client.ws.send.bind(client.ws);
  client.ws.send=(data,...args)=>{
   const result=send(data,...args),clip=client.currentClip;
   if(Buffer.isBuffer(data)&&clip&&clip.sent<clip.frames&&data.length>8){
    client.log('client.wire_input_frame',{clip_id:clip.clip_id,frame_index:clip.sent,
      epoch:Number(data.readBigUInt64BE()),samples:(data.length-8)/2,
      pcm_sha256:createHash('sha256').update(data.subarray(8)).digest('hex')});
   }
   return result;
  };
  parentPort.postMessage({reply:m.id,value:true})
 }
 if(m.op==='play'){
  active={};await client.playPcm(Buffer.from(m.pcm),m.metadata);const value=active;active=null;
  parentPort.postMessage({reply:m.id,value});
 }
 if(m.op==='close'){closing=new Promise(resolve=>{const timer=setTimeout(()=>{client.ws?.terminate?.();resolve()},1000);client.ws?.once('close',()=>{clearTimeout(timer);resolve()});if(client.ws?.readyState===3){clearTimeout(timer);resolve()}});client.close();}
 if(m.op==='flush'){
  if(closing)await closing;await Promise.all(writes);await new Promise((ok,fail)=>{stream.once('error',fail);stream.end(ok)});
  parentPort.postMessage({reply:m.id,value:true});parentPort.close();
 }
}catch(e){parentPort.postMessage({reply:m.id,error:String(e.stack||e).replaceAll(workerData.token,'[redacted]')})}});
