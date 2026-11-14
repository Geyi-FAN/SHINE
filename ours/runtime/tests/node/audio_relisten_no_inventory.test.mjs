import test from 'node:test';
import assert from 'node:assert/strict';
import {needsAudioRelisten,selectStreamingGroundingText,streamingGroundingAlternative} from '../../voice/dist/tools/robot-audio-relisten.js';
import {LiveSession} from '../../voice/dist/orchestrator/live-session.js';

const primary='Open the top drawer and put the ball inside.';
const secondary='Open the top drawer and put the bowl inside.';

test('privacy-redacted inventory does not disable unknown noun relisten',()=>{
    assert.equal(needsAudioRelisten(primary,null),true);
    assert.equal(needsAudioRelisten(secondary,null),false);
    assert.equal(needsAudioRelisten('Cancel the bull task.',undefined),true);
    assert.equal(needsAudioRelisten('Put it back.',null),false);
});
test('independent same-utterance noun proof works without simulator inventory',()=>{
    assert.equal(selectStreamingGroundingText(primary,secondary,null),secondary);
    assert.equal(selectStreamingGroundingText(primary,primary,null),undefined);
});
for(const wrong of [
    'Close the top drawer and put the bowl inside.',
    'Open the middle drawer and put the bowl inside.',
    'Do not open the top drawer and put the bowl inside.',
    'Open the top drawer and put the cheese inside.',
])test('no changed action, layer, negation, or unrelated noun: '+wrong,()=>{
    assert.equal(streamingGroundingAlternative(primary,wrong,null),false);
});
test('unrelated absent noun is not a phonetic replacement',()=>{
    assert.equal(streamingGroundingAlternative('Put the apple in the drawer.','Put the bowl in the drawer.',null),false);
});
test('actual LiveSession emits acoustic-only evidence with no scene/reference',async()=>{
    const old=process.env.ROBOT_AUDIO_RELISTEN;
    process.env.ROBOT_AUDIO_RELISTEN='1';
    try {
        const context={stopping:false,taskInputVersion:5,realtimeGeneration:2,speechAudioTotal:32000,
            fastStopOnsets:[{version:5,generation:2,audioMs:0,identity:Promise.resolve({scene_inventory:null}),asrPrefix:secondary}]};
        const events=[];
        const receiver={active:context,log:{write:(...args)=>events.push(args)}};
        const result=await LiveSession.prototype.prepareAudioEvidence.call(receiver,context,primary,5,2);
        assert.equal(result.transcript,secondary);
        assert.equal(result.channel,'independent_streaming_asr');
        assert.equal(result.reference_sent,false);
        assert.equal(result.scene_sent,false);
        context.taskInputVersion++;
        assert.equal(await LiveSession.prototype.prepareAudioEvidence.call(receiver,context,primary,5,2),undefined);
    } finally {
        if(old===undefined)delete process.env.ROBOT_AUDIO_RELISTEN;else process.env.ROBOT_AUDIO_RELISTEN=old;
    }
});
