/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
/**
 * Derive the WebSocket origin for a DashScope-style HTTP base URL: swap the
 * scheme and strip a trailing `/compatible-mode/v1` or `/v1` path prefix.
 */
export function deriveWebSocketBase(baseUrl) {
    const url = new URL(baseUrl);
    const wsScheme = url.protocol === 'https:' ? 'wss:' : 'ws:';
    let prefix = url.pathname.replace(/\/+$/, '');
    if (prefix.endsWith('/compatible-mode/v1')) {
        prefix = prefix.slice(0, -'/compatible-mode/v1'.length);
    }
    else if (prefix.endsWith('/v1')) {
        prefix = prefix.slice(0, -'/v1'.length);
    }
    return `${wsScheme}//${url.host}${prefix}`;
}
