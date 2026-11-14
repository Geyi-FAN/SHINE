/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
const MAX_PARSED_FRAME_BYTES = 2 * 1024 * 1024;
function safeEndpoint(value) {
    if (typeof value !== 'string')
        return undefined;
    try {
        const url = new URL(value);
        return `${url.protocol}//${url.host}${url.pathname}`;
    }
    catch {
        return undefined;
    }
}
function failureMetadata(error) {
    if (!error || typeof error !== 'object')
        return {};
    const value = error;
    // Error messages can contain request URLs or credentials. Protocol error
    // events remain available separately; transport errors retain safe codes.
    const token = (candidate) => typeof candidate === 'string' && /^[A-Za-z0-9_]{1,64}$/u.test(candidate)
        ? candidate
        : undefined;
    try {
        return { name: token(value['name']), code: token(value['code']) };
    }
    catch {
        return {};
    }
}
function frameBytes(value) {
    if (typeof value === 'string')
        return {
            data: Buffer.from(value),
            totalBytes: Buffer.byteLength(value),
        };
    if (value instanceof ArrayBuffer)
        return {
            data: Buffer.from(value),
            totalBytes: value.byteLength,
        };
    if (ArrayBuffer.isView(value))
        return {
            data: Buffer.from(value.buffer, value.byteOffset, value.byteLength),
            totalBytes: value.byteLength,
        };
    if (Array.isArray(value) && value.every((part) => Buffer.isBuffer(part))) {
        // ws also accepts fragmented buffers. The transport's maxPayload and the
        // archive's queue/disk budgets bound retention; do not silently truncate
        // an observed message and label the resulting recording replayable.
        const totalBytes = value.reduce((bytes, part) => bytes + part.byteLength, 0);
        return {
            data: Buffer.concat(value, totalBytes),
            totalBytes,
        };
    }
    return undefined;
}
function wireEvent(value, binary) {
    const frame = frameBytes(value);
    if (!frame)
        return { raw: { kind: 'unrecognized' } };
    if (!binary && frame.totalBytes <= MAX_PARSED_FRAME_BYTES) {
        try {
            return JSON.parse(frame.data.toString('utf8'));
        }
        catch {
            // Keep the malformed wire data so parser failures can be reproduced.
        }
    }
    return {
        raw: {
            kind: binary ? 'binary' : 'text',
            encoding: binary ? 'base64' : 'utf8',
            data: frame.data.toString(binary ? 'base64' : 'utf8'),
            bytes: frame.totalBytes,
        },
    };
}
/**
 * Observe the transport before any provider parser, without changing its wire
 * messages. A successful send means local acceptance, not a provider ACK.
 * When debug is disabled even object identity and listeners remain unchanged.
 */
export function createDebugSocket(create, options) {
    let archive;
    if (options.debugArchive) {
        try {
            archive = options.debugArchive.beginConnection({
                ...options.info,
                endpoint: safeEndpoint(options.info.endpoint) ?? '[invalid endpoint]',
            });
        }
        catch {
            // Diagnostics must never prevent a call from opening.
        }
    }
    if (!archive)
        return create();
    const record = (direction, event) => {
        try {
            archive?.record(direction, event);
        }
        catch {
            // Disk pressure or an observer failure does not change protocol state.
        }
    };
    const closeArchive = (reason) => {
        try {
            archive?.close(reason);
        }
        catch {
            // The actual transport teardown retains ownership of completion.
        }
    };
    record('local', { type: 'transport.construct' });
    let socket;
    try {
        socket = create();
    }
    catch (error) {
        record('local', {
            type: 'transport.construct_failed',
            ...failureMetadata(error),
        });
        closeArchive('construction_failed');
        throw error;
    }
    // Install observers first. Even malformed, duplicate, stale or terminal
    // provider events are retained before the caller decides to discard them.
    socket.on('message', (value, binary) => {
        record('in', {
            type: 'wire.receive',
            binary: binary === true,
            event: wireEvent(value, binary === true),
        });
    });
    socket.on('open', () => record('local', { type: 'transport.open' }));
    socket.on('error', (error) => record('local', { type: 'transport.error', ...failureMetadata(error) }));
    socket.on('unexpected-response', (_request, response) => {
        const status = response && typeof response === 'object'
            ? response['statusCode']
            : undefined;
        record('local', {
            type: 'transport.unexpected_response',
            ...(typeof status === 'number' && Number.isInteger(status)
                ? { status }
                : {}),
        });
    });
    socket.on('close', (code, reason) => {
        record('local', {
            type: 'transport.close',
            ...(typeof code === 'number' && Number.isInteger(code) ? { code } : {}),
            ...(typeof reason === 'string' || Buffer.isBuffer(reason)
                ? { reason: String(reason).slice(0, 1024) }
                : {}),
        });
        closeArchive('transport_closed');
    });
    let sequence = 0;
    const methods = new Map();
    return new Proxy(socket, {
        get(target, property) {
            const value = Reflect.get(target, property, target);
            if (typeof value !== 'function')
                return value;
            if (methods.has(property))
                return methods.get(property);
            let method;
            if (property === 'send') {
                method = (...args) => {
                    const attemptId = `send-${++sequence}`;
                    record('out', {
                        type: 'wire.send',
                        attemptId,
                        event: wireEvent(args[0], typeof args[0] !== 'string'),
                    });
                    try {
                        const result = Reflect.apply(value, target, args);
                        record('local', {
                            type: 'wire.send_result',
                            attemptId,
                            status: 'sent',
                        });
                        return result;
                    }
                    catch (error) {
                        record('local', {
                            type: 'wire.send_result',
                            attemptId,
                            status: 'failed_or_uncertain',
                            ...failureMetadata(error),
                        });
                        throw error;
                    }
                };
            }
            else if (property === 'close' || property === 'terminate') {
                method = (...args) => {
                    record('local', { type: `transport.${String(property)}_requested` });
                    try {
                        return Reflect.apply(value, target, args);
                    }
                    catch (error) {
                        record('local', {
                            type: `transport.${String(property)}_failed`,
                            ...failureMetadata(error),
                        });
                        throw error;
                    }
                };
            }
            else {
                method = value.bind(target);
            }
            methods.set(property, method);
            return method;
        },
        set(target, property, value) {
            return Reflect.set(target, property, value, target);
        },
    });
}
