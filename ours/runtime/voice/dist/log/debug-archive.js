/**
 * @license
 * Copyright 2026 Qwen Team
 * SPDX-License-Identifier: Apache-2.0
 */
import { createHash, randomUUID } from 'node:crypto';
import { constants } from 'node:fs';
import { lstat, mkdir, open, readdir, rename, rm, unlink, } from 'node:fs/promises';
import { basename, join, resolve } from 'node:path';
const FORMAT = 'qwen-live-harness-debug-v1';
const RUN_NAME = /^run-(\d+)-([a-f0-9-]{36})$/u;
const MANIFEST_BUDGET = 8 * 1024;
const CONTROL_RESERVE = MANIFEST_BUDGET * 2;
const MAX_WARNINGS = 16;
const MAX_NODES = 100_000;
const MAX_DEPTH = 128;
const DEFAULT_MAX_BYTES = 512 * 1024 * 1024;
const DEFAULT_QUEUED_BYTES = 32 * 1024 * 1024;
const DEFAULT_RETAIN_RUNS = 10;
const READ_NOFOLLOW = constants.O_RDONLY | constants.O_NOFOLLOW;
const CREATE_NOFOLLOW = constants.O_CREAT |
    constants.O_EXCL |
    constants.O_WRONLY |
    constants.O_NOFOLLOW;
