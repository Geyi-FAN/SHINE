/** One bounded retry of a buffered, tool-free fixed readout; never robot POSTs. */
export async function synthesizeFixedReceiptWithRecovery(options, synthesize, control) {
    const started = Date.now(), windowMs = control.retryWindowMs ?? 5000;
    try {
        return await synthesize(options);
    }
    catch (error) {
        const code = error && typeof error === 'object' && 'code' in error ? error.code : undefined;
        const remaining = windowMs - (Date.now() - started);
        if (!options.fixedAnnouncement || code !== 'notification_speech_failed' ||
            options.signal?.aborted || !control.isCurrent() || remaining <= 0)
            throw error;
        // The synthesizer buffers and validates the entire result before returning.
        // Its failed attempt has not forwarded PCM; the original text stays intact.
        const signal = AbortSignal.any([...(options.signal ? [options.signal] : []), AbortSignal.timeout(Math.max(1, Math.floor(remaining)))]);
        try {
            control.onRetry?.({ attempt: 2, code, remainingMs: remaining });
        }
        catch { /* logging is not speech authority */ }
        return synthesize({ ...options, signal });
    }
}
