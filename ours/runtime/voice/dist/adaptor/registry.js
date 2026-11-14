/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
export class BackendRegistry {
    entries;
    byName;
    /** In-flight secondary warm-ups by backend name; settled ones drop out. */
    warmups = new Map();
    closing = false;
    constructor(entries) {
        this.entries = entries.map((entry) => ({
            adaptor: entry.adaptor,
            isDefault: entry.isDefault,
            status: 'ready',
        }));
        this.byName = new Map(this.entries.map((entry) => [entry.adaptor.name, entry]));
    }
    get hasBackends() {
        return this.entries.length > 0;
    }
    get defaultAdaptor() {
        const entry = this.entries.find((candidate) => candidate.isDefault);
        if (!entry) {
            // Empty registries have no default. Callers must check hasBackends
            // before starting work; nonempty configuration validates its default.
            throw new Error('no default backend configured');
        }
        return entry.adaptor;
    }
    get defaultName() {
        return this.defaultAdaptor.name;
    }
    names() {
        return this.entries.map((entry) => entry.adaptor.name);
    }
    /** All registered backends, default first. */
    all() {
        return this.entries;
    }
    byAdaptorName(name) {
        return this.byName.get(name);
    }
    /**
     * The adaptor that owns a backend handle. Handles are minted only by
     * registered adaptors, so an unknown name is an invariant violation —
     * throw rather than guess.
     */
    adaptorFor(handle) {
        const entry = this.byName.get(handle.adaptor);
        if (!entry) {
            throw new Error(`unknown backend '${handle.adaptor}' (configured: ${this.names().join(', ')})`);
        }
        return entry.adaptor;
    }
    async preflight(log, progress) {
        if (!this.hasBackends)
            return;
        // Default first, and its failure aborts startup.
        progress?.({ backend: this.defaultAdaptor.name, stage: 'starting' });
        await this.defaultAdaptor.preflight();
        progress?.({ backend: this.defaultAdaptor.name, stage: 'ready' });
        // Secondaries warm up in the background. Their readiness is best-effort,
        // so it must never sit on the daemon's ready path: a package-runner
        // install can take minutes, and the daemon is usable without them.
        for (const entry of this.entries) {
            if (entry.isDefault)
                continue;
            void this.warmUp(entry, log, progress);
        }
    }
    /**
     * Await a secondary backend's in-flight warm-up, resolving immediately when
     * none is pending. Only entries reading 'starting' have one; every other
     * status is already settled.
     */
    async whenReady(name) {
        await this.warmups.get(name);
    }
    warmUp(entry, log, progress) {
        const name = entry.adaptor.name;
        const inFlight = this.warmups.get(name);
        if (inFlight)
            return inFlight;
        entry.status = 'starting';
        progress?.({ backend: name, stage: 'starting' });
        const running = (async () => {
            try {
                await entry.adaptor.preflight();
                entry.status = 'ready';
                progress?.({ backend: name, stage: 'ready' });
            }
            catch (error) {
                entry.status = 'unavailable';
                entry.lastError =
                    error instanceof Error ? error.message : String(error);
                // A shutdown that interrupts a warm-up is not a broken backend; the
                // adaptor reports itself closed, which would misread as a config fix.
                if (this.closing)
                    return;
                progress?.({ backend: name, stage: 'unavailable' });
                log(`backend '${name}' unavailable: ${entry.lastError}`);
            }
            finally {
                this.warmups.delete(name);
            }
            // Fire-and-forget: the outcome lives in status/lastError, so a warm-up
            // must never reject — an unhandled rejection would kill the daemon, and
            // whenReady() would surface a reporting fault as a backend failure.
        })().catch(() => { });
        this.warmups.set(name, running);
        return running;
    }
    async closeAll(log) {
        this.closing = true;
        await Promise.allSettled(this.entries.map(async (entry) => {
            try {
                await entry.adaptor.close();
            }
            catch (error) {
                log(`closing backend '${entry.adaptor.name}' failed: ${error instanceof Error ? error.message : String(error)}`);
            }
        }));
    }
}
