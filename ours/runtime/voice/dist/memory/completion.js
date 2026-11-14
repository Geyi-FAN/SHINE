/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
export function resolveCompletionConnection(shared, settings) {
    if (!settings.baseUrl)
        return shared;
    const apiKey = settings.apiKeyEnv
        ? process.env[settings.apiKeyEnv]
        : shared.apiKey;
    return { baseUrl: settings.baseUrl, ...(apiKey ? { apiKey } : {}) };
}
export class MemoryCompletionError extends Error {
    status;
    constructor(status) {
        super(status
            ? `Memory completion HTTP ${status}`
            : 'Invalid memory completion response');
        this.status = status;
        this.name = 'MemoryCompletionError';
    }
}
export function completionFailureDetails(error) {
    return {
        kind: error instanceof Error ? error.name : 'unknown',
        ...(error instanceof MemoryCompletionError && error.status !== undefined
            ? { status: error.status }
            : {}),
    };
}
export async function complete(connection, body, timeoutMs, signal, fetcher = fetch) {
    const timeout = AbortSignal.timeout(timeoutMs);
    const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
    let response;
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            response = await fetcher(`${connection.baseUrl.replace(/\/$/u, '')}/chat/completions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(connection.apiKey
                        ? { Authorization: `Bearer ${connection.apiKey}` }
                        : {}),
                },
                body: JSON.stringify(body),
                signal: combined,
            });
        }
        catch (error) {
            if (attempt === 0 && !combined.aborted)
                continue;
            throw error;
        }
        if (!response.ok) {
            await response.body?.cancel();
            if (attempt === 0 &&
                (response.status === 429 || response.status >= 500) &&
                !combined.aborted)
                continue;
            throw new MemoryCompletionError(response.status);
        }
        break;
    }
    if (!response?.body)
        throw new MemoryCompletionError();
    const reader = response.body.getReader();
    const chunks = [];
    let size = 0;
    for (;;) {
        const item = await reader.read();
        if (item.done)
            break;
        size += item.value.byteLength;
        if (size > 1_048_576) {
            await reader.cancel();
            throw new MemoryCompletionError();
        }
        chunks.push(item.value);
    }
    const decoded = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!isRecord(decoded) || !Array.isArray(decoded['choices']))
        throw new MemoryCompletionError();
    const first = decoded['choices'][0];
    const message = isRecord(first) ? first['message'] : undefined;
    return isRecord(message) && typeof message['content'] === 'string'
        ? message['content']
        : '';
}
export function isRecord(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}
