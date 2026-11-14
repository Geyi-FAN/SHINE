import fs from 'node:fs';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const R='/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114';
const W=R+'/code/runtime';
const require=createRequire(W+'/voice/package.json');const WebSocket=require('ws');
const {synthesizeNotificationSpeech}=await import(pathToFileURL(W+'/voice/dist/realtime/notification-speech.js'));
let active=0,maxActive=0;const words=['one','two','three','four'];
const rows=await Promise.all([0,1,2,3].map(async lane=>{
 const cfg=JSON.parse(fs.readFileSync(`${R}/private/voice_lane${lane}.json`));const key=fs.readFileSync(`${R}/private/realtime_lane${lane}.key`,'utf8').trim();
 const row={lane,started_at:Date.now()/1000};let sessionId;
 try{
  const result=await synthesizeNotificationSpeech({endpoint:cfg.providers.speech.endpoint,model:cfg.providers.speech.model,voice:cfg.providers.speech.voice,apiKey:key,language:'en',purpose:'visual_result',summary:`Voice lane ${words[lane]} is ready.`,fixedAnnouncement:`Voice lane ${words[lane]} is ready.`},{createWebSocket:(url,settings)=>{
   const s=new WebSocket(url,settings);s.on('open',()=>{active++;maxActive=Math.max(maxActive,active);row.connected_at=Date.now()/1000;});let closed=false;
   s.on('close',()=>{if(!closed){closed=true;if(row.connected_at)active--;row.closed_at=Date.now()/1000;}});
   s.on('message',data=>{try{const x=JSON.parse(data.toString());if(x.type==='session.created'){sessionId=x.session?.id;row.session_id=sessionId;}}catch{}});return s;
  }});
  row.passed=true;row.transcript=result.transcript;row.result_keys=Object.keys(result);
  for(const [k,v]of Object.entries(result))if(Buffer.isBuffer(v)){fs.writeFileSync(`${R}/reports/realtime_lane${lane}.pcm`,v);row.audio_bytes=v.length;}
 }catch(e){row.passed=false;row.error_code=e?.code??e?.name??'unknown';row.message=String(e?.message??'').replaceAll(key,'[redacted]').slice(0,500);}
 row.finished_at=Date.now()/1000;return row;
}));
const out={calls:4,passed:rows.filter(x=>x.passed).length,max_simultaneous_connections:maxActive,unique_sessions:new Set(rows.map(x=>x.session_id).filter(Boolean)).size,not_ASR_or_task_success:true,rows};
fs.writeFileSync(R+'/reports/REALTIME_PROBE.json',JSON.stringify(out,null,2)+'\n');console.log(JSON.stringify(out));
