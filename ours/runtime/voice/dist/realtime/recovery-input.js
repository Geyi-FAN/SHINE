/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
const BYTES_PER_MS = 32;
export const MAX_RECOVERY_AUDIO_BYTES = 60_000 * BYTES_PER_MS;
/** Bounded real-microphone history, never protocol-silence replay. */
export class RecoveryInputBuffer {
    preserveUnfinished;
    constructor(preserveUnfinished = false) {
        this.preserveUnfinished = preserveUnfinished;
    }
    prefix = [];
    missingPrefixTranscript = false;
    position = 0;
    bytes = 0;
    frames = [];
    latest;
    audio(audio) {
        this.frames.push({ start: this.position, audio: Uint8Array.from(audio) });
        this.position += audio.byteLength;
        this.bytes += audio.byteLength;
        while (this.bytes > MAX_RECOVERY_AUDIO_BYTES) {
            this.bytes -= this.frames.shift().audio.byteLength;
        }
    }
    protocolSilence(bytes) {
        this.position += bytes;
    }
    speech(itemId, startMs) {
        const reported = startMs === undefined
            ? undefined
            : Math.round((startMs * BYTES_PER_MS) / 2) * 2;
        let start = reported !== undefined && reported >= 0 && reported <= this.position
            ? reported
            : undefined;
        if (this.preserveUnfinished && this.latest && !this.latest.completed && !this.latest.dispatched) {
            if (this.latest.text?.trim())
                this.prefix.push(this.latest.text);
            else
                this.missingPrefixTranscript = true;
            if (this.latest.start !== undefined)
                start = this.latest.start;
        }
        else {
            this.prefix = [];
            this.missingPrefixTranscript = false;
        }
        this.latest = { itemId, start };
    }
    committed(itemId) {
        if (this.latest?.itemId !== itemId)
            this.latest = { itemId };
    }
    transcript(itemId, text) {
        if (this.latest?.itemId === itemId)
            this.latest.text = text;
    }
    stopped(itemId) {
        if (this.latest && (itemId === undefined || this.latest.itemId === itemId))
            this.latest.stopped = true;
    }
    completed(itemId) {
        if (this.latest?.itemId === itemId)
            this.latest.completed = true;
    }
    dispatched(itemId) {
        if (this.latest &&
            (itemId === undefined || this.latest.itemId === itemId)) {
            this.latest.dispatched = true;
        }
    }
    restored(itemId, text) {
        this.prefix = [];
        this.missingPrefixTranscript = false;
        this.latest = { itemId, text, start: this.position };
    }
    snapshot() {
        const input = this.latest;
        if (!input || input.completed)
            return { kind: 'none', reason: 'completed' };
        if (input.dispatched)
            return { kind: 'none', reason: 'tool_dispatched' };
        if (this.prefix.length > 12 || this.prefix.join(' ').length > 4000)
            return { kind: 'none', reason: 'unavailable' };
        if (input.text?.trim() && !this.missingPrefixTranscript)
            return { kind: 'text', itemId: input.itemId, text: [...this.prefix, input.text].join(' ') };
        const first = this.frames[0];
        if (!first || input.start === undefined || input.start < first.start)
            return { kind: 'none', reason: 'unavailable' };
        const start = input.start;
        const audio = Buffer.concat(this.frames.flatMap((frame) => {
            const offset = Math.max(0, start - frame.start);
            return offset < frame.audio.byteLength
                ? [frame.audio.subarray(offset)]
                : [];
        }));
        return audio.byteLength > 0
            ? { kind: 'audio', itemId: input.itemId, audio, stopped: input.stopped === true }
            : { kind: 'none', reason: 'unavailable' };
    }
    clear() {
        this.frames = [];
        this.bytes = 0;
    }
}
