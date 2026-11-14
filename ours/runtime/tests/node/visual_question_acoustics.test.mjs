import test from 'node:test';import assert from 'node:assert/strict';
import {visualQuestionFromAudio} from '../../voice/dist/tools/robot-visual-audio-question.js';
const primary='Is the ball on the plate?';
function turn(changes={}){return {text:primary,asrEvidence:{kind:'audio_only_grounding.v2',primary,transcript:'Is the bowl on the plate?',reference_sent:false,scene_sent:false,...changes}}}
test('actual question uses the independently heard noun',()=>{assert.equal(visualQuestionFromAudio(turn()).question,'Is the bowl on the plate?')});
test('raw question is preserved without acoustic evidence',()=>{assert.equal(visualQuestionFromAudio({text:primary}).question,primary)});
test('evidence from another input or a reference/scene-assisted guess is rejected',()=>{for(const change of[{primary:'another input'},{reference_sent:true},{scene_sent:true},{kind:'scene_vocab_audio_review.v3'}])assert.equal(visualQuestionFromAudio(turn(change)).question,primary)});
test('negation and relation cannot change',()=>{for(const transcript of["Isn't the bowl on the plate?",'Is the bowl in the plate?'])assert.equal(visualQuestionFromAudio(turn({transcript})).question,primary)});
test('a confirmed spoken ball is not silently replaced with bowl',()=>assert.equal(visualQuestionFromAudio(turn({transcript:primary})).question,primary));
test('known source object cannot be replaced',()=>assert.equal(visualQuestionFromAudio({text:'Is the plate on the stove?',asrEvidence:turn().asrEvidence}).question,'Is the plate on the stove?'));
