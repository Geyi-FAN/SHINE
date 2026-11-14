/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
export const SUBAGENT_STATUSES = [
    'queued',
    'starting',
    'running',
    'monitoring',
    'waiting',
    'delivering',
    'completed',
    'failed',
    'cancelled',
    'interrupted',
];
export const SUBAGENT_FILTERS = [
    'all',
    'running',
    'completed',
    'needsAttention',
];
export const SUBAGENT_STOP_REASONS = [
    'stopping',
    'unsupported',
    'untracked',
    'ended',
];
export const MAX_SUBAGENTS_SNAPSHOT_BYTES = 240 * 1024;
export const MAX_SUBAGENT_TASKS = 32;
export const MAX_SUBAGENT_PERMISSIONS = 8;
export const MAX_SUBAGENTS_REQUEST_BYTES = 4 * 1024;
export const MAX_SUBAGENTS_CONTROL_BYTES = 1024 * 1024;
export const MAX_DISCOVERED_SESSIONS = 32;
export const MAX_INSTRUCTION_DELIVERIES = 100;
export const INSTRUCTION_DELIVERY_STATUSES = [
    'pending',
    'held',
    'delivered',
    'denied',
    'refused',
    'expired',
    'misaddressed',
    'dropped',
    'unknown',
    'failed',
];
export const MAX_SESSION_REPORTS = 100;
export const SESSION_REPORT_CATEGORIES = [
    'progress',
    'blocked',
    'result',
    'info',
];
export const SESSION_REPORT_ANNOUNCEMENTS = [
    'queued',
    'submitted',
    'speaking',
    'announced',
    'interrupted',
    'unspoken',
    'suppressed',
];
export const SUBAGENTS_CONTROL_ERROR_CODES = [
    'unsupported',
    'unavailable',
    'invalid_request',
    'not_found',
    'not_stoppable',
    'permission_unavailable',
    'action_failed',
    'stale_instance',
];
const record = (value) => Boolean(value) && typeof value === 'object' && !Array.isArray(value);
const text = (value, max) => typeof value === 'string' && value.length <= max;
const number = (value) => typeof value === 'number' && Number.isFinite(value) && value >= 0;
const integer = (value) => number(value) && Number.isSafeInteger(value);
const identifier = (value) => text(value, 128) && value.length > 0;
function fits(value, max) {
    try {
        return new TextEncoder().encode(JSON.stringify(value)).length <= max;
    }
    catch {
        return false;
    }
}
function validPermissions(value) {
    if (!Array.isArray(value) || value.length > MAX_SUBAGENT_PERMISSIONS)
        return false;
    const handles = new Set();
    for (const permission of value) {
        if (!record(permission) ||
            !identifier(permission['requestHandle']) ||
            handles.has(permission['requestHandle']) ||
            !text(permission['title'], 4096) ||
            (permission['titleTruncated'] !== undefined &&
                typeof permission['titleTruncated'] !== 'boolean') ||
            !Array.isArray(permission['choices']) ||
            permission['choices'].length > 3 ||
            (permission['details'] !== undefined &&
                !text(permission['details'], 8192)) ||
            (permission['alwaysScope'] !== undefined &&
                !text(permission['alwaysScope'], 1024)))
            return false;
        handles.add(permission['requestHandle']);
        for (const key of ['backend', 'sessionId'])
            if (permission[key] !== undefined && !text(permission[key], 256))
                return false;
        const decisions = new Set();
        for (const choice of permission['choices']) {
            if (!record(choice) ||
                (permission['titleTruncated'] === true &&
                    choice['decision'] === 'allow') ||
                (choice['decision'] !== 'allow' && choice['decision'] !== 'deny') ||
                decisions.has(`${choice['decision']}:${choice['scope'] ?? ''}`) ||
                (choice['scope'] !== undefined &&
                    choice['scope'] !== 'once' &&
                    choice['scope'] !== 'always'))
                return false;
            decisions.add(`${choice['decision']}:${choice['scope'] ?? ''}`);
        }
    }
    return true;
}
function validDiscoveredSessions(value) {
    if (!Array.isArray(value) || value.length > MAX_DISCOVERED_SESSIONS)
        return false;
    const ids = new Set();
    for (const session of value) {
        if (!record(session) ||
            !identifier(session['id']) ||
            ids.has(session['id']) ||
            !text(session['backend'], 256) ||
            !text(session['sessionId'], 256) ||
            !session['sessionId'] ||
            !text(session['title'], 240) ||
            (session['cwd'] !== undefined && !text(session['cwd'], 4096)) ||
            session['source'] !== 'terminal' ||
            session['status'] !== 'unknown' ||
            typeof session['readOnly'] !== 'boolean')
            return false;
        ids.add(session['id']);
    }
    return true;
}
function validInstructionDeliveries(value) {
    if (!Array.isArray(value) || value.length > MAX_INSTRUCTION_DELIVERIES)
        return false;
    const ids = new Set();
    const keys = [
        'id',
        'session',
        'backend',
        'status',
        'tracking',
        'createdAt',
        'updatedAt',
        'note',
    ];
    for (const delivery of value) {
        if (!record(delivery) ||
            !Object.keys(delivery).every((key) => keys.includes(key)) ||
            !identifier(delivery['id']) ||
            ids.has(delivery['id']) ||
            !identifier(delivery['session']) ||
            !text(delivery['backend'], 256) ||
            !INSTRUCTION_DELIVERY_STATUSES.includes(delivery['status']) ||
            typeof delivery['tracking'] !== 'boolean' ||
            !number(delivery['createdAt']) ||
            !number(delivery['updatedAt']) ||
            delivery['updatedAt'] < delivery['createdAt'] ||
            (delivery['note'] !== undefined && !text(delivery['note'], 1024)))
            return false;
        ids.add(delivery['id']);
    }
    return true;
}
function validSessionReports(value) {
    if (!Array.isArray(value) || value.length > MAX_SESSION_REPORTS)
        return false;
    const ids = new Set();
    const keys = [
        'id',
        'backend',
        'source',
        'sourceStatus',
        'session',
        'category',
        'text',
        'receivedAt',
        'updatedAt',
        'announcement',
        'note',
    ];
    for (const report of value) {
        if (!record(report) ||
            !Object.keys(report).every((key) => keys.includes(key)) ||
            !identifier(report['id']) ||
            ids.has(report['id']) ||
            !text(report['backend'], 256) ||
            !text(report['source'], 240) ||
            (report['sourceStatus'] !== 'matched' &&
                report['sourceStatus'] !== 'unconfirmed') ||
            (report['session'] !== undefined && !identifier(report['session'])) ||
            !SESSION_REPORT_CATEGORIES.includes(report['category']) ||
            !text(report['text'], 2000) ||
            !number(report['receivedAt']) ||
            !number(report['updatedAt']) ||
            report['updatedAt'] < report['receivedAt'] ||
            !SESSION_REPORT_ANNOUNCEMENTS.includes(report['announcement']) ||
            (report['note'] !== undefined && !text(report['note'], 1024)))
            return false;
        ids.add(report['id']);
    }
    return true;
}
function validTask(task) {
    if (!record(task) ||
        !identifier(task['id']) ||
        typeof task['kind'] !== 'string' ||
        !['harness', 'proactive', 'search', 'visual'].includes(task['kind']) ||
        !text(task['title'], 240) ||
        !SUBAGENT_STATUSES.includes(task['status']) ||
        !number(task['createdAt']) ||
        !number(task['updatedAt']) ||
        !text(task['request'], 4096) ||
        !text(task['activity'], 1024) ||
        !text(task['output'], 16384) ||
        (task['outputMessage'] !== undefined &&
            !text(task['outputMessage'], 512)) ||
        !Array.isArray(task['events']) ||
        task['events'].length > 24)
        return false;
    for (const key of ['backend', 'sessionId', 'source'])
        if (task[key] !== undefined && !text(task[key], 256))
            return false;
    for (const key of [
        'triggerCount',
        'pendingNotifications',
        'permissionsOmitted',
    ])
        if (task[key] !== undefined && !integer(task[key]))
            return false;
    if (task['remainingSec'] !== undefined && !number(task['remainingSec']))
        return false;
    for (const key of ['outputTruncated', 'canStop'])
        if (task[key] !== undefined && typeof task[key] !== 'boolean')
            return false;
    if (task['stopReason'] !== undefined &&
        !SUBAGENT_STOP_REASONS.includes(task['stopReason']))
        return false;
    if (task['permissions'] !== undefined &&
        !validPermissions(task['permissions']))
        return false;
    if (task['notification'] !== undefined &&
        (typeof task['notification'] !== 'string' ||
            !['queued', 'preparing', 'speaking', 'delivered', 'undelivered'].includes(task['notification'])))
        return false;
    return task['events'].every((event) => record(event) &&
        number(event['at']) &&
        typeof event['kind'] === 'string' &&
        [
            'status',
            'message',
            'plan',
            'tool',
            'observation',
            'notification',
        ].includes(event['kind']) &&
        text(event['text'], 1024));
}
export function parseSubagentsSnapshot(value) {
    if (!record(value) ||
        !integer(value['revision']) ||
        (value['deliveryRevision'] !== undefined &&
            !integer(value['deliveryRevision'])) ||
        (value['reportRevision'] !== undefined &&
            !integer(value['reportRevision'])) ||
        (value['pendingUnassignedPermissions'] !== undefined &&
            !integer(value['pendingUnassignedPermissions'])) ||
        !integer(value['omitted']) ||
        !record(value['counts']) ||
        !Array.isArray(value['tasks']) ||
        value['tasks'].length > MAX_SUBAGENT_TASKS)
        return undefined;
    const counts = value['counts'];
    if (![
        'running',
        'completed',
        'needsAttention',
        'failed',
        'cancelled',
        'interrupted',
    ].every((key) => integer(counts[key])))
        return undefined;
    const ids = new Set();
    for (const task of value['tasks']) {
        if (!validTask(task))
            return undefined;
        if (ids.has(task['id']))
            return undefined;
        ids.add(task['id']);
    }
    if (!fits(value, MAX_SUBAGENTS_SNAPSHOT_BYTES))
        return undefined;
    return value;
}
export function parseSubagentsControlRequest(value) {
    if (!record(value) || !fits(value, MAX_SUBAGENTS_REQUEST_BYTES))
        return undefined;
    const keys = Object.keys(value);
    if (value['action'] === 'list' &&
        keys.every((key) => ['action', 'offset', 'selectedId', 'filter'].includes(key)) &&
        (value['filter'] === undefined ||
            SUBAGENT_FILTERS.includes(value['filter'])) &&
        (value['offset'] === undefined || integer(value['offset'])) &&
        (value['selectedId'] === undefined || identifier(value['selectedId'])))
        return value;
    if (value['action'] === 'stop' &&
        keys.every((key) => ['action', 'taskId'].includes(key)) &&
        identifier(value['taskId']))
        return value;
    if (value['action'] === 'permission' &&
        keys.every((key) => ['action', 'requestHandle', 'decision', 'scope'].includes(key)) &&
        identifier(value['requestHandle']) &&
        (value['decision'] === 'allow' || value['decision'] === 'deny') &&
        (value['scope'] === undefined ||
            value['scope'] === 'once' ||
            (value['scope'] === 'always' && value['decision'] === 'allow')))
        return value;
    return undefined;
}
export function parseSubagentsControlResult(value) {
    if (!record(value) || !fits(value, MAX_SUBAGENTS_CONTROL_BYTES))
        return undefined;
    if (value['type'] === 'error')
        return SUBAGENTS_CONTROL_ERROR_CODES.includes(value['code'])
            ? value
            : undefined;
    if (value['type'] === 'outcome') {
        if ((value['scope'] !== undefined &&
            value['scope'] !== 'once' &&
            value['scope'] !== 'always') ||
            (value['message'] !== undefined && !text(value['message'], 1024)))
            return undefined;
        if ((['stopping', 'stopped', 'already_ended'].includes(value['outcome']) &&
            identifier(value['taskId'])) ||
            (['allowed', 'denied'].includes(value['outcome']) &&
                identifier(value['requestHandle'])))
            return value;
        return undefined;
    }
    if (value['type'] !== 'page' || !record(value['page']))
        return undefined;
    const page = value['page'];
    const snapshot = parseSubagentsSnapshot(page['snapshot']);
    if (!snapshot ||
        !integer(page['offset']) ||
        !integer(page['total']) ||
        (page['filter'] !== undefined &&
            !SUBAGENT_FILTERS.includes(page['filter'])) ||
        page['offset'] > page['total'] ||
        snapshot.tasks.length > page['total'] - page['offset'] ||
        (page['selected'] !== undefined && !validTask(page['selected'])) ||
        (page['unassignedPermissions'] !== undefined &&
            !validPermissions(page['unassignedPermissions'])) ||
        (page['unassignedPermissionsOmitted'] !== undefined &&
            !integer(page['unassignedPermissionsOmitted'])) ||
        (page['discoveredSessions'] !== undefined &&
            !validDiscoveredSessions(page['discoveredSessions'])) ||
        (page['discoveredSessionsOmitted'] !== undefined &&
            (!integer(page['discoveredSessionsOmitted']) ||
                page['discoveredSessions'] === undefined)) ||
        (page['instructionDeliveries'] !== undefined &&
            !validInstructionDeliveries(page['instructionDeliveries'])) ||
        (page['instructionDeliveriesOmitted'] !== undefined &&
            (!integer(page['instructionDeliveriesOmitted']) ||
                page['instructionDeliveries'] === undefined)) ||
        (page['sessionReports'] !== undefined &&
            !validSessionReports(page['sessionReports'])) ||
        (page['sessionReportsOmitted'] !== undefined &&
            (!integer(page['sessionReportsOmitted']) ||
                page['sessionReports'] === undefined)))
        return undefined;
    return value;
}
