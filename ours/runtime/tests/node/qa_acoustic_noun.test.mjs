import test from 'node:test';import assert from 'node:assert/strict';
import {needsAudioRelisten,streamingGroundingAlternative} from '../../voice/dist/tools/robot-audio-relisten.js';
test('ambiguous question noun asks for audio evidence without editing the noun',()=>assert.equal(needsAudioRelisten('Is the ball on the plate?',null),true));
test('recognized question and plural nouns do not force another listen',()=>{for(const s of ['Is the bowl on the plate?','Are the bowls on the plate?','Where is the wine bottle?'])assert.equal(needsAudioRelisten(s,null),false)});
test('same-utterance independent audio may distinguish bowl from ball',()=>assert.equal(streamingGroundingAlternative('Is the ball on the plate?','Is the bowl on the plate?',null),true));
test('a different affirmative/negative question cannot be substituted',()=>assert.equal(streamingGroundingAlternative('Is the ball on the plate?',"Isn't the bowl on the plate?",null),false));
test('confirmed spoken ball is not automatically renamed bowl',()=>assert.equal(streamingGroundingAlternative('Is the ball on the plate?','Is the ball on the plate?',null),false));
