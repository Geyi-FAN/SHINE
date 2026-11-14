/** Refresh metadata once after a proven unexecuted waiting replacement rejection.
 * Task wording remains the model's. The gateway retains all atomic CAS checks.
 */
import { createHash } from 'node:crypto';

const MAX_ENTRIES = 128;
const MAX_INPUT_AGE_SECONDS = 20;
const retryFlights = new Map();
const object = (value) => !!value && typeof value === 'object' && !Array.isArray(value);
const integer = (value) => Number.isSafeInteger(value) && value >= 0;
const parse = (result) => {
    try { const value = JSON.parse(result.receipt); return object(value) ? value : undefined; }
    catch { return undefined; }
};
const current = (check) => {
    try { return typeof check === 'function' && check() === true; }
    catch { return false; }
};

export function provenDeferredVersionRejection(name, args, result, inputId) {
    const receipt = parse(result);
    return name === 'robot_replace_deferred' && result.ok === false &&
        receipt?.status === 'rejected' && receipt.executed === false &&
        typeof receipt.error === 'string' &&
        /^(?:stale_task_version|stale_transaction_revision)(?::|$)/.test(receipt.error) &&
        receipt.deferred_update?.blocked === true &&
        receipt.deferred_update.deferred_id === args.deferred_id &&
        typeof inputId === 'string' && inputId.length > 0 &&
        typeof args.episode_id === 'string' && args.episode_id.length > 0 &&
        typeof args.deferred_id === 'string' && args.deferred_id.length > 0 &&
        typeof args.instruction === 'string' && args.instruction.trim().length > 0 &&
        integer(args.expected_task_version);
}

export function refreshedDeferredArguments(args, status, text, inputId, nowSeconds) {
    if (!object(status) || status.episode_id !== args.episode_id ||
        !integer(status.task_version) || !integer(status.task_intent_revision) ||
        typeof status.task_id !== 'string' || !status.task_id ||
        !['running', 'verifying', 'completed'].includes(status.state))
        return { reason: 'episode_task_or_state_changed' };
    const slot = status.deferred_task;
    const row = status.dialogue_transactions?.active?.find((r) => r.transaction_id === args.deferred_id);
    if (!object(slot) || !object(row) || slot.deferred_id !== args.deferred_id ||
        slot.episode_id !== status.episode_id || slot.predecessor_task_id !== status.task_id ||
        slot.transaction_id !== args.deferred_id || slot.state !== 'update_pending' ||
        row.kind !== 'deferred' || row.status !== 'queued' || row.consumed_by_task_id !== null ||
        row.episode_id !== status.episode_id || row.bound_task_id !== status.task_id ||
        row.predecessor_task_id !== status.task_id || row.task_intent_revision !== status.task_intent_revision ||
        !integer(row.observed_execution_version) ||
        !integer(row.revision) || row.revision < 1 || row.revision !== slot.transaction_revision)
        return { reason: 'waiting_or_transaction_changed' };
    if (slot.dispatch_blocked_by_input !== inputId || row.dispatch_blocked_by_input !== inputId ||
        slot.update_utterance !== text || typeof text !== 'string' || !text.trim())
        return { reason: 'input_fence_or_utterance_changed' };
    if (!Number.isFinite(slot.expires_at) || slot.expires_at <= nowSeconds ||
        !Number.isFinite(row.expires_at) || row.expires_at <= nowSeconds ||
        !Number.isFinite(slot.update_requested_at) || slot.update_requested_at > nowSeconds + 1 ||
        nowSeconds - slot.update_requested_at > MAX_INPUT_AGE_SECONDS)
        return { reason: 'input_or_transaction_expired' };
    const candidate = slot.candidate_contract;
    if (!object(candidate) || candidate.episode_id !== args.episode_id ||
        !integer(candidate.task_version) || candidate.task_version < 1)
        return { reason: 'original_waiting_binding_not_proven' };
    if (args.transaction_id !== undefined && args.transaction_id !== row.transaction_id)
        return { reason: 'original_transaction_id_mismatch' };
    const oldRevision = args.expected_transaction_revision;
    if (oldRevision !== undefined && (!integer(oldRevision) ||
        row.revision < oldRevision || row.revision > oldRevision + 1))
        return { reason: 'intervening_transaction_revision' };
    const sameVersion = status.task_version === args.expected_task_version;
    const completedOnce = status.task_version === candidate.task_version + 1 &&
        status.state === 'completed' && status.completion === 'verified';
    if (status.task_version !== candidate.task_version && !completedOnce)
        return { reason: 'unproven_execution_version_change' };
    const validVersions = new Set([candidate.task_version, status.task_version]);
    if (!validVersions.has(args.expected_task_version) ||
        !validVersions.has(row.observed_execution_version))
        return { reason: 'original_or_observed_execution_binding_changed' };
    if (sameVersion && oldRevision === row.revision)
        return { reason: 'no_authoritative_identity_change' };
    return {
        args: { ...args, expected_task_version: status.task_version,
            transaction_id: row.transaction_id, expected_transaction_revision: row.revision },
        evidence: { predecessor_task_id: status.task_id,
            original_waiting_task_version: candidate.task_version,
            old_task_version: args.expected_task_version, new_task_version: status.task_version,
            old_transaction_revision: oldRevision ?? null, new_transaction_revision: row.revision,
            deferred_id: slot.deferred_id, input_id: inputId, same_episode: true,
            same_predecessor: true, completion_transition: completedOnce },
    };
}

