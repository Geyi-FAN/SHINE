import assert from 'node:assert/strict';
import { independentStop, stopCommandPresent, stopSegmentAllowed } from '../../voice/dist/tools/robot-fast-stop.js';
import { controlIntent } from '../../voice/dist/tools/robot-control-semantics.js';
let n=0;
for (const s of ['Stop. Please put the bowl on the plate.','Stop! Put the cream cheese in the bowl.','Please stop now. First return the bottle, then put the cheese in the bowl.','Pause. Open the middle drawer.','Stop. Do not put the bowl on the stove.','Stop.']) {
  assert.equal(stopCommandPresent(s),true,s);assert.equal(stopSegmentAllowed(s,'',''),true,s);n+=2;
}
for (const s of ["Don't stop. Put the bowl on the plate.",'If I say stop, put it there.','What does stop mean?','He said "Stop. Put the bowl there."','Stop if the bowl moves.','Stopwatch on the table.','Put the bowl on the stove.','After this task, stop.','Never stop.','Do not stop.']) {
  assert.equal(stopCommandPresent(s),false,s);n++;
}
assert.equal(controlIntent('Stop. Please put the bowl on the plate.'),undefined);n++;
assert.equal(stopSegmentAllowed('Stop. Put the bowl on the plate.','Do not',''),false);n++;
assert.equal(stopSegmentAllowed('Stop. Put the bowl on the plate.','','if'),false);n++;


assert.equal(independentStop('Stop. Please put the bowl on the plate.'),false);
assert.equal(independentStop('Stop.'),true);

n+=2;console.log(JSON.stringify({passed:true,assertions:n,tail_request_left_for_agent:true}));
