export function rememberStopLease(context, event, identity, now = Date.now()) {
    const lease = { itemId: event.itemId, audioMs: event.audioStartMs, version: context.taskInputVersion,
        generation: context.realtimeGeneration, startedAt: now, identity };
    context.independentStopLeases ??= [];
    context.independentStopLeases.push(lease);
    context.independentStopLeases = context.independentStopLeases.slice(-16);
    return lease;
}
/** Only a provider-confirmed continuation of the exact prior primary input
 * may retain its audio boundary across reconnect. This carries no new robot
 * authority: the independent lease keeps its ORIGINAL task/version identity.
 */
export function recoveryStopContinuation(context,event) {
    const previous=context.fastStopOnsets?.at(-1),guard=context.robotSpeechGuard;
    if (!event.recoveredFromInputId || !event.itemId || !previous ||
        previous.itemId!==event.recoveredFromInputId || guard?.inputId!==event.recoveredFromInputId ||
        previous.generation>=context.realtimeGeneration || !Number.isFinite(previous.audioMs)) return;
    return {kind:'same_input_transport_recovery_v1',fromItemId:previous.itemId,toItemId:event.itemId,
        audioMs:previous.recoveryContinuation?.audioMs??previous.audioMs};
}
export function selectStopLease(context, event, now = Date.now(), claimed) {
    const lease = context.independentStopLeases?.at(-1), end = event.audioEndMs, audioNow = (context.fastStopAudioBytes ?? 0) / 32;
    if (!lease || (lease.used && lease !== claimed) || lease.itemId !== event.itemId || end === undefined || !Number.isFinite(end) ||
        end > audioNow + 500 || audioNow - end > 3000 || now - event.receivedAt > 3000 || now - lease.startedAt > 12000)
        return;
    const latest = context.fastStopOnsets?.at(-1);
    const continuation=latest?.recoveryContinuation;
    const primaryAudioMs=continuation?.kind==='same_input_transport_recovery_v1' &&
        continuation.toItemId===latest.itemId && latest.generation===context.realtimeGeneration &&
        Number.isFinite(continuation.audioMs) && continuation.audioMs>=0 && continuation.audioMs<=latest.audioMs
        ?continuation.audioMs:latest?.audioMs;
    // A newer primary utterance invalidates even a still-open independent ASR item.
    if (latest && primaryAudioMs > end + 250)
        return;
    if (context.taskInputVersion !== lease.version && (!latest || latest.version !== context.taskInputVersion ||
        primaryAudioMs < lease.audioMs - 750 || primaryAudioMs > end + 250))
        return;
    return { lease, version: context.taskInputVersion };
}

/** Choose the real onset whose first three seconds are available NOW.
 * A later primary-VAD fragment must not hide an earlier independent onset.
 * This grants only permission to LISTEN; selectStopLease/commitFastStop still
 * enforce episode/task/version authority before any pause can be submitted.
 */
export function selectPrefixStopLease(context, now = Date.now()) {
    const primary = context.fastStopOnsets?.at(-1);
    const independent = context.independentStopLeases?.at(-1);
    const total = context.speechAudioTotal ?? 0;
    return [independent, primary].filter(lease => {
        if (!lease || lease.used || lease.prefixProbeStarted || !Number.isFinite(lease.audioMs) ||
            !Number.isFinite(lease.startedAt) || now - lease.startedAt > 12000)
            return false;
        if (lease === primary && (lease.version !== context.taskInputVersion ||
            lease.generation !== context.realtimeGeneration))
            return false;
        const onset = Math.max(0, Math.round(lease.audioMs * 32));
        const start = Math.max(0, context.stopPrerollFloorBytes ?? 0, onset - 24000);
        const end = onset + 96000;
        return end - start >= 96000 && end - start <= 120000 && total >= end && total <= end + 32000;
    }).sort((a, b) => a.audioMs - b.audioMs)[0];
}
