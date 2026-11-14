/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
import { redactPermissionText, stripControlSequences, } from '../adaptor/adaptor-utils.js';
function scopedRequestId(backend, requestId) {
    return JSON.stringify([backend.adaptor, backend.id, requestId]);
}
function offersOnce(options) {
    return options.some((option) => option.kind === 'proceed' && option.escalation !== 'always');
}
/** Global Live policy only. Every allow uses a non-persistent backend vote. */
export class PermissionBroker {
    options;
    pending = new Map();
    pendingByRequestId = new Map();
    autoAnswerAllowed = new Set();
    autoAnswering = new Set();
    deliveries = new Map();
    seq = 0;
    now;
    constructor(options) {
        this.options = options;
        this.now = options.now ?? Date.now;
    }
    mode() {
        try {
            return this.options.getPermissionMode?.() === 'allow-all'
                ? 'allow-all'
                : 'ask';
        }
        catch {
            return 'ask';
        }
    }
    async onRequest(fields) {
        const key = scopedRequestId(fields.backend, fields.requestId);
        const existingHandle = this.pendingByRequestId.get(key);
        const existing = existingHandle
            ? this.pending.get(existingHandle)
            : undefined;
        if (existing)
            return { pending: existing, autoAnswered: false, alreadyPending: true };
        const pending = {
            requestHandle: `req_${++this.seq}`,
            requestId: fields.requestId,
            backend: fields.backend,
            sessionHandle: fields.sessionHandle,
            ...(fields.jobRef !== undefined ? { jobRef: fields.jobRef } : {}),
            title: stripControlSequences(redactPermissionText(fields.title)).slice(0, 8192),
            options: fields.options,
            ...(fields.details ? { details: fields.details } : {}),
            permissionMode: this.mode(),
            createdAt: this.now(),
        };
        this.pending.set(pending.requestHandle, pending);
        this.pendingByRequestId.set(key, pending.requestHandle);
        if (fields.allowAutoAnswer !== false)
            this.autoAnswerAllowed.add(pending.requestHandle);
        this.log('permission.request', {
            requestHandle: pending.requestHandle,
            requestId: pending.requestId,
            session: pending.sessionHandle,
            title: pending.title,
            permissionMode: pending.permissionMode,
            ...(pending.details?.toolCallId
                ? { toolCallId: pending.details.toolCallId }
                : {}),
        });
        const autoAnswered = await this.answerAutomatically(pending);
        return { pending, autoAnswered, alreadyPending: false };
    }
    /** Called explicitly after a successful user setting change, not by mode reads. */
    async approvePendingAutomatically() {
        for (const pending of [...this.pending.values()]) {
            if (this.mode() !== 'allow-all')
                break;
            if (this.pending.get(pending.requestHandle) !== pending)
                continue;
            await this.answerAutomatically(pending);
        }
    }
    async answerAutomatically(pending) {
        if (this.mode() !== 'allow-all' ||
            !this.autoAnswerAllowed.has(pending.requestHandle) ||
            this.pending.get(pending.requestHandle) !== pending)
            return false;
        const existing = this.deliveries.get(pending.requestHandle);
        if (existing) {
            try {
                return (await existing) !== 'skipped';
            }
            catch {
                return false;
            }
        }
        this.autoAnswering.add(pending.requestHandle);
        try {
            return (await this.deliver(pending, 'allow', true)) !== 'skipped';
        }
        catch {
            this.log('permission.decision', {
                requestHandle: pending.requestHandle,
                requestId: pending.requestId,
                auto: true,
                outcome: 'delivery_failed',
                permissionMode: 'allow-all',
                error: 'Permission delivery failed; the request still needs attention.',
            });
            return false;
        }
        finally {
            this.autoAnswering.delete(pending.requestHandle);
        }
    }
    /** Legacy allow_always is explicitly downgraded; it never changes configuration. */
    async respond(requestHandle, decision, note) {
        const handle = requestHandle.trim();
        const pending = this.pending.get(handle);
        if (!pending)
            return 'not_found';
        const existing = this.deliveries.get(handle);
        if (existing) {
            const outcome = await existing;
            if (outcome === 'skipped')
                return this.respond(handle, decision, note);
            // Another explicit/automatic vote owned the fence. Do not claim that this
            // caller's potentially different choice was sent to the backend.
            return 'already_resolved';
        }
        const outcome = await this.deliver(pending, decision, false, note);
        return outcome === 'skipped' ? 'not_found' : outcome;
    }
    onResolved(backend, requestId) {
        const key = scopedRequestId(backend, requestId);
        const handle = this.pendingByRequestId.get(key);
        if (!handle)
            return;
        const pending = this.pending.get(handle);
        this.pendingByRequestId.delete(key);
        this.pending.delete(handle);
        this.autoAnswerAllowed.delete(handle);
        return pending;
    }
    resolveHandle(requestHandle) {
        return this.pending.get(requestHandle.trim());
    }
    get pendingCount() {
        return this.pending.size;
    }
    get pendingRequests() {
        return [...this.pending.values()];
    }
    get pendingUserRequests() {
        return [...this.pending.values()].filter((pending) => !this.autoAnswering.has(pending.requestHandle));
    }
    pendingForSession(sessionHandle) {
        return [...this.pendingUserRequests]
            .reverse()
            .find((pending) => pending.sessionHandle === sessionHandle.trim());
    }
    pendingForJob(backend, jobRef) {
        return [...this.pendingUserRequests]
            .reverse()
            .find((pending) => pending.backend.adaptor === backend.adaptor &&
            pending.backend.id === backend.id &&
            pending.jobRef === jobRef.trim());
    }
    clearSession(sessionHandle) {
        for (const pending of this.pending.values()) {
            if (pending.sessionHandle !== sessionHandle.trim())
                continue;
            this.onResolved(pending.backend, pending.requestId);
        }
    }
    deliver(pending, requestedDecision, auto, note) {
        const existing = this.deliveries.get(pending.requestHandle);
        if (existing)
            return existing;
        // Install the fence before invoking an adaptor that can synchronously emit
        // resolution events or trigger another settings/manual decision callback.
        const operation = Promise.resolve()
            .then(async () => {
            if (this.pending.get(pending.requestHandle) !== pending)
                return 'already_resolved';
            const permissionMode = this.mode();
            if (auto &&
                (permissionMode !== 'allow-all' ||
                    !this.autoAnswerAllowed.has(pending.requestHandle)))
                return 'skipped';
            const decision = requestedDecision === 'deny'
                ? 'deny'
                : offersOnce(pending.options)
                    ? 'allow'
                    : 'cancel';
            const plannedReason = decision === 'cancel'
                ? 'The backend has no identifiable one-time approval option; the request was cancelled instead of granting persistent permission.'
                : requestedDecision === 'allow_always'
                    ? 'Per-operation persistent grants are no longer supported. Only this operation was approved; change the global permission mode in Settings for future requests.'
                    : undefined;
            const outcome = await this.options
                .adaptorFor(pending.backend)
                .respondPermission(pending.backend, pending.requestId, decision);
            // A synchronous resolution may already have removed this request. Do
            // not clear a newer request that reused the backend's opaque id.
            if (this.pending.get(pending.requestHandle) === pending)
                this.onResolved(pending.backend, pending.requestId);
            const reason = outcome === 'already_resolved'
                ? 'The request was already resolved; no new permission or persistent grant was issued.'
                : plannedReason;
            this.log('permission.decision', {
                requestHandle: pending.requestHandle,
                requestId: pending.requestId,
                requestedDecision,
                decision,
                auto,
                outcome,
                permissionMode,
                ...(reason ? { reason } : {}),
                ...(note ? { note: redactPermissionText(note).slice(0, 4096) } : {}),
            });
            try {
                this.options.onDecision?.({
                    pending,
                    requestedDecision,
                    decision,
                    auto,
                    outcome,
                    permissionMode,
                    ...(reason ? { reason } : {}),
                });
            }
            catch {
                /* Observability cannot retry an already-delivered vote. */
            }
            return outcome;
        })
            .finally(() => {
            if (this.deliveries.get(pending.requestHandle) === operation)
                this.deliveries.delete(pending.requestHandle);
        });
        this.deliveries.set(pending.requestHandle, operation);
        return operation;
    }
    log(type, payload) {
        try {
            this.options.log?.(type, payload);
        }
        catch {
            /* Logging never changes approval behavior. */
        }
    }
}