const CREDENTIAL_KEY = /(?:api[_-]?key$|token$|^(?:authorization|proxy[-_]?authorization|secret|client[-_]?secret|password|passwd|cookie|set[-_]?cookie|credentials?|private[-_]?key)$)/iu;
const JSON_CREDENTIAL = /("(?:[\w-]*api[_-]?key|[\w-]*token|authorization|proxy[-_]?authorization|secret|client[-_]?secret|password|passwd|cookie|set[-_]?cookie|private[-_]?key)"\s*:\s*)"(?:\\.|[^"\\])*"/giu;
let lastCreatedAt = 0;
class ArchiveIssue extends Error {
    code;
    constructor(code) {
        super(code);
        this.code = code;
    }
}
function object(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function digest(bytes) {
    return createHash('sha256').update(bytes).digest('hex');
}
function positive(value, fallback) {
    return value !== undefined && Number.isSafeInteger(value) && value > 0
        ? value
        : fallback;
}
async function privateDirectory(path, expected) {
    const stat = await lstat(path);
    if (!stat.isDirectory() ||
        stat.isSymbolicLink() ||
        (stat.mode & 0o077) !== 0 ||
        (process.getuid && stat.uid !== process.getuid()) ||
        (expected && (stat.dev !== expected.dev || stat.ino !== expected.ino)))
        throw new ArchiveIssue('unsafe_directory');
    return { dev: stat.dev, ino: stat.ino };
}
async function privateFile(path, expected) {
    const stat = await lstat(path);
    if (!stat.isFile() ||
        stat.isSymbolicLink() ||
        stat.nlink !== 1 ||
        (stat.mode & 0o077) !== 0 ||
        (process.getuid && stat.uid !== process.getuid()) ||
        (expected && (stat.dev !== expected.dev || stat.ino !== expected.ino)))
        throw new ArchiveIssue('unsafe_file');
    return { dev: stat.dev, ino: stat.ino };
}
/**
 * Construct only for debug runs. Recording never throws into the application.
 * All event/media writes share one FIFO; closing drains accepted writes even
 * after a capacity failure. No send success or missing media is fabricated.
 */
export class DebugArchive {
    options;
    path;
    root;
    runId = randomUUID();
    createdAt;
    monotonicStart = process.hrtime.bigint();
    secrets;
    maxBytes;
    maxQueuedBytes;
    retainRuns;
    warnings = [];
    warned = new Set();
    recorders = new Map();
    offsets = new Map();
    imageFiles = new Set();
    audioFiles = new Map();
    rootIdentity;
    runIdentity;
    mediaIdentity;
    eventIdentity;
    events;
    initialized = false;
    stopped = false;
    ioFailed = false;
    closing = false;
    incomplete = false;
    closedAt;
    tail;
    closingPromise;
    connectionCount = 0;
    runtimeSeq = 0;
    globalSeq = 0;
    writtenEvents = 0;
    droppedEvents = 0;
    dataBytes = 0;
    reservedBytes = 0;
    queuedBytes = 0;
    queuedHighWater = 0;
    lastManifestAt = 0;
    redactedValues = 0;
    invalidMediaValues = 0;
    constructor(options) {
        this.options = options;
        this.root = resolve(options.directory);
        this.createdAt = Math.max(Date.now(), lastCreatedAt + 1);
        lastCreatedAt = this.createdAt;
        this.path = join(this.root, `run-${this.createdAt}-${this.runId}`);
        this.secrets = [
            ...new Set((options.secrets ?? []).filter((secret) => typeof secret === 'string' && secret.length > 0)),
        ].sort((a, b) => b.length - a.length);
        this.maxBytes = positive(options.maxBytes, DEFAULT_MAX_BYTES);
        this.maxQueuedBytes = positive(options.maxQueuedBytes, DEFAULT_QUEUED_BYTES);
        this.retainRuns = positive(options.retainRuns, DEFAULT_RETAIN_RUNS);
        this.tail = this.initialize();
        if (options.metadata)
            this.recordRuntime('archive.run_metadata', options.metadata);
    }
    get isIncomplete() {
        return this.incomplete;
    }
    beginConnection(info) {
        const id = `conn-${String(++this.connectionCount).padStart(6, '0')}`;
        let sequence = 0;
        let closed = false;
        const kind = info.kind;
        const recorder = {
            id,
            path: this.path,
            record: (direction, event) => {
                if (closed)
                    return;
                this.capture(id, kind, ++sequence, direction, event);
            },
            close: (reason) => {
                if (closed)
                    return;
                closed = true;
                this.capture(id, kind, ++sequence, 'local', {
                    type: 'archive.connection_closed',
                    ...(reason !== undefined ? { reason } : {}),
                }, true);
                this.enqueueControl(async () => {
                    for (const [path, stream] of this.audioFiles) {
                        if (!basename(path).startsWith(`${id}-`))
                            continue;
                        await stream.handle.close();
                        this.audioFiles.delete(path);
                        this.offsets.delete(path);
                    }
                });
                this.recorders.delete(id);
            },
        };
        if (!['main', 'monitor', 'search', 'visual', 'notification'].includes(kind)) {
            closed = true;
            this.fail('invalid_connection_kind');
            return recorder;
        }
        if (!this.closing && !this.stopped && !this.ioFailed) {
            this.recorders.set(id, recorder);
            recorder.record('local', {
                ...info,
                type: 'archive.connection_registered',
            });
        }
        else
            closed = true;
        return recorder;
    }
    recordRuntime(type, payload) {
        this.capture('runtime', 'runtime', ++this.runtimeSeq, 'local', {
            type,
            payload,
        });
    }
    /** Flush everything accepted before this call, without waiting for future traffic. */
    async flush() {
        if (this.closingPromise) {
            await this.closingPromise;
            return;
        }
        await this.enqueueControl(async () => {
            await this.persistManifest();
            await this.events?.sync();
            for (const stream of this.audioFiles.values())
                await stream.handle.sync();
        });
    }
    close() {
        if (this.closingPromise)
            return this.closingPromise;
        this.closing = true;
        for (const recorder of [...this.recorders.values()])
            recorder.close('archive_closed');
        this.closingPromise = this.enqueueControl(async () => {
            this.closedAt = new Date().toISOString();
            await this.persistManifest();
            try {
                await this.events?.sync();
            }
            catch {
                this.fail('io_failure');
            }
            try {
                await this.events?.close();
            }
            catch {
                this.fail('io_failure');
            }
            this.events = undefined;
            for (const stream of this.audioFiles.values()) {
                try {
                    await stream.handle.close();
                }
                catch {
                    this.fail('io_failure');
                }
            }
            this.audioFiles.clear();
            this.offsets.clear();
            await this.persistManifest();
            await this.prune();
        });
        return this.closingPromise;
    }
    async initialize() {
        try {
            if (this.maxBytes < CONTROL_RESERVE * 2)
                throw new ArchiveIssue('invalid_limits');
            await mkdir(this.root, { recursive: true, mode: 0o700 });
            this.rootIdentity = await privateDirectory(this.root);
            await mkdir(this.path, { mode: 0o700 });
            this.runIdentity = await privateDirectory(this.path);
            await mkdir(join(this.path, 'media'), { mode: 0o700 });
            this.mediaIdentity = await privateDirectory(join(this.path, 'media'));
            this.events = await open(join(this.path, 'events.jsonl'), CREATE_NOFOLLOW | constants.O_APPEND, 0o600);
            this.eventIdentity = await privateFile(join(this.path, 'events.jsonl'));
            this.initialized = true;
            await this.persistManifest();
            await this.prune();
        }
        catch (error) {
            this.ioFailed = true;
            this.fail(error instanceof ArchiveIssue ? error.code : 'initialization_failed');
        }
    }
    capture(connectionId, kind, connectionSeq, direction, event, closingRecord = false) {
        if (this.closing && !closingRecord)
            return;
        const globalSeq = ++this.globalSeq;
        if (this.stopped || this.ioFailed) {
            this.droppedEvents++;
            return;
        }
        let cost = 0;
        try {
            if (!['out', 'in', 'local'].includes(direction))
                throw new ArchiveIssue('invalid_direction');
            const prepared = this.prepare(event, connectionId, direction);
            const wallTimeMs = Date.now();
            const envelope = {
                globalSeq,
                connectionSeq,
                wallTime: new Date(wallTimeMs).toISOString(),
                wallTimeMs,
                monotonicNs: (process.hrtime.bigint() - this.monotonicStart).toString(),
                direction,
                connectionId,
                kind,
                redacted: prepared.redacted,
                event: prepared.event,
            };
            const line = `${JSON.stringify(envelope)}\n`;
            cost = Buffer.byteLength(line) + prepared.mediaBytes;
            if (cost > this.maxQueuedBytes - this.queuedBytes)
                throw new ArchiveIssue('queue_limit');
            if (cost > this.maxBytes - CONTROL_RESERVE - this.reservedBytes)
                throw new ArchiveIssue('run_limit');
            this.reservedBytes += cost;
            this.queuedBytes += cost;
            this.queuedHighWater = Math.max(this.queuedHighWater, this.queuedBytes);
            for (const [path, offset] of prepared.offsets)
                this.offsets.set(path, offset);
            for (const path of prepared.images)
                this.imageFiles.add(path);
            this.tail = this.tail
                .then(async () => {
                try {
                    if (this.ioFailed || !this.initialized || !this.events) {
                        this.droppedEvents++;
                        return;
                    }
                    await this.checkDirectories(true);
                    for (const media of prepared.media)
                        await this.writeMedia(media);
                    await privateFile(join(this.path, 'events.jsonl'), this.eventIdentity);
                    await this.events.writeFile(line);
                    this.dataBytes += Buffer.byteLength(line);
                    this.writtenEvents++;
                    if (Date.now() - this.lastManifestAt >= 1000)
                        await this.persistManifest();
                }
                catch (error) {
                    this.droppedEvents++;
                    this.ioFailed = true;
                    this.fail(error instanceof ArchiveIssue ? error.code : 'io_failure', globalSeq, connectionId);
                    await this.persistManifest();
                }
                finally {
                    this.queuedBytes -= cost;
                }
            })
                .catch(() => {
                this.ioFailed = true;
                this.fail('io_failure', globalSeq, connectionId);
            });
        }
        catch (error) {
            this.droppedEvents++;
            this.fail(error instanceof ArchiveIssue ? error.code : 'serialization_failed', globalSeq, connectionId);
            void this.enqueueControl(() => this.persistManifest());
        }
    }
    cleanString(value) {
        let text = value;
        for (const secret of this.secrets)
            text = text.split(secret).join('[REDACTED]');
        return text
            .replace(JSON_CREDENTIAL, '$1"[REDACTED]"')
            .replace(/\bBearer\s+[-A-Za-z0-9._~+/]+=*/giu, 'Bearer [REDACTED]')
            .replace(/\b((?:https?|wss?):\/\/)[^/\s?#@]+@/giu, '$1[REDACTED]@')
            .replace(/([?&](?:[\w-]*api[_-]?key|[\w-]*token|secret|signature)=)[^&#\s]*/giu, '$1[REDACTED]');
    }
    prepare(event, connectionId, direction) {
        const media = [];
        const offsets = new Map();
        const images = new Set();
        const ancestors = new Set();
        let mediaBytes = 0, nodes = 0, stringBytes = 0;
        let redacted = false;
        const textValue = (value) => {
            const text = this.cleanString(value);
            if (text !== value) {
                redacted = true;
                this.redactedValues++;
            }
            stringBytes += Buffer.byteLength(text);
            if (stringBytes > this.maxQueuedBytes - this.queuedBytes - mediaBytes)
                throw new ArchiveIssue('queue_limit');
            return text;
        };
        const externalize = (value, hint) => {
            const estimated = typeof value === 'string'
                ? Math.floor(value.length / 4) * 3
                : value.byteLength;
            if (estimated > this.maxQueuedBytes - this.queuedBytes - mediaBytes)
                throw new ArchiveIssue('queue_limit');
            if (typeof value === 'string' &&
                !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/u.test(value)) {
                this.invalidMediaValues++;
                return textValue(value);
            }
            const bytes = typeof value === 'string'
                ? Buffer.from(value, 'base64')
                : Buffer.from(value);
            if (typeof value === 'string' && bytes.toString('base64') !== value) {
                this.invalidMediaValues++;
                return textValue(value);
            }
            const sha256 = digest(bytes);
            const encoding = typeof value === 'string' ? 'base64' : 'uint8array';
            let path;
            let append;
            if (hint.kind === 'image') {
                const extension = bytes[0] === 0xff && bytes[1] === 0xd8
                    ? 'jpg'
                    : bytes
                        .subarray(0, 8)
                        .equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
                        ? 'png'
                        : 'bin';
                path = `media/${sha256}.${extension}`;
                append = false;
            }
            else {
                path = `media/${connectionId}-${hint.kind === 'audio' ? (hint.lane ?? (direction === 'in' ? 'output' : 'input')) : 'binary'}.${hint.kind === 'audio' ? 'pcm' : 'bin'}`;
                append = true;
            }
            const byteOffset = append
                ? (offsets.get(path) ?? this.offsets.get(path) ?? 0)
                : 0;
            const ref = {
                $media: path,
                byteOffset,
                bytes: bytes.length,
                sha256,
                encoding,
                kind: hint.kind,
            };
            const duplicate = !append && (this.imageFiles.has(path) || images.has(path));
            media.push({ ref, ...(duplicate ? {} : { data: bytes }), append });
            if (!duplicate)
                mediaBytes += bytes.length;
            if (append)
                offsets.set(path, byteOffset + bytes.length);
            else
                images.add(path);
            return ref;
        };
        const walk = (value, depth, hint, schemaProperties = false) => {
            if (++nodes > MAX_NODES || depth > MAX_DEPTH)
                throw new ArchiveIssue('event_complexity_limit');
            if (hint && (typeof value === 'string' || value instanceof Uint8Array))
                return externalize(value, hint);
            if (value instanceof Uint8Array)
                return externalize(value, { kind: 'binary' });
            if (typeof value === 'string') {
                return textValue(value);
            }
            if (value === null ||
                typeof value === 'boolean' ||
                typeof value === 'number')
                return value;
            if (value === undefined)
                return undefined;
            if (typeof value !== 'object')
                throw new ArchiveIssue('non_json_value');
            if (ancestors.has(value))
                throw new ArchiveIssue('circular_event');
            ancestors.add(value);
            try {
                if (Array.isArray(value))
                    return value.map((item) => walk(item, depth + 1));
                const input = value instanceof Error
                    ? {
                        name: value.name,
                        message: value.message,
                        stack: value.stack,
                        ...Object.fromEntries(Object.entries(value)),
                    }
                    : value;
                const output = Object.create(null);
                const type = typeof input['type'] === 'string' ? input['type'] : '';
                for (const [key, child] of Object.entries(input)) {
                    const schemaField = schemaProperties &&
                        object(child) &&
                        (typeof child['type'] === 'string' ||
                            '$ref' in child ||
                            'anyOf' in child ||
                            'oneOf' in child);
                    if (CREDENTIAL_KEY.test(key) && !schemaField) {
                        output[key] = '[REDACTED]';
                        if (child !== '[REDACTED]') {
                            redacted = true;
                            this.redactedValues++;
                        }
                        continue;
                    }
                    if (/^(?:headers|requestHeaders|responseHeaders)$/iu.test(key) &&
                        object(child) &&
                        !schemaField) {
                        output[key] = Object.fromEntries(Object.keys(child).map((name) => [
                            this.cleanString(name),
                            '[REDACTED]',
                        ]));
                        if (Object.values(child).some((value) => value !== '[REDACTED]')) {
                            redacted = true;
                            this.redactedValues++;
                        }
                        continue;
                    }
                    let mediaHint;
                    if (key === 'jpegBase64' ||
                        (key === 'image' &&
                            ['screen', 'camera'].includes(String(input['source'])) &&
                            Number.isSafeInteger(input['width']) &&
                            Number(input['width']) > 0 &&
                            Number.isSafeInteger(input['height']) &&
                            Number(input['height']) > 0) ||
                        (['input_image_buffer.append', 'input_image', 'image'].includes(type) &&
                            ['image', 'data'].includes(key)) ||
                        (key === 'data' &&
                            typeof input['mimeType'] === 'string' &&
                            input['mimeType'].startsWith('image/')))
                        mediaHint = { kind: 'image' };
                    if ((type === 'input_audio_buffer.append' && key === 'audio') ||
                        (type === 'input_audio' && ['audio', 'data'].includes(key)) ||
                        key === 'pcm16')
                        mediaHint = { kind: 'audio', lane: 'input' };
                    if (['response.audio.delta', 'response.output_audio.delta'].includes(type) &&
                        key === 'delta')
                        mediaHint = { kind: 'audio', lane: 'output' };
                    if (type === 'audio' && ['audio', 'data'].includes(key))
                        mediaHint = { kind: 'audio' };
                    output[textValue(key)] = walk(child, depth + 1, mediaHint, key === 'properties');
                }
                return output;
            }
            finally {
                ancestors.delete(value);
            }
        };
        const clean = walk(event, 0);
        return { event: clean, media, mediaBytes, offsets, images, redacted };
    }
    async checkDirectories(media) {
        if (!this.initialized)
            throw new ArchiveIssue('initialization_failed');
        await privateDirectory(this.root, this.rootIdentity);
        await privateDirectory(this.path, this.runIdentity);
        if (media)
            await privateDirectory(join(this.path, 'media'), this.mediaIdentity);
    }
    async writeMedia(write) {
        const path = join(this.path, write.ref.$media);
        if (write.append) {
            let stream = this.audioFiles.get(write.ref.$media);
            if (!stream) {
                const handle = await open(path, CREATE_NOFOLLOW | constants.O_APPEND, 0o600);
                stream = { handle, identity: await privateFile(path) };
                this.audioFiles.set(write.ref.$media, stream);
            }
            await privateFile(path, stream.identity);
            if ((await stream.handle.stat()).size !== write.ref.byteOffset ||
                !write.data)
                throw new ArchiveIssue('media_integrity_failed');
            await stream.handle.writeFile(write.data);
            this.dataBytes += write.data.length;
            return;
        }
        if (write.data) {
            let handle;
            try {
                handle = await open(path, CREATE_NOFOLLOW, 0o600);
                await handle.writeFile(write.data);
                this.dataBytes += write.data.length;
            }
            catch (error) {
                if (!object(error) || error['code'] !== 'EEXIST')
                    throw error;
            }
            finally {
                await handle?.close();
            }
        }
        await privateFile(path);
        const handle = await open(path, READ_NOFOLLOW);
        try {
            if ((await handle.stat()).size !== write.ref.bytes)
                throw new ArchiveIssue('media_integrity_failed');
            const hash = createHash('sha256');
            const chunk = Buffer.alloc(Math.min(64 * 1024, Math.max(1, write.ref.bytes)));
            for (let at = 0; at < write.ref.bytes;) {
                const { bytesRead } = await handle.read(chunk, 0, Math.min(chunk.length, write.ref.bytes - at), at);
                if (!bytesRead)
                    throw new ArchiveIssue('media_integrity_failed');
                hash.update(chunk.subarray(0, bytesRead));
                at += bytesRead;
            }
            if (hash.digest('hex') !== write.ref.sha256)
                throw new ArchiveIssue('media_integrity_failed');
        }
        finally {
            await handle.close();
        }
    }
    fail(code, globalSeq, connectionId) {
        this.incomplete = true;
        this.stopped = true;
        if (this.warned.has(code))
            return;
        this.warned.add(code);
        const warning = Object.freeze({
            code,
            message: `Debug archive is incomplete (${code}); application execution is unaffected.`,
            at: new Date().toISOString(),
            path: this.cleanString(this.path),
            ...(globalSeq !== undefined ? { globalSeq } : {}),
            ...(connectionId ? { connectionId } : {}),
        });
        if (this.warnings.length < MAX_WARNINGS)
            this.warnings.push(warning);
        try {
            this.options.onWarning?.(warning);
        }
        catch {
            /* never break the application */
        }
    }
    enqueueControl(work) {
        const pending = this.tail.then(work).catch((error) => {
            this.fail(error instanceof ArchiveIssue ? error.code : 'io_failure');
        });
        this.tail = pending;
        return pending;
    }
    async persistManifest() {
        if (!this.initialized)
            return;
        let temporary;
        try {
            await this.checkDirectories(false);
            const manifest = {
                format: FORMAT,
                owner: 'qwen-live-harness',
                runId: this.runId,
                pid: process.pid,
                createdAt: this.createdAt,
                startedAt: new Date(this.createdAt).toISOString(),
                ...(this.options.sessionId
                    ? {
                        sessionId: this.cleanString(this.options.sessionId).slice(0, 512),
                    }
                    : {}),
                status: this.incomplete
                    ? 'incomplete'
                    : this.closedAt
                        ? 'closed'
                        : 'recording',
                incomplete: this.incomplete,
                redacted: this.redactedValues > 0,
                redaction: {
                    redactedValues: this.redactedValues,
                    knownSecretsCount: this.secrets.length,
                    media: 'not-inspected',
                },
                ...(this.closedAt ? { closedAt: this.closedAt } : {}),
                warnings: this.warnings,
                files: { events: 'events.jsonl', media: 'media' },
                connections: {
                    count: this.connectionCount,
                    index: 'events.jsonl',
                    registrationType: 'archive.connection_registered',
                },
                counters: {
                    recordedEvents: this.globalSeq,
                    writtenEvents: this.writtenEvents,
                    droppedEvents: this.droppedEvents,
                    lastGlobalSeq: this.globalSeq,
                    dataBytes: this.dataBytes,
                    reservedBytes: this.reservedBytes,
                    queuedBytes: this.queuedBytes,
                    queuedHighWater: this.queuedHighWater,
                    invalidMediaValues: this.invalidMediaValues,
                },
                limits: {
                    maxBytes: this.maxBytes,
                    maxQueuedBytes: this.maxQueuedBytes,
                    retainRuns: this.retainRuns,
                },
                integrity: 'Verify every referenced byte range with its sha256 before replay; send attempts are not proof of delivery.',
            };
            const json = `${JSON.stringify(manifest, null, 2)}\n`;
            if (Buffer.byteLength(json) > MANIFEST_BUDGET)
                throw new ArchiveIssue('manifest_limit');
            const destination = join(this.path, 'manifest.json');
            try {
                await privateFile(destination);
            }
            catch (error) {
                if (!object(error) || error['code'] !== 'ENOENT')
                    throw error;
            }
            const candidate = join(this.path, `manifest-${randomUUID()}.tmp`);
            const handle = await open(candidate, CREATE_NOFOLLOW, 0o600);
            temporary = candidate;
            try {
                await handle.writeFile(json);
            }
            finally {
                await handle.close();
            }
            await rename(candidate, destination);
            temporary = undefined;
            this.lastManifestAt = Date.now();
        }
        catch (error) {
            this.fail(error instanceof ArchiveIssue ? error.code : 'manifest_write_failed');
        }
        finally {
            if (temporary)
                await unlink(temporary).catch(() => undefined);
        }
    }
    async prune() {
        if (!this.rootIdentity)
            return;
        try {
            await privateDirectory(this.root, this.rootIdentity);
            const finished = [];
            for (const entry of await readdir(this.root, { withFileTypes: true })) {
                const name = RUN_NAME.exec(entry.name);
                if (!name || !entry.isDirectory())
                    continue;
                const path = join(this.root, entry.name);
                try {
                    await privateDirectory(path);
                    const marker = join(path, 'manifest.json');
                    await privateFile(marker);
                    const handle = await open(marker, READ_NOFOLLOW);
                    let value;
                    try {
                        if ((await handle.stat()).size > MANIFEST_BUDGET)
                            continue;
                        value = JSON.parse(await handle.readFile('utf8'));
                    }
                    finally {
                        await handle.close();
                    }
                    if (!object(value) ||
                        value['format'] !== FORMAT ||
                        value['owner'] !== 'qwen-live-harness' ||
                        value['runId'] !== name[2] ||
                        value['createdAt'] !== Number(name[1]))
                        continue;
                    let alive = true;
                    const pid = value['pid'];
                    if (typeof pid !== 'number' || !Number.isSafeInteger(pid) || pid <= 0)
                        continue;
                    try {
                        process.kill(pid, 0);
                    }
                    catch (error) {
                        alive = !object(error) || error['code'] !== 'ESRCH';
                    }
                    if (!value['closedAt'] && alive)
                        continue;
                    finished.push({ path, createdAt: Number(value['createdAt']) });
                }
                catch {
                    /* unrecognized or unsafe data is never deleted */
                }
            }
            finished.sort((left, right) => right.createdAt - left.createdAt ||
                right.path.localeCompare(left.path));
            for (const entry of finished.slice(this.retainRuns)) {
                if (entry.path === this.path)
                    continue;
                await privateDirectory(this.root, this.rootIdentity);
                await privateDirectory(entry.path);
                await rm(entry.path, { recursive: true, force: true });
            }
        }
        catch {
            /* retention failure must not interfere with capture or the app */
        }
    }
}
