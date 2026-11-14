/** Read-only QA consumes the same-input acoustic evidence already recorded.
 * No scene dictionary substitution, benchmark wording or image-based renaming.
 */
import {selectStreamingGroundingText} from './robot-audio-relisten.js';
export function visualQuestionFromAudio(turn) {
    const primary=String(turn?.text??'');
    const proof=turn?.asrEvidence;
    if(!proof||!['audio_only_grounding.v2','audio_only_relisten.v1'].includes(proof.kind)||
       proof.primary!==primary||proof.reference_sent!==false||proof.scene_sent!==false||
       typeof proof.transcript!=='string')
        return {question:primary,source:'original_user_transcript'};
    const alternative=selectStreamingGroundingText(primary,proof.transcript,undefined);
    return alternative?{question:alternative,source:'same_input_audio_only_evidence',primary}:
        {question:primary,source:'original_user_transcript'};
}
