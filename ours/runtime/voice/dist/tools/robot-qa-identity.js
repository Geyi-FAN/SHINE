/** Same semantic task across completion; new user speech cancels stale QA. */
export function robotQASubject(s) {
    if (typeof s['episode_id'] !== 'string' || typeof s['task_version'] !== 'number')
        throw Error('robot scene identity unavailable');
    return JSON.stringify([s['episode_id'], s['task_id'],
        typeof s['task_intent_revision'] === 'number' ? s['task_intent_revision'] : s['task_version']]);
}
