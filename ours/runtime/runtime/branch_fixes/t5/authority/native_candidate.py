def native_candidate(state, fresh_episode_task, held_object):
    """Post-authorization routing. No benchmark ID or correct answer is read."""
    if not fresh_episode_task or held_object != 'none':
        return None, 'nonstandard_takeover_or_holding'
    if state.policy_metadata.get('executor') != 'smolvla_e3_v4':
        return None, 'different_model_profile'
    from instructions import normalize_instruction
    normalized, _ = normalize_instruction(state.instruction)
    skill = next((s for s in CATALOG if text_key(s['canonical_task']) == text_key(normalized)), None)
    if skill is None:
        return None, 'not_a_complete_native_task'
    record = state.task_record or {}
    candidate = record.get('candidate_contract') or {}
    intrinsic_pre = set(skill.get('intrinsic_preconditions', []))
    intrinsic_keep = set(skill.get('intrinsic_constraints', []))
    if (set(record.get('preconditions', [])) - intrinsic_pre
            or set(candidate.get('preconditions', [])) - intrinsic_pre
            or set(record.get('persistent_constraints', [])) - intrinsic_keep
            or set(candidate.get('persistent_constraints', [])) - intrinsic_keep
            or record.get('reference_memory_ids') or state.deferred_task):
        return None, 'extra_obligations_or_memory'
    evidence = record.get('clarification_evidence') or {}
    raw = evidence.get('resolved_instruction') if evidence.get('status') == 'resolved' else None
    raw = raw or record.get('user_utterance') or record.get('requested_instruction') or state.instruction
    # This is already-authorized routing, not permission to start. Preserve the
    # original record; only remove a terminal consent clause after its proposal
    # was genuinely consumed. Physical before/after/keep clauses remain intact.
    if record.get('confirmed_proposal_id'):
        routing_raw = re.sub(
            r'(?:,\s*|\s+)(?:but\s+)?ask\s+'
            r'(?:for\s+(?:my|our)\s+confirmation|me\s+to\s+confirm)\s+'
            r'before\s+(?:starting|you\s+start|execution|executing)\s*[.!]?\s*$',
            '', raw, flags=re.I,
        )
        if routing_raw.strip():
            raw = routing_raw
    # Never erase an obligation just because the accepted text resembles a task.
    if re.search(r'\b(?:keep|remain|without|unless|if|until|before|after|return|back|close|shut|not|never)\b|\bdon[’\x27]t\b|归位|放回|保持|不要|别动|如果|等.{0,8}(?:完成|结束)|关闭|关上', raw, re.I):
        return None, 'raw_request_has_extra_or_negative_clause'
    if skill['task_id'] != 3 and re.search(r'\b(?:then|next|also|afterwards)\b|然后|接着|再去', raw, re.I):
        return None, 'raw_request_has_additional_sequence'
    raw_normalized, _ = normalize_instruction(raw)
    exact_raw = text_key(raw_normalized) == text_key(skill['canonical_task'])
    check = record.get('semantic_check') or candidate.get('semantic_check') or {}
    trusted_resolution = check.get('decision') == 'checked'
    if not exact_raw and not trusted_resolution and not record.get('confirmed_proposal_id'):
        return None, 'raw_request_not_resolved'
    if re.search(r'\bball\b', raw, re.I) and not record.get('speech_correction_evidence'):
        return None, 'unresolved_ball_bowl_conflict'
    return copy.deepcopy(skill), 'complete_trained_task_in_standard_episode'