const withAudit = (result, audit) => {
    const receipt = parse(result);
    return receipt ? { ...result, receipt: JSON.stringify({ ...receipt, deferred_version_retry: audit }) } : result;
};

export async function retryDeferredVersion(options) {
    const { name, args, result, inputId, text, requestId, isCurrent, readStatus, retry, onEvent } = options;
    if (!provenDeferredVersionRejection(name, args, result, inputId))
        return result;
    const emit = (phase, extra = {}) => {
        try { onEvent?.({ phase, request_id: requestId, input_id: inputId,
            deferred_id: args.deferred_id, ...extra }); } catch { /* logging is not authority */ }
    };
    const original = parse(result);
    const audit = { initial_rejection: original, metadata_refreshes: 0, retry_attempts: 0,
        original_request_id: requestId, bounded_max_retry_attempts: 1 };
    const stop = (reason) => { emit('not_retried', { reason }); return withAudit(result, { ...audit, reason }); };
    if (!current(isCurrent))
        return stop('current_input_lease_unavailable');
    const key = JSON.stringify([args.episode_id, args.deferred_id, inputId]);
    const signature = JSON.stringify([name, args, text]);
    const previous = retryFlights.get(key);
    if (previous) {
        if (previous.signature !== signature)
            return stop('candidate_changed_within_input');
        emit('deduplicated_same_input');
        return previous.promise;
    }
    if (retryFlights.size >= MAX_ENTRIES) {
        for (const [k, entry] of retryFlights) {
            if (entry.settled) retryFlights.delete(k);
            if (retryFlights.size < MAX_ENTRIES) break;
        }
    }
    if (retryFlights.size >= MAX_ENTRIES)
        return stop('refresh_capacity_unavailable');
    const entry = { signature, settled: false, promise: undefined };
    // Install before executing callbacks, including synchronous mocked transports.
    entry.promise = Promise.resolve().then(async () => {
        emit('refresh_started', { initial_rejection: original });
        let refreshed;
        try { refreshed = await readStatus(requestId + ':refresh-deferred-state'); }
        catch { return stop('status_read_failed'); }
        audit.metadata_refreshes = 1;
        if (!current(isCurrent)) return stop('input_superseded_during_refresh');
        if (!refreshed.ok) return stop('status_read_not_authoritative');
        const decision = refreshedDeferredArguments(args, parse(refreshed), text, inputId, Date.now() / 1000);
        if (!decision.args) return stop(decision.reason);
        if (!current(isCurrent)) return stop('input_superseded_before_retry');
        audit.evidence = decision.evidence;
        audit.retry_request_id = 'deferred-refresh:' + createHash('sha256').update(requestId).digest('hex');
        audit.retry_attempts = 1;
        emit('retry_submitted', { ...decision.evidence, retry_request_id: audit.retry_request_id });
        let repeated;
        try { repeated = await retry(decision.args, audit.retry_request_id); }
        catch {
            repeated = { ok: false, receipt: JSON.stringify({ status: 'unknown',
                code: 'robot_deferred_retry_result_unknown',
                note: 'No further automatic retry; the retried operation outcome is uncertain.' }) };
        }
        audit.outcome = parse(repeated)?.status ?? 'unknown';
        emit('retry_finished', { outcome: audit.outcome, ok: repeated.ok,
            retry_request_id: audit.retry_request_id });
        return withAudit(repeated, audit);
    }).finally(() => { entry.settled = true; });
    retryFlights.set(key, entry);
    return entry.promise;
}
