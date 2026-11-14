import { readFileSync } from 'node:fs';
import { isAbsolute } from 'node:path';
// Credentials are resolved server-side. Never serialize these resolved profiles.
export function resolveProviderRoles(input, legacy) {
    const roles = input === undefined ? {} : input;
    if (!roles || typeof roles !== 'object' || Array.isArray(roles))
        throw new Error('Invalid provider roles');
    const record = roles;
    const resolve = (name) => {
        const raw = record[name];
        if (raw === undefined)
            return { ...legacy, provider: 'qwen-realtime' };
        if (!raw || typeof raw !== 'object' || Array.isArray(raw))
            throw new Error(`Invalid provider role: ${name}`);
        const p = raw;
        if (!['qwen-realtime'].includes(String(p['provider'])))
            throw new Error(`Unsupported provider: ${name}`);
        if (typeof p['endpoint'] !== 'string' ||
            typeof p['model'] !== 'string' ||
            !p['model'].trim())
            throw new Error(`Missing endpoint/model: ${name}`);
        const url = new URL(p['endpoint']);
        if (!['https:', 'wss:'].includes(url.protocol) ||
            url.username ||
            url.password ||
            url.search ||
            url.hash)
            throw new Error(`Invalid endpoint: ${name}`);
        let apiKey;
        if (p['apiKeyFile'] !== undefined) {
            if (typeof p['apiKeyFile'] !== 'string' || !isAbsolute(p['apiKeyFile']))
                throw new Error(`apiKeyFile must be absolute: ${name}`);
            apiKey = readFileSync(p['apiKeyFile'], 'utf8').trim();
        }
        else if (p['provider'] === 'qwen-realtime' &&
            url.origin === new URL(legacy.endpoint).origin) {
            apiKey = legacy.apiKey;
        }
        if (!apiKey)
            throw new Error(`Missing provider credential: ${name}`);
        return {
            provider: p['provider'],
            endpoint: p['endpoint'],
            model: p['model'],
            apiKey,
            ...(typeof p['voice'] === 'string' ? { voice: p['voice'] } : {}),
        };
    };
    const ground = record['grounding'];
    if (ground &&
        (ground['provider'] !== 'rex-omni' ||
            typeof ground['enabled'] !== 'boolean'))
        throw new Error('Invalid grounding configuration');
    return {
        dialogue: resolve('dialogue'),
        visual_qa: resolve('visual_qa'),
        speech: resolve('speech'),
        grounding: { provider: 'rex-omni', enabled: ground?.['enabled'] === true },
    };
}
