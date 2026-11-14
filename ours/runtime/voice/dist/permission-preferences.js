/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
import { randomUUID } from 'node:crypto';
import { closeSync, constants, fstatSync, fsyncSync, lstatSync, openSync, readFileSync, renameSync, unlinkSync, writeFileSync, } from 'node:fs';
import { join } from 'node:path';
import { liveMessage } from './i18n/messages.js';
export function isPermissionMode(value) {
    return value === 'ask' || value === 'allow-all';
}
export function resolvePermissionMode(value) {
    if (value === undefined)
        return 'ask';
    if (!isPermissionMode(value))
        throw new Error(liveMessage('permissionMode.invalid'));
    return value;
}
/** Only an existing valid configuration may be changed by the settings UI. */
export function persistPermissionModePreference(dataDir, value) {
    if (!isPermissionMode(value))
        throw new Error(liveMessage('permissionMode.invalid'));
    const path = join(dataDir, 'config.json');
    let descriptor;
    try {
        descriptor = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
    }
    catch {
        throw new Error(liveMessage('permissionMode.configInvalid'));
    }
    let original;
    let before;
    let config;
    try {
        before = fstatSync(descriptor);
        if (!before.isFile() || before.nlink !== 1 || before.size > 4 * 1024 * 1024)
            throw new Error('Unsafe configuration');
        original = readFileSync(descriptor);
        const parsed = JSON.parse(original.toString('utf8').replace(/^\uFEFF/u, ''));
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed))
            throw new Error('Invalid configuration');
        config = parsed;
    }
    catch {
        throw new Error(liveMessage('permissionMode.configInvalid'));
    }
    finally {
        closeSync(descriptor);
    }
    const temporary = join(dataDir, `.permission-mode-${randomUUID()}.tmp`);
    let created = false;
    try {
        const fd = openSync(temporary, constants.O_WRONLY |
            constants.O_CREAT |
            constants.O_EXCL |
            constants.O_NOFOLLOW, 0o600);
        created = true;
        try {
            writeFileSync(fd, JSON.stringify({ ...config, permissionMode: value }, null, 2) + '\n');
            fsyncSync(fd);
        }
        finally {
            closeSync(fd);
        }
        const current = lstatSync(path);
        if (!current.isFile() ||
            current.isSymbolicLink() ||
            current.nlink !== 1 ||
            current.dev !== before.dev ||
            current.ino !== before.ino ||
            current.size !== before.size ||
            current.mtimeMs !== before.mtimeMs ||
            !readFileSync(path).equals(original))
            throw new Error(liveMessage('permissionMode.concurrentEdit'));
        renameSync(temporary, path);
    }
    catch (error) {
        if (error instanceof Error &&
            error.message.startsWith('qwen-live-harness-ui:'))
            throw error;
        throw new Error(liveMessage('permissionMode.saveFailed'));
    }
    finally {
        if (created)
            try {
                unlinkSync(temporary);
            }
            catch {
                /* Rename consumed the private file. */
            }
    }
    return value;
}
