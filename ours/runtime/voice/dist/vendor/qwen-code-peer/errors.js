/**
 * @license
 * Copyright 2026 Qwen Team
 * SPDX-License-Identifier: Apache-2.0
 */
export class PeerEndpointError extends Error {
    code;
    constructor(code, message) {
        super(message);
        this.code = code;
        this.name = 'PeerEndpointError';
    }
}
export function describeError(error) {
    return error instanceof Error ? error.message : String(error);
}
