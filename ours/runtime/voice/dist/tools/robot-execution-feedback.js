/** Observed policy work only. A command receipt alone never starts this notice. */
export function executionNoticeCurrent(notice, status) {
    return !!notice && status?.state === 'running' &&
        status.episode_id === notice.episodeId && status.task_id === notice.taskId &&
        status.task_version === notice.taskVersion &&
        status.task_intent_revision === notice.intentRevision &&
        Number.isFinite(status.policy_action_steps) && status.policy_action_steps > 0;
}

export class RobotExecutionTracker {
    constructor() { this.admittedKeys = new Set(); }
    observe(status) {
        if (!status?.episode_id || !status.task_id || !Number.isFinite(status.task_intent_revision)) return;
        // Pause/resume is the same intent: it must not announce a second start.
        const key = JSON.stringify([status.episode_id, status.task_id, status.task_intent_revision]);
        if (['paused','completed','cancelled','budget_exhausted','needs_review','error'].includes(status.state)) {
            this.admittedKeys.add(key);
            return;
        }
        if (this.admittedKeys.has(key)) return;
        const notice = {key, episodeId:status.episode_id, taskId:status.task_id,
            taskVersion:status.task_version, intentRevision:status.task_intent_revision,
            text:'机械臂已开始执行当前任务。'};
        return executionNoticeCurrent(notice,status) ? notice : undefined;
    }
    admitted(key) { this.admittedKeys.add(key); }
}
