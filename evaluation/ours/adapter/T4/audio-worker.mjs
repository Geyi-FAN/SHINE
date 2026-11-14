/** Dedicated WS/audio clock. No simulator polling or synchronous logging here. */
import {parentPort,workerData}from'node:worker_threads';
import{createWriteStream}from'node:fs';import{writeFile}from'node:fs/promises';
import{join}from'node:path';import{performance}from'node:perf_hooks';
import{AudioBenchmarkClient,wav}from'./transport.mjs';
let closing=null;
const writes=[],stream=createWriteStream(join(workerData.directory,'events.jsonl'),{flags:'w'});
let active=null;
class Client extends AudioBenchmarkClient{
 log(type,data={}){const row={type,time:Date.now()/1000,monotonic:Number(process.hrtime.bigint())/1e9,system_monotonic:Number(process.hrtime.bigint())/1e9,...data};stream.write(JSON.stringify(row)+'\n');parentPort.postMessage({event:row});if(active&&type==='client.input_clip_start')active.start=row;if(active&&type==='client.input_clip_end')active.end=row;return row}
}
const client=new Client(workerData);
client.sink.persist=p=>{if(p.buffers.length)writes.push(writeFile(join(workerData.directory,`output_${p.epoch}_${p.outputId}.wav`),wav(Buffer.concat(p.buffers),24000)))};
parentPort.on('message',async m=>{try{
 if(m.op==='connect'){await client.connect();parentPort.postMessage({reply:m.id,value:true})}
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
