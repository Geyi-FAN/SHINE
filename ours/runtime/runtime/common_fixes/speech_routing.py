"""Carry validated current-input acoustic evidence into existing native gates.

No new aliases or tasks: original native admission runs first and again after
an identity-bound read-only revalidation of the stored acoustic evidence.
"""
import copy,json
from types import SimpleNamespace
from contextlib import nullcontext
import native_execution
from speech_relisten import validated_relisten


def native_candidate(state,fresh_episode_task,held_object):
    # Complete ordinary tasks retain their existing authorization/obligation
    # gates. The executor supports a complete-task text mode without subgoals.
    with getattr(state,'lock',nullcontext()):
        return _candidate_locked(state,fresh_episode_task,held_object)

def _candidate_locked(state,fresh_episode_task,held_object):
    skill,reason=native_execution.native_candidate(state,fresh_episode_task,held_object)
    if reason!='unresolved_ball_bowl_conflict':return skill,reason
    record=state.task_record or {};check=record.get('semantic_check')or{}
    if (record.get('episode_id')!=state.episode or record.get('task_id')!=state.task_id
            or check.get('decision')!='checked' or check.get('audio_relisten_grounding_used')is not True
            or record.get('source')!='qwen_realtime_current_user' or not record.get('voice_input_id')):
        return skill,reason
    row=state.db.execute('SELECT u.text,e.payload FROM utterances u JOIN events e ON e.id=u.event_id WHERE u.id=? AND u.episode=?',
        (record['voice_input_id'],state.episode)).fetchone()
    if not row or row[0]!=record.get('user_utterance'):return skill,reason
    evidence=json.loads(row[1]).get('asr_evidence')
    resolved=validated_relisten(row[0],evidence,state.instruction,state.scene_inventory)
    if not resolved or resolved!=check.get('grounding_utterance'):return skill,reason
    proof=dict(kind='native_route_acoustic_proof.v1',episode_id=state.episode,task_id=state.task_id,
        voice_input_id=record['voice_input_id'],primary=row[0],resolved_instruction=resolved,
        audio_evidence=copy.deepcopy(evidence),source='same_input_stored_audio_only_revalidation')
    candidate_record=copy.deepcopy(record);candidate_record['speech_correction_evidence']=proof
    proxy=SimpleNamespace(policy_metadata=state.policy_metadata,instruction=state.instruction,
        task_record=candidate_record,deferred_task=state.deferred_task)
    chosen,admission=native_execution.native_candidate(proxy,fresh_episode_task,held_object)
    if chosen:
        # Provenance is recorded, raw user text remains untouched.
        record['speech_correction_evidence']=proof
        state.event('native_acoustic_evidence_bound',dict(episode_id=state.episode,task_id=state.task_id,
            voice_input_id=record['voice_input_id'],primary=row[0],resolved_instruction=resolved))
    return chosen,admission
