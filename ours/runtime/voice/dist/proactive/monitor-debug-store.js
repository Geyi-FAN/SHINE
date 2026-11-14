/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
import { randomUUID, createHash } from 'node:crypto';
import { lstat, mkdir, readFile, readdir, rename, rm, unlink, writeFile, } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, basename, resolve } from 'node:path';
export const MONITOR_DEBUG_ROOT = join(tmpdir(), 'qwen-live-harness-monitor-debug');
const FORMAT = 'qwen-live-harness-monitor-debug-v1';
const DIRECTORY = /^monitor-\d+-[a-f0-9-]{36}$/u;
const MAX_PENDING_BYTES = 32 * 1024 * 1024;
const MAX_PROVIDER_SESSION_ID_CHARS = 256;
async function privateDirectory(path) {
    const stat = await lstat(path);
    if (!stat.isDirectory() ||
        stat.isSymbolicLink() ||
        (stat.mode & 0o077) !== 0 ||
        (process.getuid && stat.uid !== process.getuid()))
        throw new Error('unsafe_directory');
}
async function json(path, value) {
    const temporary = `${path}.${randomUUID()}.tmp`;
    try {
        await writeFile(temporary, `${JSON.stringify(value, null, 2)}\n`, {
            flag: 'wx',
            mode: 0o600,
        });
        await rename(temporary, path);
    }
    finally {
        await unlink(temporary).catch(() => undefined);
    }
}
function wav(chunks) {
    const bytes = chunks.reduce((total, chunk) => total + chunk.length, 0);
    const header = Buffer.alloc(44);
    header.write('RIFF');
    header.writeUInt32LE(36 + bytes, 4);
    header.write('WAVEfmt ', 8);
    header.writeUInt32LE(16, 16);
    header.writeUInt16LE(1, 20);
    header.writeUInt16LE(1, 22);
    header.writeUInt32LE(16_000, 24);
    header.writeUInt32LE(32_000, 28);
    header.writeUInt16LE(2, 32);
    header.writeUInt16LE(16, 34);
    header.write('data', 36);
    header.writeUInt32LE(bytes, 40);
    return Buffer.concat([header, ...chunks]);
}
export class MonitorDebugStore {
    log;
    root;
    ready = false;
    lastCreatedAt = 0;
    tail = Promise.resolve();
    recorders = new Set();
    constructor(log, root = MONITOR_DEBUG_ROOT) {
        this.log = log;
        this.root = resolve(root);
    }
    async initialize() {
        try {
            await mkdir(this.root, { mode: 0o700 }).catch((error) => {
                if (error.code !== 'EEXIST')
                    throw error;
            });
            await privateDirectory(this.root);
            this.ready = true;
            await this.prune();
            this.emit('proactive.monitor_debug_ready', {
                directory: this.root,
                retainedMonitors: 10,
            });
            return true;
        }
        catch {
            this.ready = false;
            this.emit('proactive.monitor_debug_failed', {
                directory: this.root,
                reason: 'initialization_failed',
            });
            return false;
        }
    }
    create(info, apiKey) {
        if (!this.ready ||
            !info.modalities.some((modality) => modality === 'vision' || modality === 'audio'))
            return undefined;
        const createdAt = Math.max(Date.now(), this.lastCreatedAt + 1);
        this.lastCreatedAt = createdAt;
        const directory = join(this.root, `monitor-${createdAt}-${randomUUID()}`);
        const recorder = new MonitorDebugRecorder(directory, info, apiKey, (event, details) => this.emit(event, details), () => this.recorders.delete(recorder));
        this.recorders.add(recorder);
        const start = this.tail.then(async () => {
            await privateDirectory(this.root);
            await mkdir(directory, { mode: 0o700 });
            await json(join(directory, 'monitor.json'), {
                format: FORMAT,
                createdAt,
                ...recorder.clean(info),
            });
            await mkdir(join(directory, 'requests'), { mode: 0o700 });
            await this.prune();
        });
        this.tail = start.catch(() => undefined);
        recorder.prepare(start);
        return recorder;
    }
    async flush() {
        await this.tail;
        await Promise.all([...this.recorders].map((recorder) => recorder.flush()));
    }
    emit(event, details) {
        try {
            this.log(event, details);
        }
        catch {
            /* Debugging must not break a call. */
        }
    }
    async prune() {
        await privateDirectory(this.root);
        const owned = [];
        for (const entry of await readdir(this.root, { withFileTypes: true })) {
            if (!entry.isDirectory() || !DIRECTORY.test(entry.name))
                continue;
            const directory = join(this.root, entry.name);
            try {
                await privateDirectory(directory);
                const markerPath = join(directory, 'monitor.json');
                const stat = await lstat(markerPath);
                if (!stat.isFile() || stat.isSymbolicLink() || stat.size > 16_384)
                    continue;
                const marker = JSON.parse(await readFile(markerPath, 'utf8'));
                if (!marker ||
                    typeof marker !== 'object' ||
                    !('format' in marker) ||
                    marker.format !== FORMAT ||
                    !('createdAt' in marker) ||
                    typeof marker.createdAt !== 'number' ||
                    !Number.isSafeInteger(marker.createdAt) ||
                    !entry.name.startsWith(`monitor-${marker.createdAt}-`))
                    continue;
                owned.push({ directory, createdAt: marker.createdAt });
            }
            catch {
                /* Do not remove unrecognized temporary data. */
            }
        }
        owned.sort((a, b) => b.createdAt - a.createdAt || b.directory.localeCompare(a.directory));
        this.lastCreatedAt = Math.max(this.lastCreatedAt, owned[0]?.createdAt ?? 0);
        for (const entry of owned.slice(10)) {
            for (const recorder of this.recorders)
                if (recorder.directory === entry.directory)
                    recorder.evict();
            await privateDirectory(entry.directory);
            await rm(entry.directory, { recursive: true, force: true });
            this.emit('proactive.monitor_debug_pruned', {
                directory: entry.directory,
            });
        }
    }
}
export class MonitorDebugRecorder {
    directory;
    info;
    apiKey;
    log;
    release;
    tail = Promise.resolve();
    disabled = false;
    disabledReason;
    closed = false;
    pending = [];
    pendingBytes = 0;
    queuedBytes = 0;
    sequence = 0;
    transport = 0;
    providerSessionId;
    session = [];
    previousRequest;
    activeRequest;
    constructor(directory, info, apiKey, log, release) {
        this.directory = directory;
        this.info = info;
        this.apiKey = apiKey;
        this.log = log;
        this.release = release;
    }
    clean(value) {
        return JSON.parse(JSON.stringify(value, (key, item) => {
            if (/^(authorization|apiKey|headers)$/iu.test(key))
                return undefined;
            return typeof item === 'string' && this.apiKey
                ? item.split(this.apiKey).join('[redacted]')
                : item;
        }));
    }
    prepare(start) {
        this.tail = start
            .then(() => this.emit('proactive.monitor_debug_started', {}))
            .catch(() => this.fail('initialization_failed'));
    }
    async start() {
        await this.tail;
    }
    async flush() {
        await this.tail;
    }
    beginTransport(transport) {
        this.result({ status: 'recycled', incomplete: true });
        this.pending = [];
        this.pendingBytes = 0;
        this.session = [];
        this.previousRequest = undefined;
        this.activeRequest = undefined;
        this.providerSessionId = undefined;
        this.transport = transport;
    }
    setProviderSessionId(id) {
        if (this.closed ||
            this.disabled ||
            this.providerSessionId !== undefined ||
            typeof id !== 'string' ||
            id.length === 0 ||
            id.length > MAX_PROVIDER_SESSION_ID_CHARS ||
            !/^[A-Za-z0-9_.:/-]+$/u.test(id) ||
            (this.apiKey && id.includes(this.apiKey)))
            return;
        // A transport has one provider identity. Duplicate or conflicting updates
        // cannot rewrite an earlier request or enqueue an unbounded stream of writes.
        this.providerSessionId = id;
        const active = this.activeRequest;
        if (!active || active.completed)
            return;
        active.record['providerSessionId'] = id;
        this.enqueue(async () => {
            await privateDirectory(active.directory);
            await json(join(active.directory, 'request.json'), active.record);
        }, Buffer.byteLength(id));
    }
    sent(body, metadata) {
        if (this.closed)
            return;
        if (this.disabled) {
            if (body['type'] === 'input_audio_buffer.commit' ||
                body['type'] === 'conversation.item.create')
                this.emit('proactive.monitor_request_skipped', {
                    reason: this.disabledReason,
                    retained: false,
                });
            return;
        }
        try {
            this.recordSent(body, metadata);
        }
        catch {
            this.fail('recording_failed');
        }
    }
    recordSent(body, metadata) {
        const type = body['type'];
        const item = body['item'];
        if (type === 'conversation.item.create' &&
            item !== null &&
            typeof item === 'object' &&
            'content' in item &&
            Array.isArray(item.content) &&
            item.content.some((part) => part !== null &&
                typeof part === 'object' &&
                'type' in part &&
                part.type === 'input_audio')) {
            for (const part of item.content) {
                if (part['type'] !== 'input_audio' || typeof part['audio'] !== 'string')
                    continue;
                const bytes = Buffer.from(part['audio'], 'base64');
                if (this.pendingBytes + this.queuedBytes + bytes.length >
                    MAX_PENDING_BYTES) {
                    this.fail('pending_byte_limit');
                    return;
                }
                this.pending.push({
                    type: 'input_audio_buffer.append',
                    bytes,
                    sentAt: Date.now(),
                    ...(metadata?.origin ? { origin: metadata.origin } : {}),
                    ...(typeof body['event_id'] === 'string'
                        ? { eventId: body['event_id'] }
                        : {}),
                });
                this.pendingBytes += bytes.length;
            }
            this.commit(this.clean(body), true);
        }
        else if (type === 'session.update' ||
            type === 'conversation.item.create') {
            this.session.push(this.clean(body));
        }
        else if (type === 'input_audio_buffer.clear') {
            this.pending = [];
            this.pendingBytes = 0;
        }
        else if (type === 'input_image_buffer.append' ||
            type === 'input_audio_buffer.append') {
            const payload = type === 'input_image_buffer.append' ? body['image'] : body['audio'];
            if (typeof payload !== 'string')
                return;
            const bytes = Buffer.from(payload, 'base64');
            if (this.pendingBytes + this.queuedBytes + bytes.length >
                MAX_PENDING_BYTES) {
                this.fail('pending_byte_limit');
                return;
            }
            this.pending.push({
                type,
                bytes,
                sentAt: Date.now(),
                ...(type === 'input_audio_buffer.append' &&
                    (metadata?.origin === 'microphone' ||
                        metadata?.origin === 'protocol_silence')
                    ? { origin: metadata.origin }
                    : {}),
                ...(typeof body['event_id'] === 'string'
                    ? { eventId: body['event_id'] }
                    : {}),
            });
            this.pendingBytes += bytes.length;
        }
        else if (type === 'input_audio_buffer.commit') {
            this.commit(this.clean(body));
        }
        else if (type === 'response.create' && this.activeRequest) {
            const active = this.activeRequest;
            active.events.push(this.clean(body));
            this.enqueue(async () => {
                await privateDirectory(active.directory);
                await json(join(active.directory, 'request.json'), active.record);
            });
        }
    }
    result(value) {
        if (this.disabled || !this.activeRequest || this.activeRequest.completed)
            return;
        try {
            const active = this.activeRequest;
            active.completed = true;
            const safe = this.clean({
                ...value,
                // Snapshot correlation from the request, never from a later transport
                // or arbitrary result fields supplied by the caller.
                providerSessionId: active.record['providerSessionId'],
                ...(typeof value['text'] === 'string' && value['text'].length > 131_072
                    ? { text: value['text'].slice(0, 131_072), textTruncated: true }
                    : {}),
            });
            this.enqueue(async () => {
                await privateDirectory(active.directory);
                await json(join(active.directory, 'response.json'), safe);
                this.emit('proactive.monitor_request_result', {
                    requestDirectory: active.directory,
                });
            }, Buffer.byteLength(JSON.stringify(safe)));
        }
        catch {
            this.fail('recording_failed');
        }
    }
    close() {
        if (this.activeRequest && !this.activeRequest.completed)
            this.result({ status: 'closed', incomplete: true });
        this.closed = true;
        this.pending = [];
        this.pendingBytes = 0;
        void this.tail.then(this.release);
    }
    evict() {
        if (this.disabled)
            return;
        this.emit('proactive.monitor_debug_evicted', { retained: false });
        this.disabled = true;
        this.disabledReason = 'evicted';
        this.pending = [];
        this.pendingBytes = 0;
        void this.tail.then(this.release);
    }
    commit(event, audioItem = false) {
        const media = this.pending;
        const byteCost = this.pendingBytes;
        this.pending = [];
        this.pendingBytes = 0;
        const directory = join(this.directory, 'requests', String(++this.sequence).padStart(6, '0'));
        const events = [];
        const audio = [];
        const audioSummary = {
            totalBytes: 0,
            microphoneBytes: 0,
            protocolSilenceBytes: 0,
            unknownBytes: 0,
        };
        let audioOffset = 0;
        let imageIndex = 0;
        const images = [];
        for (const input of media) {
            if (input.type === 'input_image_buffer.append') {
                const path = `image-${String(++imageIndex).padStart(4, '0')}.jpg`;
                images.push({ path, bytes: input.bytes });
                events.push({
                    type: input.type,
                    image: path,
                    bytes: input.bytes.length,
                    sentAt: input.sentAt,
                    eventId: input.eventId,
                    sha256: createHash('sha256').update(input.bytes).digest('hex'),
                });
            }
            else {
                audio.push(input.bytes);
                audioSummary.totalBytes += input.bytes.length;
                if (input.origin === 'microphone')
                    audioSummary.microphoneBytes += input.bytes.length;
                else if (input.origin === 'protocol_silence')
                    audioSummary.protocolSilenceBytes += input.bytes.length;
                else
                    audioSummary.unknownBytes += input.bytes.length;
                events.push({
                    type: input.type,
                    audio: 'input.wav',
                    byteOffset: audioOffset,
                    bytes: input.bytes.length,
                    sentAt: input.sentAt,
                    eventId: input.eventId,
                    origin: input.origin ?? 'unknown',
                });
                audioOffset += input.bytes.length;
            }
        }
        if (audioItem) {
            const item = event['item'];
            let audioIndex = 0;
            const content = item['content'].map((part) => {
                if (part['type'] !== 'input_audio')
                    return part;
                const saved = events[audioIndex++];
                return {
                    ...part,
                    audio: saved['audio'],
                    byteOffset: saved['byteOffset'],
                    bytes: saved['bytes'],
                    origin: saved['origin'],
                };
            });
            events.splice(0, events.length, { ...event, item: { ...item, content } });
        }
        else {
            events.push(event);
        }
        const record = {
            format: FORMAT,
            recordingStatus: 'writing',
            monitor: this.clean(this.info),
            request: this.sequence,
            transportGeneration: this.transport,
            ...(this.providerSessionId
                ? { providerSessionId: this.providerSessionId }
                : {}),
            createdAt: Date.now(),
            previousRequest: this.previousRequest,
            session: this.session.map((item) => this.clean(item)),
            audioFormat: {
                encoding: 'pcm16le',
                sampleRate: 16000,
                channels: 1,
                byteOffsetsExcludeWavHeader: true,
            },
            audioSummary,
            events,
        };
        this.previousRequest = basename(directory);
        this.activeRequest = { directory, record, events, completed: false };
        this.enqueue(async () => {
            await mkdir(directory, { mode: 0o700 });
            await json(join(directory, 'request.json'), record);
            for (const image of images)
                await writeFile(join(directory, image.path), image.bytes, {
                    flag: 'wx',
                    mode: 0o600,
                });
            await writeFile(join(directory, 'input.wav'), wav(audio), {
                flag: 'wx',
                mode: 0o600,
            });
            record.recordingStatus = 'saved';
            await json(join(directory, 'request.json'), record);
            this.emit('proactive.monitor_request_saved', {
                requestDirectory: directory,
                request: record.request,
                imageFrames: images.length,
                audioBytes: audioOffset,
                audioSummary,
            });
        }, byteCost);
    }
    enqueue(operation, byteCost = 0) {
        if (this.disabled)
            return;
        if (this.pendingBytes + this.queuedBytes + byteCost > MAX_PENDING_BYTES) {
            this.fail('pending_byte_limit');
            return;
        }
        this.queuedBytes += byteCost;
        this.tail = this.tail
            .then(async () => {
            if (this.disabled)
                return;
            await privateDirectory(this.directory);
            await privateDirectory(join(this.directory, 'requests'));
            await operation();
        })
            .catch(() => this.fail('write_failed'))
            .finally(() => {
            this.queuedBytes -= byteCost;
        });
    }
    fail(reason) {
        if (this.disabled)
            return;
        this.disabled = true;
        this.disabledReason = reason;
        this.pending = [];
        this.pendingBytes = 0;
        this.emit('proactive.monitor_debug_failed', { reason, incomplete: true });
    }
    emit(event, details) {
        try {
            this.log(event, {
                directory: this.directory,
                taskId: this.info.taskId,
                ...details,
            });
        }
        catch {
            /* Non-fatal diagnostics. */
        }
    }
}
