/**
 * @license
 * Copyright 2026 Alibaba Group Holding Limited
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 * Adapted to TypeScript from qwen-omni-realtime-agent; modified for Qwen Live Harness.
 */
import { DEFAULT_MEMORY_CONFIG } from './config.js';
export function formatTimestamp(moment) {
    const part = (value) => String(value).padStart(2, '0');
    return `${moment.getFullYear()}-${part(moment.getMonth() + 1)}-${part(moment.getDate())} ${part(moment.getHours())}:${part(moment.getMinutes())}:${part(moment.getSeconds())}`;
}
export class DialogueRecorder {
    config;
    nextTurnIdx;
    pending;
    tail = [];
    constructor(config = DEFAULT_MEMORY_CONFIG.segment, firstTurnIdx = 0) {
        this.config = config;
        this.nextTurnIdx = firstTurnIdx;
    }
    get pendingTurn() {
        return this.pending ? { ...this.pending } : undefined;
    }
    get tailTurns() {
        return this.tail.map((turn) => ({ ...turn }));
    }
    onUserText(text, moment = new Date()) {
        if (typeof text !== 'string' || !text.trim())
            return {};
        const result = this.closePending();
        this.pending = {
            turnIdx: this.nextTurnIdx++,
            userText: text.trim(),
            userTs: formatTimestamp(moment),
            userEpoch: Math.floor(moment.getTime() / 1000),
            asstText: '',
            asstTs: '',
            asstEpoch: 0,
            interrupted: false,
            provisionalAnswer: false,
        };
        return result;
    }
    onAssistantText(text, options = {}) {
        const source = options.source ?? 'normal';
        if (typeof text !== 'string' ||
            !text.trim() ||
            !this.pending ||
            !['normal', 'filler'].includes(source))
            return {};
        const authoritative = source === 'normal';
        if (!authoritative && this.pending.asstText)
            return {};
        const moment = options.moment ?? new Date();
        Object.assign(this.pending, {
            asstText: text.trim(),
            asstTs: formatTimestamp(moment),
            asstEpoch: Math.floor(moment.getTime() / 1000),
            interrupted: options.interrupted === true,
            provisionalAnswer: !authoritative,
        });
        return authoritative ? this.closePending() : {};
    }
    flush() {
        return this.closePending();
    }
    cutTail(reason = 'session_end') {
        if (!this.tail.length)
            return undefined;
        const segment = { turns: this.tail, cutReason: reason };
        this.tail = [];
        return segment;
    }
    closePending() {
        const turn = this.pending;
        this.pending = undefined;
        if (!turn)
            return {};
        const reason = this.cutReasonFor(turn);
        const segment = reason ? this.cutTail(reason) : undefined;
        this.tail.push(turn);
        return { turn, ...(segment ? { segment } : {}) };
    }
    cutReasonFor(incoming) {
        if (!this.tail.length)
            return undefined;
        if (this.tail.length >= this.config.maxTurns)
            return 'max_turns';
        if (this.tail.reduce((total, turn) => total + [...turn.userText].length + [...turn.asstText].length, 0) >= this.config.maxChars)
            return 'max_chars';
        const previous = this.tail[this.tail.length - 1];
        if (this.config.silenceGapSec > 0 &&
            this.tail.length >= this.config.minTurnsBeforeGapCut &&
            previous &&
            incoming.userEpoch - (previous.asstEpoch || previous.userEpoch) >=
                this.config.silenceGapSec)
            return 'silence_gap';
        return undefined;
    }
}
