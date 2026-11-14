/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
import { reportNoteForDisplay } from '../subagents/display-text.js';
const PENDING = new Set([
    'queued',
    'submitted',
    'speaking',
]);
/** Display-only ledger. It owns no jobs, permissions or execution state. */
export class SessionReports {
    changed;
    records = new Map();
    seen = new Map();
    fallbackSources = new Set();
    seq = 0;
    revision = 0;
    omitted = 0;
    constructor(changed) {
        this.changed = changed;
    }
    clear() {
        this.records.clear();
        this.seen.clear();
        this.fallbackSources.clear();
        this.omitted = 0;
        this.publish();
    }
    add(backend, report, session) {
        const key = JSON.stringify([backend, report.callId, report.id]);
        if (this.seen.has(key))
            return undefined;
        if (this.records.size >= 100 &&
            ![...this.records.values()].some((item) => !PENDING.has(item.announcement)))
            return undefined;
        const view = {
            id: `report_${++this.seq}`,
            backend,
            source: report.source,
            sourceStatus: report.sourceStatus,
            ...(session ? { session } : {}),
            category: report.category,
            text: report.text,
            receivedAt: report.receivedAt,
            updatedAt: report.receivedAt,
            announcement: 'queued',
        };
        this.records.set(view.id, view);
        if (report.sourceIsFallback)
            this.fallbackSources.add(view.id);
        this.seen.set(key, view.id);
        while (this.seen.size > 256)
            this.seen.delete(this.seen.keys().next().value);
        return view;
    }
    get(id) {
        const report = this.records.get(id);
        return report ? { ...report } : undefined;
    }
    reject(id) {
        this.records.delete(id);
        this.fallbackSources.delete(id);
    }
    update(id, announcement, note) {
        const report = this.records.get(id);
        if (!report)
            return;
        report.announcement = announcement;
        report.updatedAt = Math.max(report.receivedAt, Date.now());
        if (note)
            report.note = note;
        while (this.records.size > 100) {
            const old = [...this.records.values()].find((item) => item.id !== id && !PENDING.has(item.announcement));
            if (!old)
                break;
            this.records.delete(old.id);
            this.fallbackSources.delete(old.id);
            this.omitted += 1;
        }
        this.publish(report);
    }
    end() {
        for (const report of this.records.values()) {
            if (PENDING.has(report.announcement)) {
                this.update(report.id, 'unspoken', 'The call ended before playback was confirmed.');
            }
        }
    }
    page() {
        return [...this.records.values()]
            .reverse()
            .map((report) => ({ ...report }));
    }
    /** Host-only projection; tools retain the original source and note structure. */
    displayPage() {
        return this.page().map((report) => ({
            ...report,
            source: this.fallbackSources.has(report.id) ? '' : report.source,
            ...(report.note ? { note: reportNoteForDisplay(report.note) } : {}),
        }));
    }
    publish(report) {
        this.revision += 1;
        this.changed(report ? { ...report } : undefined);
    }
}
