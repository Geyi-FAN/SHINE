import { explicitObjectSelection } from './robot-object-evidence.js';
/** Validate redundant metadata against live identity; never refresh a stale call. */
export function canDropTaskId(args, state) {
    return typeof args['task_id'] === 'string' && !!args['task_id'] &&
        args['task_id'] === state['task_id'] && args['episode_id'] === state['episode_id'] &&
        Number.isSafeInteger(args['expected_task_version']) &&
        args['expected_task_version'] === state['task_version'];
}
/** A preserved opening is not an instruction to open/close that drawer. */
export function preservationError(raw, candidate) {
    // A literal repeated OBJECT slot is dialogue identity, not "keep still".
    // Parse only a same-object prefix; the complete remaining physical request
    // (including any trailing real keep/release conditions) remains checked.
    raw = explicitObjectSelection(raw)?.groundingText ?? raw;
    // Same lossless contract for English, Mandarin and code-switched speech.
    // Reject only: the Agent must regenerate the full instruction itself.
    const preserve = /\b(?:keep|maintain|preserve)\b|\bleave\b[^.!?;]{0,65}\b(?:there|where|position|place|unchanged|as it is)\b|保持|保留|留在|留着|不要改变|不要移动|不要动/i.test(raw);
    const kept = /\b(?:keep(?:ing|s)?|leav(?:e|ing)|remain(?:ing|s)?|maintain(?:ing|s)?|preserv(?:e|ing))\b|\b(?:do not|don't|without)\b[^.!?;]{0,35}\b(?:mov(?:e|ing)|chang(?:e|ing)|turn(?:ing)?)\b/i.test(candidate);
    if (preserve && !kept) {
        return 'The actual user request contains a KEEP/LEAVE requirement, including Chinese 保持/留在/留着. No action was dispatched. Regenerate the COMPLETE same request with every physical goal and persistent constraint. Resolve the referent from actual current task/memory; do not invent an object or remove a clause.';
    }
    const explicitOff = /(?:\bkeep\b|\bleave\b|保持|保留)[^.!?;。；]{0,60}\boff\b/i.test(raw);
    const keptOff = /\boff\b|\b(?:do not|don't|never)\b[^.!?;]{0,35}\b(?:turn|switch)\b[^.!?;]{0,35}\bon\b/i.test(candidate);
    if (explicitOff && !keptOff) {
        return 'The user explicitly said to keep the referenced device OFF. No action was dispatched. Preserve that binary state as well as the new action, resolving its actual referent from current task/memory. Do not change off to on or drop it.';
    }
    const historical = /\b(?:keep|maintain|leave|preserve)\b[^.!?;]{0,100}\b(?:(top|middle)\s+)?drawer\b[^.!?;]{0,100}\b(?:instruction[- ]switch|current|same|unchanged|as it is)\b/i.exec(raw);
    if (!historical)
        return undefined;
    const scope = /\b(?:keep(?:ing)?|maintain(?:ing)?|leav(?:e|ing)|preserv(?:e|ing))\b[^.!?;]{0,100}\bdrawer\b([^.!?;]*)/i.exec(candidate);
    if (!scope || (historical[1] && !new RegExp('\\b' + historical[1] + '\\s+drawer\\b', 'i').test(scope[0])) || !/opening|openness|state|unchanged|as it is/i.test(scope[1]) ||
        /\b(?:open|closed|shut)\b/i.test(scope[1])) {
        return 'Preserve the drawer at its instruction-switch opening. Do not replace this by keep-open/keep-closed, opening or closing it. Generate the COMPLETE same user request; keep every clause.';
    }
    return undefined;
}
