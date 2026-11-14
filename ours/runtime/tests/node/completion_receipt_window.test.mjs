import test from 'node:test';
import assert from 'node:assert/strict';
import { robotTerminalText, robotTerminalNoticeCurrent } from '../../voice/dist/tools/robot-feedback.js';

test('completed but still settling cannot produce a completed speech claim',()=>{
 const status={state:'completed',agent_execution:{completion_current_verified:true,completion_receipt:{ready:false}}};
 assert.equal(robotTerminalText(status),undefined);
 status.agent_execution.completion_receipt.ready=true;
 assert.match(robotTerminalText(status),/当前任务已完成/);
});

test('a once ready notice is rejected when current holding proof is lost',()=>{
 const status={episode_id:'e',task_id:'t',task_version:4,state:'completed',observation_time:Date.now()/1000,
   agent_execution:{completion_current_verified:true,completion_receipt:{ready:true}}};
 const notice={episodeId:'e',taskId:'t',taskVersion:4,state:'completed',text:robotTerminalText(status)};
 assert.equal(robotTerminalNoticeCurrent(notice,status),true);
 status.agent_execution.completion_receipt.ready=false;
 assert.equal(robotTerminalNoticeCurrent(notice,status),false);
});
