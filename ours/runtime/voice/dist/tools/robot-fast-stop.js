import { controlIntent } from './robot-control-semantics.js';
/** Narrow, final-ASR stop path. Never generates goals, retries POSTs, or resumes. */
import WebSocket from 'ws';
import { dispatchRobotTool } from './robot.js';
import { deriveQwenOmniRealtimeUrl } from '../realtime/realtime-session.js';
export function independentStop(text) { return controlIntent(text) === 'pause'; }
export function stopCommandPresent(text) {
    if (controlIntent(text) === 'pause') return true;
    // A final ASR segment may merge an unconditional stop with its next task.
    // This ONLY authorizes the stop receipt. The original full utterance still
    // goes to the Agent, whose controlIntent must remain non-pause for revision.
    return /^(?:please\s+)?(?:stop|pause|halt)(?:\s+(?:now|immediately|first))?[.!。！,，;:]+\s*(?:(?:please|first|then|now)\b[\s,]*)*(?:put|place|return|open|close|turn|push|move|take|don['’]?t|do\s+not)\b/i.test(String(text).trim());
}
/** A segment after a negation/question is not an independent imperative. */
export function stopSegmentAllowed(text, prefix, recentPrefix = '') {
    if (!stopCommandPresent(text))
        return false;
    if (/\b(?:don['’]?t|do not|never|if|unless|said|say|means?)\b|不要|别停|如果|是否/i.test(recentPrefix))
        return false;
    return (!prefix.trim() ||
        /^(?:(?:hold on|please|hey|ok|okay|请你?|麻烦你?|嗯|好)[.!。！,，\s]*)+$/i.test(prefix.trim()));
}
/** Re-listen to an ambiguous SHORT first segment; never reinterpret its text. */
export function canVerifyShortStop(event, prefix, recent) {
    const duration = (event.audioEndMs ?? NaN) - (event.audioStartMs ?? NaN);
    return !!event.text.trim() && !independentStop(event.text) &&
        event.text.length <= 70 && event.text.trim().split(/\s+/).length <= 4 &&
        Number.isFinite(duration) && duration >= 150 && duration <= 1600 &&
        !/[?？“”"「」]|\b(?:don't|do not|never|if|unless|after|said|say)\b|不要|别停|如果/i.test(event.text) &&
        stopSegmentAllowed('Stop.', prefix, recent);
}
/** Fresh manual ASR, audio only. No user-reference text, scene, tools or plan. */
export function transcribeShortStopAudio(options) {
    return new Promise((resolve, reject) => {
        const budget = Math.min(2500, Math.max(100, options.timeoutMs ?? 2500));
        if (options.signal.aborted || options.pcm16.length < 3200 ||
            options.pcm16.length > 32000 * 3.75) {
            reject(Error('stop_verify_invalid_or_cancelled'));
            return;
        }
        let done = false, text = '';
        const socket = new WebSocket(deriveQwenOmniRealtimeUrl(options.endpoint, 'qwen3-asr-flash-realtime'), { headers: { Authorization: 'Bearer ' + (options.apiKey ?? '') },
            handshakeTimeout: Math.min(1200, budget) });
        const finish = (error) => {
            if (done)
                return;
            done = true;
            clearTimeout(timer);
            options.signal.removeEventListener('abort', abort);
            try {
                socket.close();
            }
            catch { /* Owned socket only. */ }
            if (error)
                reject(error);
            else if (text.trim())
                resolve(text.trim());
            else
                reject(Error('stop_verify_empty'));
        };
        const abort = () => finish(Error('stop_verify_cancelled'));
        const timer = setTimeout(() => finish(Error('stop_verify_timeout')), budget);
        options.signal.addEventListener('abort', abort, { once: true });
        socket.on('error', () => finish(Error('stop_verify_transport')));
        socket.on('close', () => finish(text ? undefined : Error('stop_verify_closed')));
        socket.on('message', raw => {
            if (done)
                return;
            try {
                const event = JSON.parse(raw.toString());
                if (event['type'] === 'session.created')
                    socket.send(JSON.stringify({
                        type: 'session.update', event_id: 'short-stop-config',
                        session: { input_audio_format: 'pcm', sample_rate: 16000, turn_detection: null },
                    }));
                if (event['type'] === 'session.updated') {
                    for (let i = 0; i < options.pcm16.length; i += 16000)
                        socket.send(JSON.stringify({
                            type: 'input_audio_buffer.append', event_id: 'short-stop-audio-' + i,
                            audio: options.pcm16.subarray(i, i + 16000).toString('base64'),
                        }));
                    socket.send(JSON.stringify({ type: 'input_audio_buffer.commit', event_id: 'short-stop-commit' }));
                    socket.send(JSON.stringify({ type: 'session.finish', event_id: 'short-stop-finish' }));
                }
                if (event['type'] === 'conversation.item.input_audio_transcription.completed') {
                    text = String(event['transcript'] ?? '');
                    if (text.length > 120)
                        finish(Error('stop_verify_too_long'));
                }
                if (event['type'] === 'session.finished')
                    finish();
                if (event['type'] === 'error')
                    finish(Error('stop_verify_provider_error'));
            }
            catch {
                finish(Error('stop_verify_invalid_event'));
            }
        });
    });
}
/** A second ASR stream segments short commands; the main speech stream is unchanged. */
export class StopASR {
    socket;
    ready = false;
    closed = false;
    pending = [];
    starts = new Map();
    ends = new Map();
    previous = '';
    previousAt = 0;
    seen = new Set();
    constructor(options) {
        try {
            const url = deriveQwenOmniRealtimeUrl(options.endpoint, 'qwen3-asr-flash-realtime');
            const ws = (this.socket = new WebSocket(url, {
                headers: { Authorization: `Bearer ${options.apiKey ?? ''}` },
                handshakeTimeout: 12000,
            }));
            ws.on('message', (raw) => {
                try {
                    const m = JSON.parse(raw.toString()), kind = String(m['type']);
                    if (kind === 'session.created')
                        ws.send(JSON.stringify({
                            event_id: 'stop-config',
                            type: 'session.update',
                            session: {
                                input_audio_format: 'pcm',
                                sample_rate: 16000,
                                turn_detection: {
                                    type: 'server_vad',
                                    threshold: 0.2,
                                    silence_duration_ms: 200,
                                },
                            },
                        }));
                    if (kind === 'session.updated') {
                        this.ready = true;
                        options.onEvent({
                            type: 'robot.fast_stop_asr',
                            phase: 'ready',
                            model: 'qwen3-asr-flash-realtime',
                            silence_ms: 200,
                        });
                        for (const b of this.pending)
                            this.push(b);
                        this.pending = [];
                    }
                    const id = String(m['item_id'] ?? '');
                    if (kind === 'input_audio_buffer.speech_started') {
                        this.starts.set(id, Number(m['audio_start_ms']));
                        options.onStart?.({itemId:id,audioStartMs:Number(m['audio_start_ms'])});
                    }
                    if (kind === 'input_audio_buffer.speech_stopped') {
                        this.ends.set(id, Number(m['audio_end_ms']));
                    }
                    if (kind === 'conversation.item.input_audio_transcription.completed' &&
                        id &&
                        !this.seen.has(id)) {
                        this.seen.add(id);
                        const text = String(m['transcript'] ?? '');
                        const event = {
                            itemId: id,
                            text,
                            audioStartMs: this.starts.get(id),
                            audioEndMs: this.ends.get(id),
                            receivedAt: Date.now(),
                            precedingText: this.previous,
                            precedingReceivedAt: this.previousAt,
                        };
                        this.previous = text;
                        this.previousAt = event.receivedAt;
                        options.onEvent({
                            type: 'robot.fast_stop_asr',
                            phase: 'final',
                            ...event,
                        });
                        options.onFinal(event);
                        if (this.seen.size > 256) {
                            this.seen.clear();
                            this.starts.clear();
                            this.ends.clear();
                        }
                    }
                    if (kind === 'error')
                        options.onEvent({
                            type: 'robot.fast_stop_asr',
                            phase: 'error',
                            code: m['error']?.['code'] ??
                                'provider_error',
                        });
                }
                catch {
                    options.onEvent({
                        type: 'robot.fast_stop_asr',
                        phase: 'error',
                        code: 'invalid_event',
                    });
                }
            });
            ws.on('error', () => options.onEvent({
                type: 'robot.fast_stop_asr',
                phase: 'error',
                code: 'transport_error',
            }));
            ws.on('close', () => {
                this.ready = false;
                options.onEvent({ type: 'robot.fast_stop_asr', phase: 'closed' });
            });
        }
        catch {
            options.onEvent({
                type: 'robot.fast_stop_asr',
                phase: 'error',
                code: 'configuration_error',
            });
        }
    }
    push(pcm) {
        if (this.closed)
            return;
        if (!this.ready) {
            if (this.pending.reduce((n, b) => n + b.length, 0) + pcm.length <=
                32000 * 15)
                this.pending.push(Buffer.from(pcm));
            return;
        }
        if (this.socket?.readyState === WebSocket.OPEN &&
            this.socket.bufferedAmount < 1_000_000)
            this.socket.send(JSON.stringify({
                event_id: 'stop-audio',
                type: 'input_audio_buffer.append',
                audio: pcm.toString('base64'),
            }));
    }
    close() {
        this.closed = true;
        this.pending = [];
        this.socket?.close();
    }
}
export async function commitFastStop(identity, inputId, text, current) {
    const rejected = (code) => ({
        ok: false,
        receipt: JSON.stringify({
            status: 'rejected',
            code,
            executed: false,
            dispatch_attempted: false,
        }),
    });
    if (!stopCommandPresent(text) || !current())
        return rejected('not_current_independent_stop');
    if (!['running', 'verifying', 'paused', 'budget_exhausted'].includes(String(identity['state'])))
        return rejected('no_active_task_at_stop_onset');
    // Final ASR + a current input lease authorize this ordinary version-fenced
    // tool. The immutable control journal already records its actual speech.
    // /interaction is telemetry, not authority; waiting for a second durable
    // write here delayed Stop by three seconds under rendering/IO contention.
    // Do not enqueue that old prefix later: it could overwrite a newer intake.
    return await dispatchRobotTool('robot_pause', JSON.stringify({
        episode_id: identity['episode_id'],
        expected_task_version: identity['task_version'],
    }), inputId + ':pause', text, inputId);
}
/** End timestamps remain useful when server VAD includes preceding silence. */
export function matchStopOnset(onsets, event, nowAudioMs) {
    const end = event.audioEndMs;
    if (end !== undefined && Number.isFinite(end)) {
        if (end > nowAudioMs + 500 || nowAudioMs - end > 3000)
            return undefined;
        return onsets.filter((o) => o.audioMs <= end + 250).at(-1);
    }
    return onsets
        .filter((o) => event.audioStartMs !== undefined &&
        o.audioMs <= event.audioStartMs + 750)
        .at(-1);
}
