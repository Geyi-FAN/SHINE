/** Only authoritative, known pre-execution validator rejections may reopen a turn. */
export function repairableServerValidation(receipt) {
    return !!receipt && receipt['status'] === 'rejected' && receipt['executed'] === false &&
        /^(?:clarification_missing_destination|deferred_pronoun_target_mismatch|stale_task_version):/.test(String(receipt['error'] || ''));
}
export function provenNoExecution(receipt) {
    return !!receipt && receipt['status'] !== 'unknown' &&
        (receipt['dispatch_attempted'] === false || repairableServerValidation(receipt));
}
