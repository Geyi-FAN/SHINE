/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
import { liveMessage, } from './i18n/messages.js';
/** Keep technical diagnostics stable while providing an owned UI message. */
export class ConfigurationError extends Error {
    displayMessage;
    constructor(diagnostic, key, params = {}) {
        super(diagnostic instanceof Error ? diagnostic.message : String(diagnostic), { cause: diagnostic });
        this.displayMessage = liveMessage(key, params);
    }
}
export function readConfigurationValue(key, read, params = {}) {
    try {
        return read();
    }
    catch (error) {
        if (error instanceof ConfigurationError)
            throw error;
        throw new ConfigurationError(error, key, params);
    }
}
export function configurationErrorMessage(error) {
    return error instanceof ConfigurationError
        ? error.displayMessage
        : liveMessage('config.invalid');
}
