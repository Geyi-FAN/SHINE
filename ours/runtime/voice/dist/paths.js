/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
import { homedir } from 'node:os';
import { join } from 'node:path';
export function defaultLiveDataDirectory(homeDirectory = homedir()) {
    return join(homeDirectory, '.qwen-live-harness');
}
/** Shared by init and daemon startup so desktop registration uses the same locator. */
export function resolveLiveDiscoveryDirectory(env = process.env, fileDirectory, homeDirectory = homedir()) {
    const configured = env['QWEN_LIVE_HARNESS_DISCOVERY_DIR']?.trim() ||
        (typeof fileDirectory === 'string' ? fileDirectory.trim() : '');
    if (!configured)
        return defaultLiveDataDirectory(homeDirectory);
    if (configured === '~')
        return homeDirectory;
    if (/^~[/\\]/u.test(configured))
        return join(homeDirectory, configured.slice(2));
    return configured;
}
/** Resolve only the Harness namespace; legacy data is never read or migrated. */
export function resolveLiveDataDirectory(env = process.env, homeDirectory = homedir()) {
    const configured = env['QWEN_LIVE_HARNESS_DATA_DIR']?.trim();
    if (!configured)
        return defaultLiveDataDirectory(homeDirectory);
    if (configured === '~')
        return homeDirectory;
    if (/^~[/\\]/u.test(configured))
        return join(homeDirectory, configured.slice(2));
    return configured;
}
