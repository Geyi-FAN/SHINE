import assert from'node:assert/strict';
import{robotActionRequest,robotReplyDecision}from'../../voice/dist/tools/robot-turn.js';
for(const text of ['Keep it off and open the middle drawer instead.','Keep it off and push the plate to the front of the stove instead.','Leave the bowl there and put the cheese in it.']){
 assert.equal(robotActionRequest(text),true);
 const t={inputId:'i',version:1,generation:1,text,attempted:false,repaired:false,receipt:{status:'rejected',code:'robot_constraints_missing',executed:false,dispatch_attempted:false}};
 assert.equal(robotReplyDecision(t,'没有受理'),'repair');
 assert.notEqual(robotReplyDecision({...t,attempted:true},'没有受理'),'repair');
 assert.notEqual(robotReplyDecision({...t,receipt:{status:'unknown'}},'没有受理'),'repair');
 assert.notEqual(robotReplyDecision({...t,repaired:true,repairAttempts:2},'没有受理'),'repair');
}
for(const text of ['Keep it off.','Keep the bowl there and do not open the drawer.','What does keep it off mean?','Do not stop the robot.'])assert.equal(robotActionRequest(text),false);
console.log('19 command/negative/replay-bound assertions passed; no model/audio call');
