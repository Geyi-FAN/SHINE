/** Retry only complete-buffer TTS generation; never replay an audible output. */
export async function boundedNotificationSpeech(once, options, deps = {}) {
    const start = Date.now();
    const totalMs = 12000;
    let lastError;
    for (let attempt = 0; attempt < 2; attempt++) {
        if (options.signal?.aborted) {
            const error = new Error('notification_speech_aborted');
            error.code = 'notification_speech_aborted';
            throw error;
        }
        const remaining = totalMs - (Date.now() - start);
        if (remaining <= 0) throw lastError;
        try {
            return await once(options, { ...deps, timeoutMs: Math.min(6000, remaining) });
        } catch (error) {
            lastError = error;
            const retryable=error?.code==='notification_speech_timeout'||(error?.code==='notification_speech_readout_changed'&&typeof options.fixedAnnouncement==='string'&&!!options.fixedAnnouncement);
            if (attempt || !retryable || options.signal?.aborted)
                throw error;
            const event = { type: 'robot.notification_speech_retry', attempt: 2,
                purpose: options.purpose, cause:error.code, firstAttemptMs: Date.now() - start,
                noAudioForwarded: true, identicalText: true };
            if (deps.onRetry) deps.onRetry(event);
            else process.stderr.write(JSON.stringify(event) + '\n');
        }
    }
    throw lastError;
}
