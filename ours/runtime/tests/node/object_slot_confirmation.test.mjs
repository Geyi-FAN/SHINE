import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {explicitObjectSelection} from '../../voice/dist/tools/robot-object-evidence.js';
import {preservationError} from '../../voice/dist/tools/robot-entry-guard.js';
import {dispatchRobotTool} from '../../voice/dist/tools/robot.js';

const raw='Keep the wine bottle as the object, but put it on the rack. Ask me to confirm the change.';
const literal=raw.replace('put it','put the wine bottle');
test('repeating the same source noun is the same dialogue object slot',()=>{
 for(const text of [raw,literal,literal.replace('put the wine bottle','put the bottle')]) {
  assert.ok(explicitObjectSelection(text));
  assert.equal(preservationError(text,'put the wine bottle on the rack'),undefined);
 }
});
test('identity prefix cannot erase a real physical requirement or a conflicting object',()=>{
 for(const text of [literal+' Keep the bowl still.', literal.replace('wine bottle as','bowl as'), 'Keep the wine bottle at its current position and open the drawer.'])
  assert.ok(preservationError(text,'put the wine bottle on the rack'));
 assert.equal(explicitObjectSelection('Keep the wine bottle as the object, but put the bowl on the rack.'),undefined);
});
test('actual dispatcher admits the model proposal once and preserves original user evidence',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'object-slot-'));
 const old={fetch:globalThis.fetch,url:process.env.ROBOT_GATEWAY_URL,token:process.env.ROBOT_GATEWAY_TOKEN_FILE};
 writeFileSync(join(dir,'token'),'local-test');process.env.ROBOT_GATEWAY_URL='http://127.0.0.1:12345';process.env.ROBOT_GATEWAY_TOKEN_FILE=join(dir,'token');
 const calls=[];globalThis.fetch=async(url,options)=>{const x=JSON.parse(options.body);calls.push(x);return Response.json({status:'needs_confirmation',executed:false})};
 try {
  const result=await dispatchRobotTool('robot_propose_task',JSON.stringify({episode_id:'ep',expected_task_version:0,instruction:'put the wine bottle on the rack'}),'request',literal,'input');
  assert.equal(result.ok,true);assert.equal(calls.length,1);assert.equal(calls[0].name,'robot_propose_task');
  assert.equal(calls[0].args.user_utterance,literal);assert.equal(calls[0].args.instruction,'put the wine bottle on the rack');
  calls.length=0;
  const rejected=await dispatchRobotTool('robot_propose_task',JSON.stringify({episode_id:'ep',expected_task_version:0,instruction:'put the wine bottle on the rack'}),'bad',literal+' Keep the bowl still.','input2');
  assert.equal(JSON.parse(rejected.receipt).code,'robot_constraints_missing');assert.equal(calls.length,0);
 }finally{
  globalThis.fetch=old.fetch;
  for(const[k,v]of[['ROBOT_GATEWAY_URL',old.url],['ROBOT_GATEWAY_TOKEN_FILE',old.token]])if(v===undefined)delete process.env[k];else process.env[k]=v;
  rmSync(dir,{recursive:true,force:true});
 }
});
