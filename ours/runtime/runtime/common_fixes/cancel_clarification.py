"""Fence ambiguous named cancellations, never guess their intended object.

The question is attached to the real deferred transaction, not a new motion
proposal. Original ASR, active task, episode and transaction identity survive.
"""
import re
import time


def named_subject(text):
    if not isinstance(text, str) or re.search(r'[?？"“”「」]', text):
        return None
    words = ' '.join(re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower()))
    if not re.search(r'[\u4e00-\u9fff]', text):
        match = re.fullmatch(
            r'(?:please )?(?:cancel|skip) (?:the )?([a-z]+(?: [a-z]+){0,2}) task'
            r'(?: keep going| carry on| keep working)?', words)
        if match and not set(match[1].split()) & {
            'not', 'never', 'no', 'if', 'current', 'active', 'running',
            'queued', 'pending', 'waiting', 'next', 'all', 'any', 'every',
        }:
            return match[1]
        return None
    match = re.fullmatch(
        r'\s*(?:请)?取消([\u4e00-\u9fff]{1,5})(?:的)?任务[。.!！]*'
        r'(?:\s*(?:Keep going|Carry on|继续|继续当前任务)[。.!！]*)?\s*', text, re.I)
    if not match:
        return None
    noun = match[1].removesuffix('的')
    if re.search(r'不要|别|不|如果|当前|现在|全部|所有|等待|排队', noun):
        return None
    return noun


def named_entities(text):
    from grounding import mentions
    return {entity for _, entity in mentions(text) if entity}


def direct_named_cancel(text, pending, active=''):
    noun = named_subject(text)
    if not noun:
        return False
    requested = named_entities(noun)
    # Full object references only. A known but different object is never fixed.
    return bool(len(requested) == 1 and requested <= named_entities(pending or '')
                and not requested & named_entities(active or ''))


def ambiguous_question(state, text, input_id):
    slot = getattr(state, 'deferred_task', None)
    noun = named_subject(text)
    if (not slot or not noun or named_entities(noun)
            or slot.get('episode_id') != state.episode
            or slot.get('predecessor_task_id') != state.task_id
            or slot.get('expires_at', 0) <= time.time()
            or not input_id):
        return None
    return dict(
        schema='pending_cancel_clarification.v1', input_id=input_id,
        episode_id=state.episode, predecessor_task_id=state.task_id,
        deferred_id=slot['deferred_id'], original_transcript=text,
        unresolved_subject=noun, state='awaiting_explicit_task_reference',
        current_task_continues=True, pending_task_cancelled=False,
        question=(f'I heard "{noun}". Nothing was cancelled. '
                  'Please name the queued task.'),
        queued_instruction=slot['instruction'],
        created_at=time.time(), expires_at=slot['expires_at'])
