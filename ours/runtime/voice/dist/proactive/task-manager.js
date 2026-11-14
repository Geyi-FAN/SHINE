/**
 * @license
 * Copyright 2026 Alibaba Group Holding Limited
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 * Adapted to TypeScript from qwen-omni-realtime-agent; modified for Qwen Live Harness.
 */
import { randomUUID } from 'node:crypto';
import { DEFAULT_NARRATION_STYLE, MAX_NARRATION_SOURCE_CHARS, } from './monitor-protocol.js';
const TERMINAL_STATUSES = new Set([
    'completed',
    'cancelled',
    'failed',
]);
const MODALITY_ALIASES = new Map([
    ['vision', 'vision'],
    ['video', 'vision'],
    ['camera', 'vision'],
    ['image', 'vision'],
    ['visual', 'vision'],
    ['摄像头', 'vision'],
    ['视频', 'vision'],
    ['图像', 'vision'],
    ['视觉', 'vision'],
    ['audio', 'audio'],
    ['microphone', 'audio'],
    ['mic', 'audio'],
    ['sound', 'audio'],
    ['voice', 'audio'],
    ['auditory', 'audio'],
    ['麦克风', 'audio'],
    ['声音', 'audio'],
    ['音频', 'audio'],
    ['语音', 'audio'],
]);
function text(value, field) {
    if (typeof value !== 'string' || !value.trim()) {
        throw new Error(`${field} must be a non-empty string.`);
    }
    return value.trim();
}
function positiveNumber(value, field) {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
        throw new Error(`${field} must be a positive finite number.`);
    }
    return value;
}
function modalities(value) {
    if (!Array.isArray(value) || value.length === 0) {
        throw new Error('modalities must be a non-empty array.');
    }
    const result = [];
    for (const raw of value) {
        if (typeof raw !== 'string') {
            throw new Error('modalities must contain strings only.');
        }
        const key = raw
            .trim()
            .toLowerCase()
            .replace(/[\s_-]+/gu, ' ');
        const normalized = MODALITY_ALIASES.get(key);
        if (!normalized) {
            throw new Error(`Unsupported Proactive modality: ${raw}.`);
        }
        if (!result.includes(normalized))
            result.push(normalized);
    }
    return result;
}
function copyTask(task) {
    return {
        ...task,
        ...(task.taskType === 'perception_monitor'
            ? { modalities: [...task.modalities] }
            : {}),
        ...(task.taskType === 'perception_monitor' && task.narrationPreferences
            ? { narrationPreferences: { ...task.narrationPreferences } }
            : {}),
    };
}
export class ProactiveTaskManager {
    onChange;
    tasks = new Map();
    constructor(_legacyMaxConcurrentPerceptionTasks, onChange) {
        this.onChange = onChange;
    }
    createMonitor(input) {
        if (typeof input.repeat !== 'boolean') {
            throw new Error('repeat must be a boolean.');
        }
        return this.createPerception({
            title: text(input.title, 'title'),
            modalities: modalities(input.modalities),
            taskDescription: text(input.condition, 'condition'),
            interventionText: text(input.triggerResponse, 'trigger_response'),
            repeat: input.repeat,
            monitorMode: 'event',
        });
    }
    createNarration(input) {
        const preferences = input.narrationPreferences;
        if (preferences &&
            (typeof preferences.sourceRequest !== 'string' ||
                !preferences.sourceRequest.trim() ||
                preferences.sourceRequest.length > MAX_NARRATION_SOURCE_CHARS ||
                !['en', 'zh-CN'].includes(preferences.fallbackLanguage) ||
                (preferences.styleOverride !== undefined &&
                    (typeof preferences.styleOverride !== 'string' ||
                        !preferences.styleOverride.trim()))))
            throw new Error('Invalid narration preferences.');
        return this.createPerception({
            title: text(input.title, 'title'),
            modalities: modalities(input.modalities),
            taskDescription: text(input.narrationFocus, 'narration_focus'),
            interventionText: input.narrationStyle === undefined
                ? DEFAULT_NARRATION_STYLE
                : text(input.narrationStyle, 'narration_style'),
            ...(preferences ? { narrationPreferences: { ...preferences } } : {}),
            repeat: true,
            monitorMode: 'always',
        });
    }
    createTimer(input) {
        const now = Date.now();
        const title = text(input.title, 'title');
        this.assertUniqueTitle(title);
        const task = {
            taskId: this.newTaskId(),
            title,
            taskType: 'time_reminder',
            status: 'provisioning',
            monitorMode: 'event',
            repeat: false,
            generation: 1,
            createdAt: now,
            updatedAt: now,
            triggerCount: 0,
            failureCount: 0,
            durationSec: positiveNumber(input.durationSec, 'duration_sec'),
            reminderText: text(input.reminderText, 'reminder_text'),
        };
        this.tasks.set(task.taskId, task);
        this.onChange?.(copyTask(task));
        return copyTask(task);
    }
    update(input) {
        const existing = this.resolveOne(input);
        if (existing.status === 'provisioning' ||
            existing.status === 'delivering') {
            throw new Error(`Task is busy (${existing.status}); retry after it settles.`);
        }
        if (TERMINAL_STATUSES.has(existing.status)) {
            throw new Error('Only active Proactive tasks can be updated.');
        }
        const patchKeys = Object.keys(input).filter((key) => key !== 'targetTitle' && key !== 'targetTitleContains' && key !== 'all');
        if (patchKeys.length === 0) {
            throw new Error('update_proactive_task needs at least one changed field.');
        }
        const task = copyTask(existing);
        if (input.title !== undefined) {
            const title = text(input.title, 'title');
            this.assertUniqueTitle(title, task.taskId);
            task.title = title;
        }
        if (task.taskType === 'time_reminder') {
            this.rejectPresent(input, [
                'modalities',
                'condition',
                'triggerResponse',
                'narrationFocus',
                'narrationStyle',
                'repeat',
            ]);
            if (input.durationSec !== undefined) {
                task.durationSec = positiveNumber(input.durationSec, 'duration_sec');
            }
            if (input.reminderText !== undefined) {
                task.reminderText = text(input.reminderText, 'reminder_text');
            }
        }
        else if (task.monitorMode === 'event') {
            this.rejectPresent(input, [
                'narrationFocus',
                'narrationStyle',
                'durationSec',
                'reminderText',
            ]);
            if (input.modalities !== undefined) {
                task.modalities = modalities(input.modalities);
            }
            if (input.condition !== undefined) {
                task.taskDescription = text(input.condition, 'condition');
            }
            if (input.triggerResponse !== undefined) {
                task.interventionText = text(input.triggerResponse, 'trigger_response');
            }
            if (input.repeat !== undefined) {
                if (typeof input.repeat !== 'boolean') {
                    throw new Error('repeat must be a boolean.');
                }
                task.repeat = input.repeat;
            }
        }
        else {
            this.rejectPresent(input, [
                'condition',
                'triggerResponse',
                'repeat',
                'durationSec',
                'reminderText',
            ]);
            if (input.modalities !== undefined) {
                task.modalities = modalities(input.modalities);
            }
            if (input.narrationFocus !== undefined) {
                task.taskDescription = text(input.narrationFocus, 'narration_focus');
            }
            if (input.narrationStyle !== undefined) {
                task.interventionText = text(input.narrationStyle, 'narration_style');
                if (task.narrationPreferences)
                    task.narrationPreferences.styleOverride = task.interventionText;
            }
        }
        task.generation += 1;
        task.updatedAt = Date.now();
        task.failureCount = 0;
        task.error = undefined;
        this.tasks.set(task.taskId, task);
        this.onChange?.(copyTask(task));
        return copyTask(task);
    }
    cancel(selector) {
        if (selector.all === true) {
            if (selector.targetTitle !== undefined ||
                selector.targetTitleContains !== undefined) {
                throw new Error('all=true cannot be combined with a title selector.');
            }
            const cancelled = [];
            for (const task of this.tasks.values()) {
                if (TERMINAL_STATUSES.has(task.status))
                    continue;
                task.status = 'cancelled';
                task.updatedAt = Date.now();
                task.generation += 1;
                this.onChange?.(copyTask(task));
                cancelled.push(copyTask(task));
            }
            return cancelled;
        }
        if (selector.all !== undefined && selector.all !== false) {
            throw new Error('all must be a boolean.');
        }
        const task = this.resolveOne(selector);
        if (!TERMINAL_STATUSES.has(task.status)) {
            task.status = 'cancelled';
            task.updatedAt = Date.now();
            task.generation += 1;
            this.onChange?.(copyTask(task));
        }
        return [copyTask(task)];
    }
    listActive() {
        return [...this.tasks.values()]
            .filter((task) => !TERMINAL_STATUSES.has(task.status))
            .map((task) => copyTask(task));
    }
    cancelById(taskId) {
        const task = this.tasks.get(taskId);
        if (!task)
            return undefined;
        if (!TERMINAL_STATUSES.has(task.status)) {
            task.status = 'cancelled';
            task.updatedAt = Date.now();
            task.generation += 1;
            this.onChange?.(copyTask(task));
        }
        return copyTask(task);
    }
    get(taskId) {
        const task = this.tasks.get(taskId);
        return task ? copyTask(task) : undefined;
    }
    activePerceptionTasks() {
        return [...this.tasks.values()]
            .filter((task) => task.taskType === 'perception_monitor' &&
            !TERMINAL_STATUSES.has(task.status))
            .map((task) => copyTask(task));
    }
    mutate(taskId, generation, mutation) {
        const current = this.tasks.get(taskId);
        if (!current || current.generation !== generation)
            return undefined;
        const next = copyTask(current);
        if (!mutation(next))
            return undefined;
        next.updatedAt = Date.now();
        this.tasks.set(taskId, next);
        this.onChange?.(copyTask(next));
        return copyTask(next);
    }
    beginDelivery(taskId, generation, summary) {
        return this.mutate(taskId, generation, (task) => {
            if (task.status !== 'running')
                return false;
            if (!task.repeat)
                task.status = 'delivering';
            task.triggerCount += 1;
            task.failureCount = 0;
            if (summary !== undefined)
                task.lastSummary = summary;
            return true;
        });
    }
    completeDelivery(taskId, generation) {
        return this.mutate(taskId, generation, (task) => {
            if (task.status !== 'delivering' || task.repeat)
                return false;
            task.status = 'completed';
            return true;
        });
    }
    fail(taskId, generation, error) {
        return this.mutate(taskId, generation, (task) => {
            if (TERMINAL_STATUSES.has(task.status))
                return false;
            task.status = 'failed';
            task.error = error.slice(0, 300);
            return true;
        });
    }
    clear() {
        const active = this.listActive();
        this.tasks.clear();
        return active;
    }
    createPerception(input) {
        this.assertUniqueTitle(input.title);
        const now = Date.now();
        const task = {
            taskId: this.newTaskId(),
            title: input.title,
            taskType: 'perception_monitor',
            status: 'provisioning',
            monitorMode: input.monitorMode,
            repeat: input.repeat,
            modalities: input.modalities,
            taskDescription: input.taskDescription,
            interventionText: input.interventionText,
            ...(input.narrationPreferences
                ? { narrationPreferences: { ...input.narrationPreferences } }
                : {}),
            generation: 1,
            createdAt: now,
            updatedAt: now,
            triggerCount: 0,
            failureCount: 0,
        };
        this.tasks.set(task.taskId, task);
        this.onChange?.(copyTask(task));
        return copyTask(task);
    }
    resolveOne(selector) {
        const exact = selector.targetTitle === undefined
            ? undefined
            : text(selector.targetTitle, 'target_title');
        const partial = selector.targetTitleContains === undefined
            ? undefined
            : text(selector.targetTitleContains, 'target_title_contains');
        if (exact !== undefined && partial !== undefined) {
            throw new Error('Provide exactly one task title selector.');
        }
        if (selector.all !== undefined && selector.all !== false) {
            throw new Error('all is valid only for cancel_proactive_task.');
        }
        if (exact === undefined && partial === undefined) {
            throw new Error('No task title selector was provided.');
        }
        const needle = (exact ?? partial ?? '').toLocaleLowerCase();
        const matches = [...this.tasks.values()].filter((task) => {
            if (TERMINAL_STATUSES.has(task.status))
                return false;
            const title = task.title.toLocaleLowerCase();
            return exact !== undefined ? title === needle : title.includes(needle);
        });
        if (matches.length === 0)
            throw new Error('No matching active task.');
        if (matches.length > 1) {
            throw new Error('The title selector is ambiguous; use a unique title.');
        }
        return matches[0];
    }
    assertUniqueTitle(title, excludeTaskId) {
        const normalized = title.toLocaleLowerCase();
        for (const task of this.tasks.values()) {
            if (task.taskId !== excludeTaskId &&
                !TERMINAL_STATUSES.has(task.status) &&
                task.title.toLocaleLowerCase() === normalized) {
                throw new Error(`Active task title '${title}' already exists.`);
            }
        }
    }
    rejectPresent(input, fields) {
        const invalid = fields.filter((field) => input[field] !== undefined);
        if (invalid.length > 0) {
            throw new Error(`Fields do not apply to this task: ${invalid.join(', ')}.`);
        }
    }
    newTaskId() {
        return `task_${randomUUID().replaceAll('-', '').slice(0, 16)}`;
    }
}
