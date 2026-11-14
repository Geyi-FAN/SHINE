import fs from 'node:fs';import path from 'node:path';import {pathToFileURL}from'node:url';import{createHash}from'node:crypto';
const N='/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114';
const old='/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_T1_direct_20261112/code/runtime';
const cfg=JSON.parse(fs.readFileSync('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_final_c3r_20261110/private/voice_lane0.json'));
const qa=cfg.providers.visual_qa,key=fs.readFileSync(qa.apiKeyFile,'utf8').trim();
const modules={old:await import(pathToFileURL(old+'/voice/dist/realtime/robot-visual-analysis.js')),candidate:await import(pathToFileURL(N+'/code/runtime/voice/dist/realtime/robot-visual-analysis.js'))};
const cases=JSON.parse(fs.readFileSync(N+'/diagnostics/QA_REPLAY6.json'));const rows=[];
for(let i=0;i<cases.length;i++)for(const variant of(i%2?['candidate','old']:['old','candidate'])){
 const c=cases[i],body=fs.readFileSync(c.image_file);if(createHash('sha256').update(body).digest('hex')!==c.image_sha256)throw Error('Historical image hash changed');
 const dir=N+'/diagnostics/qa6/'+c.case_id+'/'+variant;fs.mkdirSync(dir,{recursive:true});process.env.VOICE_T6_QA_AUDIT=dir+'/qa_audit.jsonl';
 const row={case_id:c.case_id,variant,began:Date.now()/1000,image_sha256:c.image_sha256,original_total_budget_s:14,not_robot_or_audio_benchmark:true};
 try{const a=await modules[variant].analyzeRobotImage({endpoint:qa.endpoint,apiKey:key,question:c.question,image:body.toString('base64')});row.status='completed';row.answer=a.answer;}
 catch(e){row.status='failed';row.errorName=e?.name;row.message=String(e?.message??e).replaceAll(key,'[redacted]').slice(0,400)}
 row.seconds=Date.now()/1000-row.began;rows.push(row);fs.writeFileSync(N+'/reports/QA_REPLAY6_PROGRESS.json',JSON.stringify({rows,planned:12,completed:rows.length},null,2)+'\n');console.log(JSON.stringify(row));
}
fs.writeFileSync(N+'/reports/QA_REPLAY6_COMPLETED.json',JSON.stringify({rows,planned:12,completed:rows.length,no_actions:true,no_gold_answers_provided:true},null,2)+'\n');
