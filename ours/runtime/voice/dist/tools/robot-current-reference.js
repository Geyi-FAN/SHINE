/** Bind a real current instruction ID, never generate a task or world fact. */
export function uniqueCurrentInstructionReference(memory, args, userRequest) {
    const current = memory?.current_reference;
    const candidates = memory?.task_selection?.candidates;
    if (memory?.episode_id !== args.episode_id || current?.episode_id !== args.episode_id
        || current?.task_version !== args.expected_task_version
        || typeof current?.instruction_memory_id !== 'string' || !current.instruction_memory_id
        || typeof current?.task_id !== 'string' || !current.task_id
        || !Array.isArray(candidates)
        || /\bor\b|或者|还是|earlier|previous|上一个|之前/i.test(userRequest)) return undefined;
    const matching = candidates.filter(t => t.is_current === true
        && t.task_id === current.task_id
        && t.instruction_memory_id === current.instruction_memory_id);
    if (matching.length !== 1) return undefined;
    if (current.unique_source_object === true) return current.instruction_memory_id;
    // A binary fixture operation (e.g. switching a stove) has no transported
    // source object. Use the checked instruction's sole named entity only for
    // a preservation pronoun. Multiple named entities still require selection.
    if (!/\b(?:keep|maintain|leave)\s+it\b/i.test(userRequest)) return undefined;
    const contract = matching[0].candidate_contract;
    if (contract?.semantic_check?.decision !== 'checked' || !Array.isArray(contract.entities)) return undefined;
    const entities = [...new Set(contract.entities.filter(e => typeof e === 'string' && e.length > 0 && e !== 'table'))];
    return entities.length === 1 ? current.instruction_memory_id : undefined;
}
