"""Reuse an already-authorized exact training sentence; never write a subgoal."""
import re


def text_key(value):
    return re.sub(r'\s+', ' ', str(value).strip().lower()).rstrip('.!?。！？')


def exact_authorized_task(state, raw, catalog):
    normalization = getattr(state, 'normalization', getattr(state, 'instruction_normalization', None))
    if normalization != 'exact_training_template':
        return False
    if raw != getattr(state, 'instruction', None):
        return False
    if not any(text_key(raw) == text_key(s['canonical_task']) for s in catalog):
        return False
    record = getattr(state, 'task_record', None) or {}
    contract = record.get('candidate_contract') or {}
    # An exact sentence must never hide additional obligations in side fields.
    for field in ('preconditions', 'persistent_constraints', 'reference_memory_ids'):
        if record.get(field) or contract.get(field):
            return False
    return True


def reused_task(raw):
    return dict(raw_user_message=raw, output=dict(execution_task=raw,semantic_changes=[],
                rationale='Keep the already-authorized exact training sentence verbatim; no rewrite or added goal'),
                attempts=[],seconds=0.,reused=True,source='authorized_exact_training_sentence',
                wording_agent_called=False)
