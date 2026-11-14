"""Bounded user speech evidence; never generate an instruction or start motion."""
import re
import time
from grounding import mentions
from interaction import classify_utterance


def dialogue_evidence(state):
    rows = state.db.execute(
        "SELECT u.id,u.text,e.time,e.version FROM utterances u JOIN events e ON e.id=u.event_id "
        "WHERE u.episode=? ORDER BY e.rowid DESC LIMIT 6", (state.episode,)
    ).fetchall()
    recent = [dict(input_id=i,text=t,time=when,task_version=v) for i,t,when,v in rows
              if 0 <= time.time()-when <= 90]
    result = dict(source='same_episode_user_final_transcripts', recent_user_utterances=recent,
                  correction_context=None, note='Evidence only; consumed requests are not permission to replay. The model writes the full instruction.')
    if len(recent) < 2:
        return result
    current, previous = recent[:2]
    # Only the immediately adjacent, unresolved command with an unknown name.
    # This does not reinterpret a new full command, QA, assent or an old task.
    fragment = current['text'].strip()
    fragment = re.sub(r'^(?:不对[，,]?|我说的是|说的是|是指|是)+', '', fragment).strip('。！! ，,')
    entities = {e for _,e in mentions(fragment) if e}
    if (len(fragment)>12 or len(entities)!=1 or classify_utterance(current['text'])!='cloud_decision'
            or classify_utterance(previous['text'])!='cloud_decision'
            or re.search(r'放|拿|取|开|关|继续|恢复|取消|等|再|然后|不要|别|[?？]',fragment)
            or not re.search(r'打开|开启|关闭|关上|把.+放|put|open|close|turn\s+(?:on|off)',previous['text'],re.I)
            or re.search(r'不要|别|不许|如果|假如|[?？“”「」]',previous['text'])
            or any(e for _,e in mentions(previous['text']))
            or current['time']-previous['time']>45
            or time.time()>previous['time']+45
            or current['task_version']!=state.version or previous['task_version']!=state.version):
        return result
    # Any intervening action/hold ends the correction lease, even if its intent
    # would otherwise look similar. New episodes are excluded by the query.
    changed = state.db.execute(
        "SELECT 1 FROM events WHERE episode=? AND time>? AND kind IN "
        "('control_hold','task_instruction','task_completed','task_cancelled','clarification_created','proposal_created') LIMIT 1",
        (state.episode, previous['time']),
    ).fetchone()
    if not changed:
        result['correction_context'] = dict(
            source_utterances=[previous,current],
            correction_input_ids=[previous['input_id'],current['input_id']],
            relation='current_entity_fragment_corrects_adjacent_unresolved_request',
            expires_at=previous['time']+45,
        )
    return result


def validate_correction_instruction(context, instruction):
    """Check retained action semantics, without constructing model output."""
    original=context['source_utterances'][0]['text']
    correction=context['source_utterances'][-1]['text']
    entities={e for _,e in mentions(correction) if e}
    if entities == {'stove'}:
        on=bool(re.search(r'打开|开启|turn\s+on',original,re.I))
        off=bool(re.search(r'关闭|关上|turn\s+off',original,re.I))
        if (on and not re.search(r'\bturn\s+on\b',instruction,re.I)
                or off and not re.search(r'\bturn\s+off\b',instruction,re.I)):
            raise ValueError('correction_action_mismatch: preserve the original action verb')
