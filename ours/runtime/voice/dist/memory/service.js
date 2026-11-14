/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
import { randomUUID } from 'node:crypto';
import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, renameSync, unlinkSync, writeFileSync, } from 'node:fs';
import { join } from 'node:path';
import { resolveMemoryConfig, } from './config.js';
import { EmbeddingBackfiller, EmbeddingClient } from './embed.js';
import { MemorySession } from './session.js';
import { MemoryStore } from './store.js';
import { MemoryConsolidationQueue } from './updater.js';
import { liveMessage } from '../i18n/messages.js';
function record(value) {
    return typeof value === 'object' && value !== null && !Array.isArray(value);
}
export function persistMemoryPreferences(dataDir, patch) {
    const path = join(dataDir, 'config.json');
    const raw = existsSync(path)
        ? JSON.parse(readFileSync(path, 'utf8').replace(/^\uFEFF/u, ''))
        : {};
    if (!record(raw))
        throw new Error('Qwen Live Harness configuration must be an object.');
    resolveMemoryConfig(raw['memory'], dataDir, path);
    const memory = record(raw['memory']) ? { ...raw['memory'] } : {};
    if (patch.enabled !== undefined)
        memory['enabled'] = patch.enabled;
    if (patch.defaultId !== undefined)
        memory['defaultId'] = patch.defaultId;
    if (patch.model !== undefined)
        memory['updater'] = {
            ...(record(memory['updater']) ? memory['updater'] : {}),
            model: patch.model,
        };
    if (patch.visualEnabled !== undefined)
        memory['observer'] = {
            ...(record(memory['observer']) ? memory['observer'] : {}),
            enabled: patch.visualEnabled,
        };
    const resolved = resolveMemoryConfig(memory, dataDir, path);
    const next = { ...raw, memory };
    mkdirSync(dataDir, { recursive: true, mode: 0o700 });
    const temporary = `${path}.${randomUUID()}.tmp`;
    try {
        const fd = openSync(temporary, 'wx', 0o600);
        try {
            writeFileSync(fd, JSON.stringify(next, null, 2) + '\n');
            fsyncSync(fd);
        }
        finally {
            closeSync(fd);
        }
        renameSync(temporary, path);
    }
    catch (error) {
        try {
            unlinkSync(temporary);
        }
        catch {
            /* no temporary file remains */
        }
        throw error;
    }
    return resolved;
}
export class MemoryService {
    options;
    config;
    store;
    embedder;
    backfillers = new Map();
    consolidation = new MemoryConsolidationQueue();
    finished = new WeakSet();
    attachments = new Set();
    libraries = [];
    locked = false;
    closed = false;
    closing = false;
    closePromise;
    consolidationClosed = false;
    error;
    constructor(options) {
        this.options = options;
        this.config = structuredClone(options.config);
        this.store = new MemoryStore({
            directory: this.config.dir,
            defaultId: 'default',
            log: options.log,
        });
        this.embedder = new EmbeddingClient({
            config: this.config.retrieve,
            connection: options.connection,
            log: options.log,
            fetch: options.fetch,
        });
        try {
            if (this.config.enabled)
                this.ensureSelected();
            this.refreshLibraries();
        }
        catch (error) {
            this.reportFailure(error);
        }
    }
    get settings() {
        return structuredClone(this.config);
    }
    state() {
        return {
            enabled: this.config.enabled,
            visualEnabled: this.config.observer.enabled,
            libraryId: this.config.defaultId,
            model: this.config.updater.model,
            libraries: this.libraries.map((library) => ({ ...library })),
            locked: this.locked,
            ...(this.error ? { error: this.error } : {}),
        };
    }
    setLocked(locked) {
        if (this.locked === locked)
            return;
        this.locked = locked;
        this.options.onChange?.();
    }
    applyAction(action) {
        if (this.closed || this.closing)
            throw new Error(liveMessage('memoryUI.closed'));
        if (this.locked &&
            ['select', 'create', 'set_model'].includes(action.action)) {
            throw new Error(liveMessage('memoryUI.locked'));
        }
        this.error = undefined;
        let patch = {};
        switch (action.action) {
            case 'set_enabled':
                if (action.enabled)
                    this.ensureSelected();
                patch = { enabled: action.enabled, defaultId: this.config.defaultId };
                break;
            case 'set_visual_enabled':
                patch = { visualEnabled: action.enabled };
                break;
            case 'select':
                this.store.getLibrary(action.libraryId);
                patch = { defaultId: action.libraryId };
                break;
            case 'create': {
                const library = this.store.createLibrary(action.name);
                patch = { defaultId: library.id };
                break;
            }
            case 'rename':
                this.store.renameLibrary(action.libraryId, action.name);
                break;
            case 'set_model':
                patch = { model: action.model };
                break;
            default:
                throw new Error(liveMessage('memoryUI.unsupported'));
        }
        if (Object.keys(patch).length)
            this.config = persistMemoryPreferences(this.options.dataDir, patch);
        this.refreshLibraries();
        this.options.onChange?.();
        return this.state();
    }
    attach(options) {
        if (!this.config.enabled || this.closed || this.closing)
            return undefined;
        try {
            for (const pending of this.attachments) {
                if (pending.closed)
                    this.finish(pending);
                if (pending.sessionId === options.sessionId &&
                    this.attachments.has(pending))
                    throw new Error('Previous memory attachment has not finished.');
            }
            this.ensureSelected();
            const libraryId = this.config.defaultId;
            let backfiller = this.backfillers.get(libraryId);
            if (!backfiller) {
                backfiller = new EmbeddingBackfiller(this.embedder, (id, vector, model) => {
                    if (!this.closed)
                        this.store.writeVector(libraryId, 'dialogue', id, vector, model);
                }, this.options.log);
                this.backfillers.set(libraryId, backfiller);
            }
            if (this.embedder.available) {
                void this.embedder.warmUp();
                for (const segment of this.store.missingVectorSegments(libraryId, this.embedder.model, 4096)) {
                    backfiller.enqueue(segment.id, segment.body);
                }
            }
            const session = new MemorySession({
                store: this.store,
                libraryId,
                sessionId: options.sessionId,
                config: structuredClone(this.config),
                maxPromptChars: options.maxPromptChars,
                connection: this.options.connection,
                embedder: this.embedder,
                log: this.options.log,
                fetch: this.options.fetch,
                visualSource: options.visualSource,
                captureVision: options.captureVision,
                enqueueEmbedding: (id, body) => {
                    backfiller.enqueue(id, body);
                },
            });
            this.attachments.add(session);
            this.refreshLibraries();
            return session;
        }
        catch (error) {
            this.reportFailure(error);
            return undefined;
        }
    }
    finish(session) {
        if (this.finished.has(session))
            return;
        try {
            session.close();
        }
        catch (error) {
            this.reportFailure(error);
            return;
        }
        this.finished.add(session);
        this.attachments.delete(session);
        if (!this.closed)
            void this.consolidation.submit(session);
    }
    close() {
        this.closePromise ??= this.closeResources().catch((error) => {
            this.closePromise = undefined;
            throw error;
        });
        return this.closePromise;
    }
    async closeResources() {
        this.closing = true;
        for (const session of this.attachments)
            this.finish(session);
        if (!this.closed) {
            this.closed = true;
            for (const backfiller of this.backfillers.values())
                backfiller.close();
            this.embedder.close();
        }
        if (this.attachments.size) {
            if (!this.consolidationClosed) {
                this.consolidation.close();
                this.consolidationClosed = true;
            }
            throw new Error('Memory session persistence failed; retry shutdown.');
        }
        if (!this.consolidationClosed) {
            const complete = await this.consolidation.drain(this.config.updater.shutdownWaitSec * 1000);
            this.consolidation.close();
            this.consolidationClosed = true;
            if (!complete)
                this.options.log?.('memory.updater.shutdown_abandoned');
        }
        this.store.close();
    }
    ensureSelected() {
        if (!this.store.exists(this.config.defaultId)) {
            const fallback = this.store.ensureDefault();
            if (this.config.defaultId !== fallback.id)
                this.error = liveMessage('memoryUI.fallback');
            this.config.defaultId = fallback.id;
        }
    }
    refreshLibraries() {
        this.libraries = this.store
            .listLibraries()
            .map(({ id, name }) => ({ id, name }));
    }
    reportFailure(error) {
        this.error =
            error instanceof RangeError && error.message.includes('prompt budget')
                ? liveMessage('memoryUI.budget')
                : liveMessage('memoryUI.storage');
        this.options.log?.('memory.storage.failed', {
            kind: error instanceof Error ? error.name : 'unknown',
        });
        this.options.onChange?.();
    }
}
