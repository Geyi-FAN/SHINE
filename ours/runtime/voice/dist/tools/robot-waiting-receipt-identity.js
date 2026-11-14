/** Delivery-only proof. This function never schedules or mutates a task. */
export function waitingReceiptKey(turn, receipt, operation, callId) {
    const prior = turn?.status, pending = receipt?.deferred_task;
    const inputId = typeof callId === 'string' && callId && turn?.inputId
        ? (turn.inputId.startsWith(callId + ':') ? turn.inputId : callId + ':' + turn.inputId)
        : undefined;
    // An automatic, verified completion of the SAME predecessor can occur
    // between status and schedule. Queueing itself does not bump its version.
    // This is delivery proof only, never scheduling/early-handoff permission.
    const completed = receipt?.state === 'completed' && receipt.completion === 'verified' &&
        receipt.agent_execution?.completion_current_verified === true &&
        receipt.agent_execution.task_id === receipt.task_id;
    const sameVersion = receipt?.task_version === prior?.task_version;
    const completionTransition = completed && ['running','verifying'].includes(prior?.state) &&
        receipt.task_version === prior.task_version + 1;
    if (operation !== 'robot_schedule_task' || !prior || !pending || !inputId ||
        receipt.status !== 'scheduled' || receipt.executed !== false ||
        !['running', 'verifying', 'completed'].includes(prior.state) ||
        (!['running', 'verifying'].includes(receipt.state) && !completed) ||
        (prior.state === 'completed' && !completed) ||
        !prior.task_id || receipt.task_id !== prior.task_id ||
        !prior.episode_id || receipt.episode_id !== prior.episode_id ||
        !Number.isFinite(prior.task_version) || (!sameVersion && !completionTransition) ||
        !Number.isFinite(prior.task_intent_revision) || receipt.task_intent_revision !== prior.task_intent_revision ||
        pending.episode_id !== receipt.episode_id ||
        pending.predecessor_task_id !== receipt.task_id ||
        pending.voice_input_id !== inputId ||
        !['waiting_for_verified_completion','waiting_for_native_release'].includes(pending.state) ||
        !pending.deferred_id || pending.transaction_id !== pending.deferred_id ||
        !Number.isFinite(pending.transaction_revision) || pending.transaction_revision < 1)
        return undefined;
    return JSON.stringify([turn.inputId, receipt.episode_id, receipt.task_id,
        receipt.task_version, operation, pending.deferred_id, pending.transaction_revision]);
}
