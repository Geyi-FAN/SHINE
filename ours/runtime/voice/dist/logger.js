/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
const LEVEL_ORDER = {
    debug: 10,
    info: 20,
    warn: 30,
    error: 40,
};
export class LiveLogger {
    minLevel;
    constructor(minLevel = process.env['QWEN_LIVE_HARNESS_LOG_LEVEL'] ?? 'info') {
        this.minLevel = minLevel;
    }
    get debugEnabled() {
        return this.minLevel === 'debug';
    }
    write(level, message) {
        if (LEVEL_ORDER[level] < (LEVEL_ORDER[this.minLevel] ?? 20))
            return;
        process.stderr.write(`[qwen-live-harness] ${new Date().toISOString()} ${level.toUpperCase()} ${message}\n`);
    }
    debug(message) {
        this.write('debug', message);
    }
    info(message) {
        this.write('info', message);
    }
    warn(message) {
        this.write('warn', message);
    }
    error(message) {
        this.write('error', message);
    }
}
