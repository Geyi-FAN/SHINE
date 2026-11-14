/** Full tool admission with a fake authenticated transport; no real motion. */
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {dispatchRobotTool} from '../../voice/dist/tools/robot.js';
const temp=mkdtempSync(join(tmpdir(),'t4-reference-'));
const token=join(temp,'token');writeFileSync(token,'local-test-token');
const saved={url:process.env.ROBOT_GATEWAY_URL,token:process.env.ROBOT_GATEWAY_TOKEN_FILE,fetch:globalThis.fetch};
process.env.ROBOT_GATEWAY_URL='http://127.0.0.1:12345';process.env.ROBOT_GATEWAY_TOKEN_FILE=token;
const user='Keep it off and open the middle drawer instead.';
const instruction='keep the stove off and open the middle drawer of the cabinet';
const current={episode_id:'ep',task_id:'task',task_version:2,instruction_memory_id:'actual-id',unique_source_object:false};
const record={task_id:'task',instruction_memory_id:'actual-id',is_current:true,candidate_contract:{entities:['stove'],semantic_check:{decision:'checked'}}};
let memory={episode_id:'ep',current_reference:current,task_selection:{candidates:[record]}};
const requests=[];let n=0;
function equal(a,b){assert.deepEqual(a,b);n++;}
globalThis.fetch=async(url,options)=>{
 const request=JSON.parse(options.body);requests.push(request);
 if(request.name==='robot_query_memory')return Response.json(memory);
 assert.equal(request.name,'robot_revise_task');
 return Response.json({status:'accepted',executed:true,task_version:3});
};
try{
 const args={episode_id:'ep',expected_task_version:'2',instruction};
 const result=await dispatchRobotTool('robot_revise_task',JSON.stringify(args),'request',user,'input');
 equal(JSON.parse(result.receipt).status,'accepted');
 equal(requests.map(r=>r.name),['robot_query_memory','robot_revise_task']);
 equal(requests[1].args.memory_ids,['actual-id']);
 equal(requests[1].args.instruction,instruction);
 equal(requests[1].args.expected_task_version,2);
 equal(requests[1].args.user_utterance,user);
 requests.length=0;
 memory={...memory,task_selection:{candidates:[{...record,candidate_contract:{entities:['stove','bowl'],semantic_check:{decision:'checked'}}}]}};
 const ambiguous=await dispatchRobotTool('robot_revise_task',JSON.stringify(args),'ambiguous',user,'input2');
 equal(JSON.parse(ambiguous.receipt).code,'robot_reference_requires_memory');
 equal(requests.map(r=>r.name),['robot_query_memory']);
 requests.length=0;memory={episode_id:'ep',current_reference:current,task_selection:{candidates:[record]}};
 const stale=await dispatchRobotTool('robot_revise_task',JSON.stringify({...args,expected_task_version:1}),'stale',user,'input3');
 equal(JSON.parse(stale.receipt).code,'robot_reference_requires_memory');
 equal(requests.map(r=>r.name),['robot_query_memory']);
 console.log(`${n} complete-dispatch assertions passed: actual memory ID only; instruction/version retained; ambiguity/stale blocks mutation`);
}finally{
 globalThis.fetch=saved.fetch;
 for(const[k,v]of[['ROBOT_GATEWAY_URL',saved.url],['ROBOT_GATEWAY_TOKEN_FILE',saved.token]]){if(v===undefined)delete process.env[k];else process.env[k]=v;}
 rmSync(temp,{recursive:true});
}
