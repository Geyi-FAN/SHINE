/**
 * @license
 * Copyright 2026 Alibaba Group Holding Limited
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 * Adapted to TypeScript from qwen-omni-realtime-agent; modified for Qwen Live Harness.
 */
import { randomUUID } from 'node:crypto';
import { PROACTIVE_MONITOR_FPS } from './media-cadence.js';
import { QWEN_REALTIME_INPUT_SAMPLE_RATE, QWEN_REALTIME_LIMITS, } from '../realtime/realtime-session.js';
import { DashScopeRealtimeMonitor, } from './realtime-monitor.js';
import { buildMonitorInstruction, formatProactiveEvent, } from './monitor-protocol.js';
import { ProactiveTaskManager, } from './task-manager.js';
const MAX_TIMEOUT_MS = 2_147_483_647;
export class ProactiveScheduler {
    options;
    manager;
    monitors = new Map();
    evidence = new Map();
    visualCaptureFailures = new Map();
    repeats = new Map();
    cooldownAudioDrops = new Map();
    timers = new Map();
    deliveries = new Map();
    deliveryOutcomes = new Map();
    deliveryTimers = new Map();
    createMonitor;
    now;
    pollTimer;
    visionTimer;
    visionCaptureInFlight = false;
    lastVisionAt = 0;
    disposed = false;
    diagnosticStates = new Map();
    constructor(options) {
        this.options = options;
        this.manager = new ProactiveTaskManager(undefined, (task) => this.notifyTask(task));
        this.createMonitor =
            options.createMonitor ??
                ((monitorOptions, callbacks) => new DashScopeRealtimeMonitor(monitorOptions, callbacks));
        this.now = options.now ?? Date.now;
        this.startLoops();
    }
    createPerceptionMonitor(input) {
        this.ensureActive();
        const task = this.manager.createMonitor(input);
        this.installMonitor(task);
        return this.manager.get(task.taskId) ?? task;
    }
    createLiveNarration(input) {
        this.ensureActive();
        const task = this.manager.createNarration(input);
        this.installMonitor(task);
        return this.manager.get(task.taskId) ?? task;
    }
    createTimer(input) {
        this.ensureActive();
        const task = this.manager.createTimer(input);
        const running = this.manager.mutate(task.taskId, task.generation, (current) => {
            if (current.status !== 'provisioning')
                return false;
            current.status = 'running';
            return true;
        });
        if (!running) {
            throw new Error('Timer left provisioning before it could be activated.');
        }
        this.armTimer(task);
        this.notifyTask(this.manager.get(task.taskId));
        return this.manager.get(task.taskId) ?? running;
    }
    updateTask(input) {
        this.ensureActive();
        const before = this.manager.listActive();
        const updated = this.manager.update(input);
        const previous = before.find((task) => task.taskId === updated.taskId);
        this.invalidateDeliveries(new Set([updated.taskId]));
        if (updated.taskType === 'time_reminder') {
            const record = this.timers.get(updated.taskId);
            if (record &&
                previous?.taskType === 'time_reminder' &&
                previous.durationSec === updated.durationSec) {
                record.generation = updated.generation;
            }
            else {
                this.clearTimer(updated.taskId);
                this.armTimer(updated);
            }
            return this.manager.get(updated.taskId) ?? updated;
        }
        this.closeMonitor(updated.taskId);
        this.visualCaptureFailures.delete(updated.taskId);
        this.flushCooldownAudioDrops(updated.taskId, 'task_updated');
        this.repeats.delete(updated.taskId);
        const current = this.manager.mutate(updated.taskId, updated.generation, (candidate) => {
            if (candidate.status !== 'running')
                return false;
            candidate.status = 'provisioning';
            return true;
        });
        if (!current || current.taskType !== 'perception_monitor') {
            this.failTask(updated.taskId, updated.generation, 'Updated monitor could not enter provisioning.');
            throw new Error('Updated monitor could not enter provisioning.');
        }
        this.installMonitor(current);
        return this.manager.get(updated.taskId) ?? current;
    }
    cancelTasks(selector) {
        this.ensureActive();
        const cancelled = this.manager.cancel(selector);
        for (const task of cancelled) {
            this.cleanupTask(task.taskId);
        }
        this.invalidateDeliveries(new Set(cancelled.map((task) => task.taskId)));
        return cancelled;
    }
    cancelTaskById(taskId) {
        this.ensureActive();
        const task = this.manager.cancelById(taskId);
        if (!task)
            return undefined;
        this.cleanupTask(task.taskId);
        this.invalidateDeliveries(new Set([task.taskId]));
        return task;
    }
    listTasks() {
        const pendingCounts = new Map();
        for (const { delivery } of this.deliveries.values()) {
            pendingCounts.set(delivery.taskId, (pendingCounts.get(delivery.taskId) ?? 0) + 1);
        }
        return this.manager.listActive().map((task) => {
            const timer = task.taskType === 'time_reminder'
                ? this.timers.get(task.taskId)
                : undefined;
            return {
                ...task,
                pendingDeliveryCount: pendingCounts.get(task.taskId) ?? 0,
                ...(timer
                    ? { remainingSec: Math.max(0, (timer.deadline - this.now()) / 1_000) }
                    : {}),
            };
        });
    }
    feedAudio(pcm16) {
        if (this.disposed || pcm16.byteLength === 0)
            return;
        const capturedAt = this.now();
        for (const task of this.manager.activePerceptionTasks()) {
            if (!task.modalities.includes('audio'))
                continue;
            if (!this.resumeRepeatForMedia(task, capturedAt)) {
                this.recordCooldownAudioDrop(task, capturedAt, pcm16.byteLength);
                continue;
            }
            const monitor = this.monitors.get(task.taskId);
            if (!monitor?.feedAudio(pcm16))
                continue;
            const state = this.evidenceFor(task.taskId);
            state.audio.push({ capturedAt, bytes: pcm16.byteLength });
            this.pruneEvidence(state, capturedAt);
        }
    }
    feedImage(jpegBase64) {
        this.forwardImage(jpegBase64, this.now(), true);
    }
    forwardImage(jpegBase64, capturedAt, rateLimit) {
        if (this.disposed || !jpegBase64)
            return;
        const minimumGap = 1_000 / PROACTIVE_MONITOR_FPS;
        if (rateLimit && capturedAt - this.lastVisionAt < minimumGap)
            return;
        const tasks = this.manager
            .activePerceptionTasks()
            .filter((task) => task.modalities.includes('vision') &&
            task.createdAt <= capturedAt &&
            this.resumeRepeatForMedia(task, capturedAt));
        if (tasks.length === 0)
            return;
        this.lastVisionAt = Math.max(this.lastVisionAt, capturedAt);
        for (const task of tasks) {
            const monitor = this.monitors.get(task.taskId);
            if (!monitor?.feedImage(jpegBase64, capturedAt))
                continue;
            const state = this.evidenceFor(task.taskId);
            this.pruneEvidence(state, capturedAt);
            const lastFrame = state.vision.at(-1);
            const continuityGapMs = Math.max(1_000, (3 * 1_000) / PROACTIVE_MONITOR_FPS);
            if (lastFrame !== undefined && capturedAt - lastFrame > continuityGapMs) {
                state.vision = [];
                state.visionStartedAt = undefined;
            }
            state.visionStartedAt ??= capturedAt;
            state.vision.push(capturedAt);
        }
    }
    resetVisualSource() {
        if (this.disposed)
            return;
        this.lastVisionAt = 0;
        for (const task of this.manager.activePerceptionTasks()) {
            if (!task.modalities.includes('vision'))
                continue;
            this.visualCaptureFailures.delete(task.taskId);
            if (!this.monitors.has(task.taskId))
                continue;
            this.closeMonitor(task.taskId);
            this.clearTaskEvidence(task.taskId);
            this.installMonitor(task);
        }
    }
    announcementStarted(delivery, options) {
        const current = this.deliveries.get(delivery.deliveryId);
        if (!current || !this.sameDelivery(current.delivery, delivery))
            return;
        if (current.status !== 'queued')
            return;
        current.status = 'preparing';
        this.notifyTaskId(delivery.taskId);
        const fallback = options?.fallback === true;
        const timer = setTimeout(() => {
            this.deliveryTimers.delete(delivery.deliveryId);
            const error = 'Proactive announcement playback acknowledgement timed out.';
            if (fallback)
                this.undeliverDelivery(delivery, error);
            else
                this.failDelivery(delivery, error);
        }, this.options.config.scheduler.repeat.maxWaitTtsSec * 1_000);
        timer.unref?.();
        this.deliveryTimers.set(delivery.deliveryId, timer);
    }
    playbackStarted(delivery) {
        const current = this.deliveries.get(delivery.deliveryId);
        if (!current || !this.sameDelivery(current.delivery, delivery))
            return;
        current.status = 'announcing';
        this.notifyTaskId(delivery.taskId);
    }
    deferDelivery(delivery) {
        const current = this.deliveries.get(delivery.deliveryId);
        if (!current || !this.sameDelivery(current.delivery, delivery))
            return false;
        current.status = 'queued';
        this.notifyTaskId(delivery.taskId);
        this.clearDeliveryTimer(delivery.deliveryId);
        this.debug('proactive.delivery_deferred', {
            taskId: delivery.taskId,
            deliveryId: delivery.deliveryId,
        });
        return true;
    }
    acknowledgeDelivery(delivery) {
        const current = this.deliveries.get(delivery.deliveryId);
        if (!current || !this.sameDelivery(current.delivery, delivery))
            return;
        const task = this.manager.get(delivery.taskId);
        if (!task || task.generation !== delivery.taskGeneration)
            return;
        this.clearDeliveryTimer(delivery.deliveryId);
        this.deliveries.delete(delivery.deliveryId);
        this.deliveryOutcomes.set(task.taskId, 'delivered');
        this.debug('proactive.delivery_acknowledged', {
            taskId: delivery.taskId,
            deliveryId: delivery.deliveryId,
        });
        if (!task.repeat) {
            this.manager.completeDelivery(task.taskId, task.generation);
            this.cleanupTask(task.taskId);
        }
        this.notifyTaskId(task.taskId, 'delivered');
    }
    failDelivery(delivery, error) {
        const current = this.deliveries.get(delivery.deliveryId);
        if (!current || !this.sameDelivery(current.delivery, delivery))
            return;
        this.failTask(delivery.taskId, delivery.taskGeneration, error);
    }
    undeliverDelivery(delivery, error) {
        const current = this.deliveries.get(delivery.deliveryId);
        const task = this.manager.get(delivery.taskId);
        if (!current ||
            !this.sameDelivery(current.delivery, delivery) ||
            !task ||
            task.generation !== delivery.taskGeneration)
            return;
        this.clearDeliveryTimer(delivery.deliveryId);
        this.deliveries.delete(delivery.deliveryId);
        this.deliveryOutcomes.set(task.taskId, 'undelivered');
        if (!task.repeat) {
            this.manager.completeDelivery(task.taskId, task.generation);
            this.cleanupTask(task.taskId);
        }
        this.notifyTaskId(task.taskId, 'undelivered');
        this.debug('proactive.delivery_undelivered', {
            taskId: task.taskId,
            deliveryId: delivery.deliveryId,
            reason: error.slice(0, 300),
        });
        try {
            this.options.onDeliveryInvalidated?.(delivery);
        }
        catch {
            /* delivery is already retired; observers cannot resurrect it */
        }
    }
    dispose() {
        if (this.disposed)
            return;
        this.disposed = true;
        if (this.pollTimer !== undefined)
            clearInterval(this.pollTimer);
        if (this.visionTimer !== undefined)
            clearInterval(this.visionTimer);
        this.pollTimer = undefined;
        this.visionTimer = undefined;
        for (const task of this.manager.listActive()) {
            this.notifyTask({ ...task, status: 'cancelled', updatedAt: this.now() });
            this.cleanupTask(task.taskId);
        }
        this.invalidateDeliveries();
        this.manager.clear();
        this.diagnosticStates.clear();
        this.deliveryOutcomes.clear();
    }
    startLoops() {
        this.pollTimer = setInterval(() => this.poll(), this.options.config.scheduler.evalIntervalSec * 1_000);
        this.pollTimer.unref?.();
        if (this.options.captureVision) {
            this.visionTimer = setInterval(() => void this.captureVision(), 1_000 / PROACTIVE_MONITOR_FPS);
            this.visionTimer.unref?.();
        }
    }
    async captureVision() {
        if (this.disposed || this.visionCaptureInFlight)
            return;
        const now = this.now();
        const tasks = this.manager
            .activePerceptionTasks()
            .filter((task) => task.modalities.includes('vision') &&
            this.resumeRepeatForMedia(task, now));
        if (tasks.length === 0)
            return;
        this.visionCaptureInFlight = true;
        try {
            const image = await this.options.captureVision?.();
            if (!image || image.trim().length === 0)
                return;
            // The timer already samples at the configured rate. Throttling again
            // using completion times drops valid frames under small capture jitter
            // (e.g. 600ms then 1090ms), breaking a two-frame visual grid.
            this.forwardImage(image, now, false);
            this.clearVisualCaptureFailures(tasks);
        }
        catch {
            this.recordVisualCaptureFailure(tasks);
            this.debug('proactive.visual_capture_failed', {
                taskIds: tasks.map((task) => task.taskId),
                reason: 'capture_rejected',
            });
        }
        finally {
            this.visionCaptureInFlight = false;
        }
    }
    recordVisualCaptureFailure(tasks) {
        const now = this.now();
        for (const expected of tasks) {
            const task = this.manager.get(expected.taskId);
            if (!task ||
                task.taskType !== 'perception_monitor' ||
                task.generation !== expected.generation ||
                (task.status !== 'provisioning' && task.status !== 'running') ||
                !task.modalities.includes('vision')) {
                continue;
            }
            const state = this.evidenceFor(task.taskId);
            this.pruneEvidence(state, now);
            if (state.vision.length > 0)
                continue;
            const failures = (this.visualCaptureFailures.get(task.taskId) ?? 0) + 1;
            this.visualCaptureFailures.set(task.taskId, failures);
            if (failures >= this.options.config.scheduler.maxFailuresPerTask) {
                this.failTask(task.taskId, task.generation, 'Maximum visual capture failures exceeded.');
            }
        }
    }
    clearVisualCaptureFailures(tasks) {
        for (const expected of tasks) {
            const task = this.manager.get(expected.taskId);
            if (task?.generation === expected.generation) {
                this.visualCaptureFailures.delete(task.taskId);
            }
        }
    }
    installMonitor(task) {
        const generation = task.generation;
        let monitor;
        const isCurrentMonitor = () => this.monitors.get(task.taskId) === monitor;
        try {
            monitor = this.createMonitor({
                endpoint: this.options.realtime.endpoint,
                ...(this.options.realtime.apiKey
                    ? { apiKey: this.options.realtime.apiKey }
                    : {}),
                model: this.options.realtime.model,
                taskId: task.taskId,
                taskGeneration: generation,
                instruction: buildMonitorInstruction({
                    title: task.title,
                    taskDescription: task.taskDescription,
                    monitorMode: task.monitorMode,
                    ...(task.monitorMode === 'always'
                        ? {
                            narrationStyle: task.interventionText,
                            narrationPreferences: task.narrationPreferences,
                        }
                        : {}),
                }),
                monitorMode: task.monitorMode,
                modalities: task.modalities,
                contextWindowSec: {
                    vision: this.options.config.vision.windowSizeSec,
                    audio: this.options.config.audio.windowSizeSec,
                },
                sessionRecycleEvals: this.options.config.monitor.sessionRecycleEvals,
                representationCompact: this.options.config.monitor.representationCompact,
                monitorDebug: this.options.monitorDebug,
                debugArchive: this.options.debugArchive,
                debugContext: this.options.debugContext,
            }, {
                onReady: (taskGeneration) => {
                    if (!isCurrentMonitor())
                        return;
                    const current = this.manager.mutate(task.taskId, taskGeneration, (candidate) => {
                        if (candidate.status !== 'provisioning')
                            return false;
                        candidate.status = 'running';
                        return true;
                    });
                    if (current?.status === 'running') {
                        this.debug('proactive.task_running', { taskId: task.taskId });
                    }
                },
                onResult: (result, taskGeneration) => {
                    if (!isCurrentMonitor())
                        return;
                    this.onMonitorResult(task.taskId, taskGeneration, result);
                },
                onLifecycleError: (error, taskGeneration) => {
                    if (!isCurrentMonitor())
                        return;
                    this.onMonitorLifecycleError(task.taskId, taskGeneration, error);
                },
                onDebug: (event, details) => {
                    if (isCurrentMonitor())
                        this.debug(event, details);
                },
            });
        }
        catch (error) {
            this.failMonitorSetup(task.taskId, generation, error);
            return;
        }
        this.monitors.set(task.taskId, monitor);
        this.evidence.set(task.taskId, { vision: [], audio: [] });
        let opening;
        try {
            opening = monitor.start();
        }
        catch (error) {
            if (isCurrentMonitor()) {
                this.failMonitorSetup(task.taskId, generation, error);
            }
            return;
        }
        void opening.catch((error) => {
            if (!isCurrentMonitor())
                return;
            this.failMonitorSetup(task.taskId, generation, error);
        });
    }
    failMonitorSetup(taskId, generation, error) {
        const message = error instanceof Error ? error.message : String(error);
        this.failTask(taskId, generation, `Monitor setup failed: ${message}`);
    }
    armTimer(task) {
        const deadline = this.now() + task.durationSec * 1_000;
        const record = {
            generation: task.generation,
            deadline,
        };
        this.timers.set(task.taskId, record);
        this.scheduleTimerSegment(task.taskId, record);
    }
    scheduleTimerSegment(taskId, record) {
        if (this.timers.get(taskId) !== record)
            return;
        const remainingMs = record.deadline - this.now();
        if (remainingMs <= 0) {
            this.fireTimer(taskId, record);
            return;
        }
        record.timer = setTimeout(() => this.scheduleTimerSegment(taskId, record), Math.min(remainingMs, MAX_TIMEOUT_MS));
        record.timer.unref?.();
    }
    fireTimer(taskId, record) {
        if (this.timers.get(taskId) !== record)
            return;
        this.timers.delete(taskId);
        const task = this.manager.get(taskId);
        if (!task ||
            task.taskType !== 'time_reminder' ||
            task.status !== 'running' ||
            task.generation !== record.generation) {
            return;
        }
        this.trigger(task, task.reminderText, ['text']);
    }
    poll() {
        if (this.disposed)
            return;
        const now = this.now();
        for (const id of this.timers.keys())
            this.notifyTaskId(id);
        for (const task of this.manager.activePerceptionTasks()) {
            if (!this.resumeRepeatForMedia(task, now)) {
                this.debugGate(task, 'cooldown', {});
                continue;
            }
            const state = this.evidenceFor(task.taskId);
            this.pruneEvidence(state, now);
            const audioSeconds = this.audioSeconds(state);
            const media = {
                visionFrames: state.vision.length,
                audioSeconds: Math.round(audioSeconds * 100) / 100,
                modalities: task.modalities,
            };
            if (!this.hasWarmEvidence(task, state)) {
                this.debugGate(task, 'waiting_for_media', media);
                continue;
            }
            const accepted = this.monitors.get(task.taskId)?.requestEvaluation() ?? false;
            this.debugGate(task, accepted ? 'evaluation_requested' : 'evaluation_busy', media);
        }
    }
    hasWarmEvidence(task, state) {
        if (task.modalities.includes('vision')) {
            if (state.vision.length === 0)
                return false;
            const minimumFrames = Math.ceil(this.options.config.vision.minEvalDurationSec * PROACTIVE_MONITOR_FPS);
            // Retain the nominal-rate contract, but let slower successful captures
            // warm by elapsed observation time across a continuously fresh window.
            if (state.vision.length < minimumFrames &&
                state.vision.at(-1) - state.visionStartedAt <
                    this.options.config.vision.minEvalDurationSec * 1_000) {
                return false;
            }
        }
        if (task.modalities.includes('audio')) {
            if (state.audio.length === 0)
                return false;
            const seconds = this.audioSeconds(state);
            if (seconds < this.options.config.audio.minEvalDurationSec)
                return false;
        }
        return true;
    }
    audioSeconds(state) {
        return (state.audio.reduce((total, input) => total + input.bytes, 0) /
            (QWEN_REALTIME_INPUT_SAMPLE_RATE * 2));
    }
    onMonitorResult(taskId, generation, result) {
        const task = this.manager.get(taskId);
        if (!task ||
            task.taskType !== 'perception_monitor' ||
            task.generation !== generation ||
            task.status !== 'running') {
            return;
        }
        const observedRepeat = this.repeats.get(taskId);
        this.debug('proactive.evaluation_result', {
            taskId,
            generation,
            status: task.status,
            monitorMode: task.monitorMode,
            repeat: task.repeat,
            cooldownUntil: observedRepeat?.cooldownUntil ?? 0,
            awaitingFalse: observedRepeat?.awaitingFalse ?? false,
            triggered: result.triggered,
            failed: Boolean(result.error),
            summaryChars: result.summary.length,
            ...(result.ignoredAction ? { ignoredAction: result.ignoredAction } : {}),
        });
        const repeat = this.repeats.get(taskId);
        if (repeat && repeat.cooldownUntil > 0) {
            this.resumeRepeatForMedia(task, this.now());
            this.debugEvaluationDecision(task, 'ignored_cooldown');
            return;
        }
        if (result.error) {
            const failed = this.manager.mutate(taskId, generation, (current) => {
                if (current.status !== 'running')
                    return false;
                current.failureCount += 1;
                return true;
            });
            if (failed &&
                failed.failureCount >= this.options.config.scheduler.maxFailuresPerTask) {
                this.failTask(taskId, generation, 'Maximum monitor failures exceeded.');
            }
            this.debugEvaluationDecision(task, 'error');
            return;
        }
        this.manager.mutate(taskId, generation, (current) => {
            if (current.status !== 'running')
                return false;
            current.failureCount = 0;
            return true;
        });
        if (task.repeat && task.monitorMode === 'event' && repeat?.awaitingFalse) {
            if (!result.triggered)
                repeat.awaitingFalse = false;
            this.debugEvaluationDecision(task, result.triggered ? 'suppressed_awaiting_false' : 'rearmed_false');
            return;
        }
        if (!result.triggered) {
            this.debugEvaluationDecision(task, 'no_trigger');
            return;
        }
        const accepted = this.trigger(task, result.summary, task.modalities);
        this.debugEvaluationDecision(task, accepted ? 'notification_accepted' : 'notification_rejected');
    }
    onMonitorLifecycleError(taskId, generation, error) {
        const task = this.manager.get(taskId);
        if (!task || task.generation !== generation)
            return;
        if (task.status === 'provisioning') {
            this.failTask(taskId, generation, `Monitor setup failed: ${error.message}`);
            return;
        }
        if (task.status === 'running') {
            this.onMonitorResult(taskId, generation, {
                triggered: false,
                summary: '',
                currentState: '',
                error: error.message,
            });
        }
    }
    trigger(task, summary, sourceModalities) {
        const delivering = this.manager.beginDelivery(task.taskId, task.generation, summary);
        if (!delivering)
            return false;
        const interventionText = delivering.taskType === 'perception_monitor'
            ? delivering.interventionText
            : '';
        const deliveryId = `delivery_${randomUUID().replaceAll('-', '')}`;
        const delivery = {
            taskId: delivering.taskId,
            taskGeneration: delivering.generation,
            deliveryId,
            event: formatProactiveEvent({
                taskId: delivering.taskId,
                deliveryId,
                title: delivering.title,
                taskType: delivering.taskType,
                summary,
                sourceModalities,
                interventionText,
                monitorMode: delivering.monitorMode,
                ...(delivering.taskType === 'perception_monitor' &&
                    delivering.narrationPreferences
                    ? {
                        narrationPreferences: delivering.narrationPreferences,
                        narrationFocus: delivering.taskDescription,
                    }
                    : {}),
            }),
        };
        if (delivery.event.length > QWEN_REALTIME_LIMITS.maxFunctionOutputChars) {
            this.failTask(delivering.taskId, delivering.generation, 'Proactive event exceeds the foreground response limit.');
            return false;
        }
        this.deliveries.set(deliveryId, { delivery, status: 'queued' });
        this.deliveryOutcomes.delete(delivering.taskId);
        this.notifyTaskId(delivering.taskId);
        if (delivering.repeat) {
            this.repeats.set(delivering.taskId, {
                cooldownUntil: this.now() + this.options.config.scheduler.repeat.cooldownSec * 1_000,
                awaitingFalse: delivering.monitorMode === 'event',
            });
            this.debug('proactive.cooldown_started', {
                taskId: delivering.taskId,
                generation: delivering.generation,
                monitorMode: delivering.monitorMode,
                cooldownUntil: this.repeats.get(delivering.taskId).cooldownUntil,
                awaitingFalse: delivering.monitorMode === 'event',
            });
            this.clearTaskEvidence(delivering.taskId);
            this.monitors.get(delivering.taskId)?.resetPendingCapture();
            this.debug('proactive.buffer_reset', {
                taskId: delivering.taskId,
                generation: delivering.generation,
                reason: 'repeat_trigger',
                residentHistoryRetained: true,
            });
        }
        else if (delivering.taskType === 'perception_monitor') {
            this.closeMonitor(delivering.taskId);
            this.evidence.delete(delivering.taskId);
        }
        let accepted = false;
        try {
            accepted = this.options.onEvent(delivery);
        }
        catch {
            this.debug('proactive.event_delivery_failed', {
                taskId: delivery.taskId,
                deliveryId,
                reason: 'admission_callback_failed',
            });
        }
        if (!accepted) {
            this.failDelivery(delivery, 'Proactive event delivery was rejected.');
            return false;
        }
        this.debug('proactive.event_queued', {
            taskId: delivery.taskId,
            deliveryId: delivery.deliveryId,
            generation: delivery.taskGeneration,
        });
        return true;
    }
    resumeRepeatForMedia(task, now) {
        if (task.status === 'provisioning')
            return true;
        if (task.status !== 'running')
            return false;
        const repeat = this.repeats.get(task.taskId);
        if (!repeat || repeat.cooldownUntil === 0)
            return true;
        if (repeat.cooldownUntil > now)
            return false;
        const previousCooldownUntil = repeat.cooldownUntil;
        repeat.cooldownUntil = 0;
        this.flushCooldownAudioDrops(task.taskId, 'cooldown_resumed');
        this.debug('proactive.cooldown_resumed', {
            taskId: task.taskId,
            generation: task.generation,
            cooldownUntil: previousCooldownUntil,
            resumedAt: now,
            awaitingFalse: repeat.awaitingFalse,
            clearBufferOnResume: this.options.config.scheduler.repeat.clearBufferOnResume,
        });
        if (this.options.config.scheduler.repeat.clearBufferOnResume) {
            this.clearTaskEvidence(task.taskId);
            this.monitors.get(task.taskId)?.resetPendingCapture();
            this.debug('proactive.buffer_reset', {
                taskId: task.taskId,
                generation: task.generation,
                reason: 'cooldown_resume',
                residentHistoryRetained: true,
            });
        }
        return true;
    }
    evidenceFor(taskId) {
        let state = this.evidence.get(taskId);
        if (!state) {
            state = { vision: [], audio: [] };
            this.evidence.set(taskId, state);
        }
        return state;
    }
    pruneEvidence(state, now) {
        const visionCutoff = now - this.options.config.vision.windowSizeSec * 1_000;
        const audioCutoff = now - this.options.config.audio.windowSizeSec * 1_000;
        state.vision = state.vision.filter((capturedAt) => capturedAt >= visionCutoff);
        if (state.vision.length === 0)
            state.visionStartedAt = undefined;
        state.audio = state.audio.filter((input) => input.capturedAt >= audioCutoff);
    }
    clearTaskEvidence(taskId) {
        this.evidence.set(taskId, { vision: [], audio: [] });
    }
    failTask(taskId, generation, error) {
        const failed = this.manager.fail(taskId, generation, error);
        if (!failed || failed.status !== 'failed')
            return undefined;
        this.cleanupTask(taskId);
        this.invalidateDeliveries(new Set([taskId]));
        this.notifyTaskFailed(failed, error);
        return failed;
    }
    notifyTaskFailed(task, error) {
        try {
            this.options.onTaskFailed?.(task, error);
        }
        catch {
            this.debug('proactive.task_failure_callback_failed', {
                taskId: task.taskId,
                reason: 'failure_callback_failed',
            });
        }
    }
    notifyTaskId(taskId, notification) {
        const task = this.manager.get(taskId);
        if (task)
            this.notifyTask(task, notification);
    }
    notifyTask(task, notification) {
        const terminal = ['completed', 'failed', 'cancelled'].includes(task.status);
        const pending = terminal
            ? []
            : [...this.deliveries.values()].filter((record) => record.delivery.taskId === task.taskId);
        const currentNotification = task.status === 'cancelled'
            ? undefined
            : pending.some((record) => record.status === 'announcing')
                ? 'speaking'
                : pending.some((record) => record.status === 'preparing')
                    ? 'preparing'
                    : pending.length
                        ? 'queued'
                        : (notification ?? this.deliveryOutcomes.get(task.taskId));
        if (this.options.debug) {
            const stateKey = JSON.stringify([
                task.generation,
                task.status,
                task.triggerCount,
                task.failureCount,
                pending.length,
                currentNotification,
            ]);
            if (this.diagnosticStates.get(`state:${task.taskId}`) !== stateKey) {
                this.diagnosticStates.set(`state:${task.taskId}`, stateKey);
                this.debug('proactive.task_state', {
                    taskId: task.taskId,
                    generation: task.generation,
                    status: task.status,
                    taskType: task.taskType,
                    triggerCount: task.triggerCount,
                    failureCount: task.failureCount,
                    pendingDeliveryCount: pending.length,
                    notification: currentNotification ?? 'none',
                });
            }
            if (terminal) {
                this.diagnosticStates.delete(`state:${task.taskId}`);
                this.diagnosticStates.delete(`gate:${task.taskId}`);
            }
        }
        if (!this.options.onTaskChanged)
            return;
        const timer = this.timers.get(task.taskId);
        try {
            this.options.onTaskChanged({
                ...task,
                pendingDeliveryCount: pending.length,
                ...(timer
                    ? {
                        remainingSec: Math.max(0, (timer.deadline - this.now()) / 1000),
                    }
                    : {}),
            }, currentNotification);
        }
        catch {
            // A read-only UI observer must never change task delivery semantics.
        }
    }
    cleanupTask(taskId) {
        this.closeMonitor(taskId);
        this.clearTimer(taskId);
        this.evidence.delete(taskId);
        this.visualCaptureFailures.delete(taskId);
        this.flushCooldownAudioDrops(taskId, 'task_ended');
        this.repeats.delete(taskId);
        this.diagnosticStates.delete(`state:${taskId}`);
        this.diagnosticStates.delete(`gate:${taskId}`);
    }
    invalidateDeliveries(taskIds) {
        const invalidated = [];
        for (const { delivery } of this.deliveries.values()) {
            if (taskIds && !taskIds.has(delivery.taskId))
                continue;
            this.deliveries.delete(delivery.deliveryId);
            this.clearDeliveryTimer(delivery.deliveryId);
            invalidated.push(delivery);
        }
        // Retract queued tails before aborting the active head, which can
        // synchronously reopen the Injector and submit its next item.
        for (const delivery of invalidated.reverse()) {
            this.options.onDeliveryInvalidated?.(delivery);
        }
    }
    closeMonitor(taskId) {
        const monitor = this.monitors.get(taskId);
        this.monitors.delete(taskId);
        monitor?.close();
    }
    clearTimer(taskId) {
        const record = this.timers.get(taskId);
        this.timers.delete(taskId);
        if (record?.timer !== undefined)
            clearTimeout(record.timer);
    }
    clearDeliveryTimer(deliveryId) {
        const timer = this.deliveryTimers.get(deliveryId);
        this.deliveryTimers.delete(deliveryId);
        if (timer !== undefined)
            clearTimeout(timer);
    }
    sameDelivery(current, candidate) {
        return (current?.deliveryId === candidate.deliveryId &&
            current.taskId === candidate.taskId &&
            current.taskGeneration === candidate.taskGeneration);
    }
    ensureActive() {
        if (this.disposed)
            throw new Error('The Proactive scheduler is closed.');
    }
    debug(event, details) {
        try {
            this.options.debug?.(event, details);
        }
        catch {
            // Diagnostics must not change task admission or delivery.
        }
    }
    debugEvaluationDecision(task, decision) {
        if (!this.options.debug)
            return;
        const current = this.manager.get(task.taskId);
        const repeat = this.repeats.get(task.taskId);
        this.debug('proactive.evaluation_decision', {
            taskId: task.taskId,
            generation: task.generation,
            decision,
            status: current?.status ?? task.status,
            monitorMode: task.monitorMode,
            repeat: task.repeat,
            cooldownUntil: repeat?.cooldownUntil ?? 0,
            awaitingFalse: repeat?.awaitingFalse ?? false,
        });
    }
    recordCooldownAudioDrop(task, capturedAt, bytes) {
        if (!this.options.debug || task.status !== 'running')
            return;
        const repeat = this.repeats.get(task.taskId);
        if (!repeat || repeat.cooldownUntil <= capturedAt)
            return;
        const dropped = this.cooldownAudioDrops.get(task.taskId) ?? {
            generation: task.generation,
            cooldownUntil: repeat.cooldownUntil,
            frames: 0,
            bytes: 0,
        };
        dropped.frames += 1;
        dropped.bytes += bytes;
        this.cooldownAudioDrops.set(task.taskId, dropped);
    }
    flushCooldownAudioDrops(taskId, reason) {
        const dropped = this.cooldownAudioDrops.get(taskId);
        if (!dropped)
            return;
        this.cooldownAudioDrops.delete(taskId);
        this.debug('proactive.cooldown_audio_dropped', {
            taskId,
            generation: dropped.generation,
            reason,
            cooldownUntil: dropped.cooldownUntil,
            audioFrames: dropped.frames,
            audioBytes: dropped.bytes,
            audioMs: (dropped.bytes / (QWEN_REALTIME_INPUT_SAMPLE_RATE * 2)) * 1_000,
        });
    }
    debugGate(task, reason, details) {
        if (!this.options.debug)
            return;
        if (!this.monitors.has(task.taskId) ||
            this.manager.get(task.taskId)?.generation !== task.generation)
            return;
        const key = `gate:${task.taskId}`;
        const state = `${task.generation}:${reason}`;
        if (this.diagnosticStates.get(key) === state)
            return;
        this.diagnosticStates.set(key, state);
        this.debug('proactive.evaluation_gate', {
            taskId: task.taskId,
            generation: task.generation,
            reason,
            ...details,
        });
    }
}
