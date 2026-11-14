/** A committed pending cancellation survives ONLY its predecessor completing. */
export function pendingCancellationReceipt(turn, expected, receipt, callId) {
    const pending=expected?.deferred_task;
    if(!pending || !callId || !turn?.inputId || turn.operation!=='robot_cancel_deferred' ||
       receipt?.status!=='deferred_cancelled' || receipt.executed!==false || receipt.deferred_task ||
       receipt.episode_id!==expected.episode_id || receipt.task_id!==expected.task_id ||
       !expected.task_id || !Number.isFinite(expected.task_intent_revision) ||
       receipt.task_intent_revision!==expected.task_intent_revision ||
       !Number.isFinite(expected.task_version))return false;
    const unchanged=receipt.task_version===expected.task_version && receipt.state===expected.state;
    const completed=receipt.task_version===expected.task_version+1 &&
       ['running','verifying'].includes(expected.state) && receipt.state==='completed' && receipt.completion==='verified';
    if(!unchanged&&!completed)return false;
    const inputId=turn.inputId.startsWith(callId+':')?turn.inputId:callId+':'+turn.inputId;
    const row=receipt.dialogue_transactions?.recent_terminal?.find(r=>r.transaction_id===pending.deferred_id);
    return !!row && row.kind==='deferred' && row.status==='cancelled' && row.reason==='user_cancelled' &&
       row.episode_id===receipt.episode_id && row.bound_task_id===receipt.task_id &&
       row.predecessor_task_id===receipt.task_id && row.task_intent_revision===receipt.task_intent_revision &&
       row.dispatch_blocked_by_input===inputId && !row.consumed_by_task_id &&
       Number.isFinite(row.revision) && row.revision>pending.transaction_revision;
}
export function completedPendingCancellation(turn, expected, receipt, callId) {
    return pendingCancellationReceipt(turn,expected,receipt,callId) && receipt.task_version===expected.task_version+1;
}
