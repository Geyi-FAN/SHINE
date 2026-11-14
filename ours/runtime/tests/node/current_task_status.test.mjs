import test from 'node:test';
import assert from 'node:assert/strict';
import {robotStatusQuestionAnswer} from '../../voice/dist/tools/robot-feedback.js';
const status={episode_id:'e',task_id:'real-task',state:'running',instruction:'put the bowl on the stove'};
for(const text of ['What are you doing?','What are you doing now?','What are you doing right now?',"What's the task right now?",'What is the current task?','当前在执行什么任务？']){
 test('fresh task identity for '+text,()=>{
  const answer=robotStatusQuestionAnswer(text,status);assert.ok(answer);assert.match(answer,/put the bowl on the stove/);assert.match(answer,/正在执行|is running/);assert.doesNotMatch(answer,/空闲/);
 });
}
for(const state of ['paused','completed','budget_exhausted','needs_review','cancelled'])test('preserve actual mode '+state,()=>{
 const answer=robotStatusQuestionAnswer('What are you doing?',{...status,state});assert.match(answer,/put the bowl on the stove/);assert.doesNotMatch(answer,/当前空闲/);
});
test('truly idle is not a fabricated task',()=>assert.equal(robotStatusQuestionAnswer('What are you doing?',{state:'idle'}),'There is no active task.'));
for(const text of ["What's in the bowl?",'What color is the bowl?','Where are you taking the bowl?','What does stop mean?','What are you doing? Then open the middle drawer.'])test('does not replace unrelated question '+text,()=>assert.equal(robotStatusQuestionAnswer(text,status),undefined));
