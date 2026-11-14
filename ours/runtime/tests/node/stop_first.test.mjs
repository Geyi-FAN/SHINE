import test from 'node:test';
import assert from 'node:assert/strict';
import {controlIntent}from'../../voice/dist/tools/robot-control-semantics.js';
import {independentStop,stopSegmentAllowed}from'../../voice/dist/tools/robot-fast-stop.js';
for(const text of ['Stop first.','Pause first.','Please stop first.','Stop now!','Please halt immediately.'])
 test('unconditional immediate short stop: '+text,()=>{assert.equal(controlIntent(text),'pause');assert.equal(independentStop(text),true);assert.equal(stopSegmentAllowed(text,''),true)});
for(const text of ['First.',"Do not stop first.",'Stop first if the bowl moves.','Stop after this task finishes.','What does stop first mean?','He said "Stop first."','"Stop first."'])
 test('noncommand or conditional text does not pause: '+text,()=>assert.equal(independentStop(text),false));
test('earlier negation still protects a short redecoded phrase',()=>assert.equal(stopSegmentAllowed('Stop first.','Do not.'),false));
test('full compound remains a planning turn with only leading Stop authority',()=>{
 const text='Stop. First, please close the middle drawer. Then put the wine bottle on top of the cabinet.';
 assert.equal(controlIntent(text),undefined);assert.equal(independentStop(text),false);assert.equal(stopSegmentAllowed(text,''),true);
});
