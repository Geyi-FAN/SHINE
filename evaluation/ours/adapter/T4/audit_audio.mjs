/** Independent PCM sequence and receiver-cadence audit; no ASR/goal labels. */
import{readFileSync,writeFileSync,existsSync}from'node:fs';import{join}from'node:path';import{createHash}from'node:crypto';import{readWavPcm}from'./audio-client.mjs';
const directory=process.argv[2],lines=p=>existsSync(p)?readFileSync(p,'utf8').split('\n').filter(Boolean).map(JSON.parse):[];
const received=lines(join(directory,'audio_received.jsonl')),events=lines(join(directory,'client/events.jsonl')),hashes=received.map(r=>r.sha256).join('|');let offset=0;const results=[];
for(const queued of events.filter(e=>e.type==='client.input_clip_queued')){
 const clipId=queued.turn_id,pcm=readWavPcm(queued.source_file),frames=[];
 for(let i=0;i<pcm.length;i+=640){const b=Buffer.alloc(640);pcm.copy(b,0,i,Math.min(pcm.length,i+640));frames.push(createHash('sha256').update(b).digest('hex'))}
 const key=frames.join('|'),position=hashes.indexOf(key,offset),start=position<0?-1:hashes.slice(0,position).split('|').length-1;const r=start<0?[]:received.slice(start,start+frames.length);if(position>=0)offset=position+key.length;
 const send=events.filter(e=>e.type==='client.input_frame'&&e.clip_id===clipId),stats=a=>{const dt=a.slice(1).map((r,i)=>1000*(r.system_monotonic-a[i].system_monotonic));const ratio=a.length?(a.at(-1).system_monotonic-a[0].system_monotonic+.02)/(frames.length*.02):null;return{frames:a.length,max_gap_ms:dt.length?Math.max(...dt):null,duration_ratio:ratio}};
 const sender=stats(send),receiver=stats(r),passed=r.length===frames.length&&send.length===frames.length&&[sender,receiver].every(x=>x.duration_ratio>=.95&&x.duration_ratio<=1.05&&x.max_gap_ms<100);
 results.push({clip_id:clipId,exact_received_pcm:r.length===frames.length,sender,receiver,passed});
}
const report={schema:'audio-clock-admission-v1',frame_ms:20,ratio_bounds:[.95,1.05],max_gap_ms:100,clips:results,passed:results.length>0&&results.every(r=>r.passed)};
writeFileSync(join(directory,'AUDIO_QUALITY.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({clips:results.length,passed:report.passed}));if(!report.passed)process.exitCode=2;
