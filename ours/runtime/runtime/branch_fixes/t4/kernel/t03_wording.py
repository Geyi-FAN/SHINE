"""Reuse exact authorized training text with duplicated intrinsic conditions.

This does not supply operations, subgoals, coordinates or completion evidence.
Unexpected side conditions retain the original wording/validation path.
"""
from collections import Counter


def exact_intrinsic_task(state, raw, catalog):
    from t3repair.wording import text_key
    normalization = getattr(state, 'normalization', getattr(state, 'instruction_normalization', None))
    if normalization != 'exact_training_template' or raw != getattr(state, 'instruction', None):
        return False
    matched = [s for s in catalog if text_key(raw) == text_key(s.get('canonical_task', ''))]
    if len(matched) != 1:
        return False
    intrinsic = matched[0].get('intrinsic_preconditions')
    if not isinstance(intrinsic, list) or not intrinsic or not all(isinstance(s, str) for s in intrinsic):
        return False
    record = getattr(state, 'task_record', None) or {}
    if not isinstance(record, dict):
        return False
    candidate = record.get('candidate_contract') or {}
    if not isinstance(candidate, dict):
        return False
    if record.get('structure_source') != 'training_template_contract' or candidate.get('structure_source') != 'training_template_contract':
        return False
    if record.get('complete_instruction') != raw or candidate.get('instruction') != raw:
        return False
    if candidate.get('unresolved'):
        return False
    for item in (record, candidate):
        refs = item.get('reference_memory_ids') or []
        if not isinstance(refs, list) or not all(isinstance(s, str) for s in refs):
            return False
    if (record.get('reference_memory_ids') or []) != (candidate.get('reference_memory_ids') or []):
        return False
    for item in (record, candidate):
        preconditions = item.get('preconditions')
        if not isinstance(preconditions, list) or not all(isinstance(s, str) for s in preconditions):
            return False
        # Multiplicity matters; no subset or keyword approximation.
        if Counter(preconditions) != Counter(intrinsic) or item.get('persistent_constraints'):
            return False
        semantic = item.get('semantic_check') or {}
        if not isinstance(semantic, dict) or semantic.get('decision') != 'checked':
            return False
    return True


def install(module=None):
    if module is None:
        from t3repair import wording as module
    original = module.exact_authorized_task
    if getattr(original, '_t03_intrinsic_guard', False):
        return

    def checked(state, raw, catalog):
        return original(state, raw, catalog) or exact_intrinsic_task(state, raw, catalog)

    checked._t03_intrinsic_guard = True
    module.exact_authorized_task = checked
