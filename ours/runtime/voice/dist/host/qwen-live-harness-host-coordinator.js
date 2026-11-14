import {createWriteStream as qaStream} from 'node:fs';
const qaAudioFrameLog=process.env.VOICE_AUDIO_FRAME_LOG?qaStream(process.env.VOICE_AUDIO_FRAME_LOG,{flags:'w'}):null;
qaAudioFrameLog?.on('error',()=>console.error('T6 audio receive audit log unavailable'));
/**
 * @license
 * Copyright 2026 Qwen Team
 * SPDX-License-Identifier: Apache-2.0
 */
import { isVoiceId } from '../voice-catalog.js';
import { createHash, randomUUID, timingSafeEqual } from 'node:crypto';
import { WebSocket } from 'ws';
import { LIVE_HOST_BUNDLE_ID, LIVE_HOST_PROTOCOL_VERSION, LIVE_INPUT_AUDIO_EPOCH_BYTES, LIVE_OUTPUT_AUDIO_EPOCH_BYTES, LIVE_OUTPUT_AUDIO_HEADER_BYTES, } from './types.js';
import { isScreenDisplayId } from './screen-display.js';
import { LiveLogger } from '../logger.js';
import { emitRuntimeFailure, } from '../log/runtime-failure.js';
import { isLiveLanguage, liveMessage, liveText, } from '../i18n/messages.js';
const DEFAULT_HELLO_TIMEOUT_MS = 5_000;
const DEFAULT_HEARTBEAT_INTERVAL_MS = 5_000;
const DEFAULT_HEARTBEAT_TIMEOUT_MS = 15_000;
const DEFAULT_SHORTCUT_TIMEOUT_MS = 5_000;
// The frame cap must admit every message the per-field caps below allow. The
// Visual capture results combine a bounded JPEG with Appshot metadata.
const MAX_HOST_TEXT_BYTES = 512 * 1024;
const MAX_HOST_AUDIO_BYTES = 64 * 1024;
const MAX_HOST_VISUAL_IMAGE_BYTES = 190 * 1024;
const MAX_HOST_VISUAL_BASE64_LENGTH = Math.ceil(MAX_HOST_VISUAL_IMAGE_BYTES / 3) * 4;
const MAX_HOST_AUDIO_WIRE_BYTES = LIVE_INPUT_AUDIO_EPOCH_BYTES + MAX_HOST_AUDIO_BYTES;
const MAX_DAEMON_AUDIO_BYTES = 256 * 1024;
const MAX_SOCKET_BUFFERED_BYTES = 1024 * 1024;
const MAX_ID_LENGTH = 128;
const MAX_VERSION_LENGTH = 128;
const MAX_TRANSCRIPT_LENGTH = 8_192;
const MAX_STATUS_TEXT_LENGTH = 512;
const DEFAULT_SHORTCUT = 'Command+E';
const MAX_SHORTCUT_LENGTH = 128;
const MAX_APPSHOT_TEXT_LENGTH = 32_000;
const DEFAULT_VISUAL_CAPTURE_TIMEOUT_MS = 15_000;
const MAX_REPORTED_FAILURES = 128;
const DEFAULT_VISUAL_INPUT = {
    source: 'screen',
    mode: 'on-demand',
    fps: 1,
    liveWidth: 1280,
    liveHeight: 720,
};
export class LiveUnavailableError extends Error {
    status;
    code = 'live_unavailable';
    constructor(status) {
        super(status.message ?? 'Qwen Live Harness voice is unavailable.');
        this.status = status;
        this.name = 'LiveUnavailableError';
    }
}
function isObject(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
}
function isBoundedString(value, maxLength = MAX_ID_LENGTH) {
    return (typeof value === 'string' && value.length > 0 && value.length <= maxLength);
}
function isNonNegativeSafeInteger(value) {
    return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;
}
function isPermissionState(value) {
    return (value === 'granted' || value === 'denied' || value === 'not_determined');
}
function parseHello(value) {
    const protocolVersion = value['protocolVersion'];
    const permissions = value['permissions'];
    const selfChecks = value['selfChecks'];
    const cameraPermission = isObject(permissions)
        ? permissions['camera']
        : undefined;
    const legacyHelloWithoutCamera = protocolVersion !== LIVE_HOST_PROTOCOL_VERSION &&
        cameraPermission === undefined;
    if (value['type'] !== 'host.hello' ||
        (value['subagentsV1'] !== undefined && value['subagentsV1'] !== true) ||
        (value['displayCaptureV1'] !== undefined &&
            value['displayCaptureV1'] !== true) ||
        typeof protocolVersion !== 'number' ||
        !Number.isInteger(protocolVersion) ||
        !isBoundedString(value['hostVersion'], MAX_VERSION_LENGTH) ||
        !isBoundedString(value['bundleId']) ||
        !isBoundedString(value['instanceNonce']) ||
        !isObject(permissions) ||
        !isPermissionState(permissions['microphone']) ||
        (!isPermissionState(cameraPermission) && !legacyHelloWithoutCamera) ||
        !isPermissionState(permissions['accessibility']) ||
        !isPermissionState(permissions['screenRecording']) ||
        !isObject(selfChecks) ||
        typeof selfChecks['audioInput'] !== 'boolean' ||
        typeof selfChecks['audioOutput'] !== 'boolean' ||
        typeof selfChecks['globalShortcut'] !== 'boolean' ||
        typeof selfChecks['appshot'] !== 'boolean') {
        return undefined;
    }
    return {
        ...value,
        permissions: {
            ...permissions,
            camera: isPermissionState(cameraPermission)
                ? cameraPermission
                : 'not_determined',
        },
    };
}
function parseAction(value) {
    if (value['type'] !== 'host.action')
        return undefined;
    const action = value['action'];
    const epoch = value['epoch'];
    if (epoch !== undefined &&
        (typeof epoch !== 'number' || !Number.isSafeInteger(epoch) || epoch < 0)) {
        return undefined;
    }
    if (action === 'toggle' || action === 'new' || action === 'stop') {
        return {
            type: 'host.action',
            action,
            ...(epoch !== undefined ? { epoch } : {}),
        };
    }
    if (action === 'mute') {
        const inputMuted = value['inputMuted'];
        const outputMuted = value['outputMuted'];
        if ((inputMuted === undefined && outputMuted === undefined) ||
            (inputMuted !== undefined && typeof inputMuted !== 'boolean') ||
            (outputMuted !== undefined && typeof outputMuted !== 'boolean')) {
            return undefined;
        }
        return {
            type: 'host.action',
            action,
            ...(inputMuted !== undefined ? { inputMuted } : {}),
            ...(outputMuted !== undefined ? { outputMuted } : {}),
            ...(epoch !== undefined ? { epoch } : {}),
        };
    }
    return undefined;
}
function isBoundedVisualImage(image) {
    if (typeof image !== 'string' ||
        image.length === 0 ||
        image.length > MAX_HOST_VISUAL_BASE64_LENGTH ||
        image.length % 4 !== 0 ||
        !/^[A-Za-z0-9+/]*={0,2}$/.test(image)) {
        return false;
    }
    const jpeg = Buffer.from(image, 'base64');
    return (jpeg.byteLength >= 4 &&
        jpeg.byteLength <= MAX_HOST_VISUAL_IMAGE_BYTES &&
        jpeg[0] === 0xff &&
        jpeg[1] === 0xd8 &&
        jpeg[jpeg.byteLength - 2] === 0xff &&
        jpeg[jpeg.byteLength - 1] === 0xd9 &&
        jpeg.toString('base64') === image);
}
function isVisualSource(value) {
    return value === 'screen' || value === 'camera';
}
function validDisplayCaptureIdentity(value) {
    return ((value['screenScope'] === undefined && value['displayId'] === undefined) ||
        (value['source'] === 'screen' &&
            value['screenScope'] === 'display' &&
            value['displayId'] !== 'primary' &&
            isScreenDisplayId(value['displayId'])));
}
function parseVisualFrame(value) {
    const epoch = value['epoch'];
    const image = value['image'];
    if (value['type'] !== 'host.visual_frame' ||
        typeof epoch !== 'number' ||
        !Number.isSafeInteger(epoch) ||
        epoch < 0 ||
        !isVisualSource(value['source']) ||
        !validDisplayCaptureIdentity(value) ||
        !isBoundedVisualImage(image)) {
        return undefined;
    }
    return {
        type: 'host.visual_frame',
        epoch,
        source: value['source'],
        image,
        ...(value['screenScope'] === 'display'
            ? {
                screenScope: 'display',
                displayId: value['displayId'].toLowerCase(),
            }
            : {}),
    };
}
function parseVisualSettings(value) {
    const epoch = value['epoch'];
    const permissions = value['permissions'];
    if (value['type'] !== 'host.visual_settings' ||
        typeof epoch !== 'number' ||
        !Number.isSafeInteger(epoch) ||
        epoch < 0 ||
        !isVisualSource(value['source']) ||
        (value['mode'] !== 'on-demand' && value['mode'] !== 'live-feed') ||
        (value['screenDisplayId'] !== undefined &&
            !isScreenDisplayId(value['screenDisplayId'])) ||
        !isObject(permissions) ||
        !isPermissionState(permissions['camera']) ||
        !isPermissionState(permissions['accessibility']) ||
        !isPermissionState(permissions['screenRecording']) ||
        typeof value['appshot'] !== 'boolean') {
        return undefined;
    }
    return {
        type: 'host.visual_settings',
        epoch,
        source: value['source'],
        mode: value['mode'],
        ...(typeof value['screenDisplayId'] === 'string'
            ? { screenDisplayId: value['screenDisplayId'].toLowerCase() }
            : {}),
        permissions: {
            camera: permissions['camera'],
            accessibility: permissions['accessibility'],
            screenRecording: permissions['screenRecording'],
        },
        appshot: value['appshot'],
    };
}
function parseVisualCaptureResult(value) {
    const requestId = value['requestId'];
    if (value['type'] !== 'host.visual_capture_result' ||
        !isBoundedString(requestId)) {
        return undefined;
    }
    if (value['success'] === false && isBoundedString(value['error'], 1_024)) {
        return {
            type: 'host.visual_capture_result',
            requestId: requestId,
            success: false,
            error: value['error'],
        };
    }
    const source = value['source'];
    const width = value['width'];
    const height = value['height'];
    if (value['success'] !== true ||
        !isVisualSource(source) ||
        !isBoundedVisualImage(value['image']) ||
        !validDisplayCaptureIdentity(value) ||
        typeof width !== 'number' ||
        !Number.isSafeInteger(width) ||
        width <= 0 ||
        typeof height !== 'number' ||
        !Number.isSafeInteger(height) ||
        height <= 0 ||
        (value['screenshotPath'] !== undefined &&
            !isBoundedString(value['screenshotPath'], 4_096))) {
        return undefined;
    }
    if (source === 'camera') {
        return {
            type: 'host.visual_capture_result',
            requestId: requestId,
            success: true,
            source,
            image: value['image'],
            width,
            height,
            ...(value['screenshotPath']
                ? { screenshotPath: value['screenshotPath'] }
                : {}),
        };
    }
    if (!isBoundedString(value['appName'], 512) ||
        (value['windowTitle'] !== undefined &&
            !isBoundedString(value['windowTitle'], 2_048)) ||
        typeof value['accessibilityText'] !== 'string' ||
        value['accessibilityText'].length > MAX_APPSHOT_TEXT_LENGTH) {
        return undefined;
    }
    return {
        type: 'host.visual_capture_result',
        requestId: requestId,
        success: true,
        source,
        image: value['image'],
        width,
        height,
        appName: value['appName'],
        ...(value['screenScope'] === 'display'
            ? {
                screenScope: 'display',
                displayId: value['displayId'].toLowerCase(),
            }
            : {}),
        ...(value['windowTitle']
            ? { windowTitle: value['windowTitle'] }
            : {}),
        accessibilityText: value['accessibilityText'],
        ...(value['screenshotPath']
            ? { screenshotPath: value['screenshotPath'] }
            : {}),
    };
}
function parseMemoryAction(value) {
    if (!isBoundedString(value['requestId']) ||
        !isNonNegativeSafeInteger(value['epoch']))
        return undefined;
    const base = {
        type: 'host.memory_action',
        requestId: value['requestId'],
        epoch: value['epoch'],
    };
    switch (value['action']) {
        case 'set_enabled':
        case 'set_visual_enabled':
            return typeof value['enabled'] === 'boolean'
                ? { ...base, action: value['action'], enabled: value['enabled'] }
                : undefined;
        case 'select':
            return isBoundedString(value['libraryId'], 64)
                ? { ...base, action: 'select', libraryId: value['libraryId'] }
                : undefined;
        case 'create':
            return isBoundedString(value['name'], 160)
                ? { ...base, action: 'create', name: value['name'] }
                : undefined;
        case 'rename':
            return isBoundedString(value['libraryId'], 64) &&
                isBoundedString(value['name'], 160)
                ? {
                    ...base,
                    action: 'rename',
                    libraryId: value['libraryId'],
                    name: value['name'],
                }
                : undefined;
        case 'set_model':
            return isBoundedString(value['model'], 256)
                ? { ...base, action: 'set_model', model: value['model'] }
                : undefined;
        default:
            return undefined;
    }
}
function parseHostMessage(text) {
    let value;
    try {
        value = JSON.parse(text);
    }
    catch {
        return undefined;
    }
    if (!isObject(value))
        return undefined;
    if (value['type'] === 'host.hello')
        return parseHello(value);
    if (value['type'] === 'host.action')
        return parseAction(value);
    if (value['type'] === 'host.memory_action')
        return parseMemoryAction(value);
    if (value['type'] === 'host.permission_mode_action') {
        if (!isBoundedString(value['requestId']) ||
            String(value['requestId']).length > 128 ||
            !isNonNegativeSafeInteger(value['epoch']) ||
            !isBoundedString(value['daemonInstanceNonce']) ||
            String(value['daemonInstanceNonce']).length > 256 ||
            (value['mode'] !== 'ask' && value['mode'] !== 'allow-all'))
            return undefined;
        return {
            type: 'host.permission_mode_action',
            requestId: String(value['requestId']),
            epoch: value['epoch'],
            daemonInstanceNonce: String(value['daemonInstanceNonce']),
            mode: value['mode'],
        };
    }
    if (value['type'] === 'host.voice_action') {
        if (!isBoundedString(value['requestId']) ||
            String(value['requestId']).length > 128 ||
            !isNonNegativeSafeInteger(value['epoch']) ||
            !isBoundedString(value['daemonInstanceNonce']) ||
            String(value['daemonInstanceNonce']).length > 256 ||
            !isVoiceId(value['voice']))
            return undefined;
        return {
            type: 'host.voice_action',
            requestId: String(value['requestId']),
            epoch: value['epoch'],
            daemonInstanceNonce: String(value['daemonInstanceNonce']),
            voice: value['voice'],
        };
    }
    if (value['type'] === 'host.language_action') {
        if (!isBoundedString(value['requestId']) ||
            !isNonNegativeSafeInteger(value['epoch']) ||
            !isLiveLanguage(value['language']))
            return undefined;
        return {
            type: 'host.language_action',
            requestId: value['requestId'],
            epoch: value['epoch'],
            language: value['language'],
        };
    }
    if (value['type'] === 'host.visual_frame')
        return parseVisualFrame(value);
    if (value['type'] === 'host.visual_settings')
        return parseVisualSettings(value);
    if (value['type'] === 'host.visual_capture_result')
        return parseVisualCaptureResult(value);
    if (value['type'] === 'host.pong' && isBoundedString(value['pingId'])) {
        return { type: 'host.pong', pingId: value['pingId'] };
    }
    if (value['type'] === 'host.shortcut_result') {
        const requestId = value['requestId'];
        const shortcut = value['shortcut'];
        const success = value['success'];
        const error = value['error'];
        if (isBoundedString(requestId) &&
            typeof shortcut === 'string' &&
            shortcut.length <= MAX_SHORTCUT_LENGTH &&
            typeof success === 'boolean' &&
            (error === undefined ||
                (typeof error === 'string' && error.length <= 1_024))) {
            return {
                type: 'host.shortcut_result',
                requestId: requestId,
                shortcut,
                success,
                ...(error ? { error } : {}),
            };
        }
    }
    if (value['type'] === 'host.playback_started' &&
        isNonNegativeSafeInteger(value['epoch']) &&
        isNonNegativeSafeInteger(value['outputId'])) {
        return {
            type: 'host.playback_started',
            epoch: value['epoch'],
            outputId: value['outputId'],
        };
    }
    if (value['type'] === 'host.playback_completed' &&
        isNonNegativeSafeInteger(value['epoch']) &&
        isNonNegativeSafeInteger(value['outputId'])) {
        return {
            type: 'host.playback_completed',
            epoch: value['epoch'],
            outputId: value['outputId'],
        };
    }
    return undefined;
}
function permissionRequirement(value) {
    if (value === 'granted')
        return 'ready';
    if (value === 'denied')
        return 'denied';
    return 'missing';
}
function projectStatusForHost(status) {
    return {
        v: status.v,
        available: status.available,
        state: status.state,
        shortcut: status.shortcut,
        ...(status.blocker ? { blocker: status.blocker } : {}),
        ...(status.message ? { message: status.message } : {}),
        ...(status.callId ? { callId: status.callId } : {}),
        ...(status.inputMuted !== undefined
            ? { inputMuted: status.inputMuted }
            : {}),
        ...(status.outputMuted !== undefined
            ? { outputMuted: status.outputMuted }
            : {}),
        ...(status.transcript ? { transcript: status.transcript } : {}),
        ...(status.caption ? { caption: status.caption } : {}),
        ...(status.statusText ? { statusText: status.statusText } : {}),
        ...(status.pendingPermission
            ? { pendingPermission: { ...status.pendingPermission } }
            : {}),
        ...(status.requirements
            ? { requirements: { ...status.requirements } }
            : {}),
        ...(status.host ? { host: { ...status.host } } : {}),
    };
}
export class LiveHostCoordinator {
    options;
    daemonInstanceNonce;
    now;
    helloTimeoutMs;
    heartbeatIntervalMs;
    heartbeatTimeoutMs;
    visualCaptureTimeoutMs;
    logger;
    visualInput;
    shortcut;
    handlers;
    host;
    hadConnectedHost = false;
    lastHostFailure;
    providerOverride;
    appshotReadiness = {
        state: 'unavailable',
        message: liveText('en', 'runtime.appshotUnchecked'),
    };
    call;
    pendingStartMode;
    deactivating = false;
    nextEpoch = 0;
    nextOutputId = 0;
    writableOutputId;
    outputAudio = new Map();
    playbackStartedNotified = false;
    perOutputStarted = new Set();
    inputMuted = false;
    outputMuted = false;
    lastCallError;
    pendingVisualCaptures = new Map();
    pendingShortcut;
    inactiveWaiters = new Set();
    reportedFailures = new Set();
    hostGeneration = 0;
    constructor(options) {
        this.options = options;
        this.daemonInstanceNonce = options.daemonInstanceNonce ?? randomUUID();
        this.handlers = options.handlers ?? {};
        this.now = options.now ?? Date.now;
        this.helloTimeoutMs = options.helloTimeoutMs ?? DEFAULT_HELLO_TIMEOUT_MS;
        this.heartbeatIntervalMs =
            options.heartbeatIntervalMs ?? DEFAULT_HEARTBEAT_INTERVAL_MS;
        this.heartbeatTimeoutMs =
            options.heartbeatTimeoutMs ?? DEFAULT_HEARTBEAT_TIMEOUT_MS;
        this.visualCaptureTimeoutMs =
            options.visualCaptureTimeoutMs ?? DEFAULT_VISUAL_CAPTURE_TIMEOUT_MS;
        this.visualInput = {
            ...(options.visualInput ?? DEFAULT_VISUAL_INPUT),
        };
        this.logger = options.logger ?? new LiveLogger();
        this.appshotReadiness.message = this.uiText('runtime.appshotUnchecked');
        const shortcut = options.shortcut?.trim();
        this.shortcut =
            shortcut && shortcut.length <= MAX_SHORTCUT_LENGTH
                ? shortcut
                : DEFAULT_SHORTCUT;
    }
    setHandlers(handlers) {
        this.handlers = handlers;
    }
    setConfiguredShortcut(shortcut) {
        const normalized = shortcut.trim();
        if (normalized.length > MAX_SHORTCUT_LENGTH) {
            throw new Error('The Qwen Live Harness shortcut is too long.');
        }
        this.shortcut = normalized;
        this.broadcastState();
        return this.getStatus();
    }
    async deactivate() {
        // Host-initiated starts must not re-arm a call while the stop drains:
        // state broadcasts during 'stopping' still carry the stopping call's
        // epoch, so a host.action would otherwise pass the epoch gate.
        this.deactivating = true;
        this.pendingStartMode = undefined;
        if (this.call) {
            const stopped = new Promise((resolve) => {
                this.inactiveWaiters.add(resolve);
            });
            this.stop();
            await stopped;
        }
        if (!this.host)
            return;
        const lease = this.host;
        lease.expectedClose = true;
        if (lease.socket.readyState === WebSocket.OPEN) {
            lease.socket.close(1001, 'Qwen Live Harness voice disabled.');
        }
        this.detachHost(lease, 'host_disconnected');
    }
    attachHost(socket, daemonNonce) {
        const expectedNonce = Buffer.from(this.daemonInstanceNonce);
        const presentedNonce = Buffer.from(daemonNonce ?? '');
        if (expectedNonce.byteLength !== presentedNonce.byteLength ||
            !timingSafeEqual(expectedNonce, presentedNonce)) {
            this.debug('host.rejected', { reason: 'daemon_nonce' });
            this.reportFailure({
                code: 'host_identity_rejected',
                stage: 'host_handshake',
                impact: 'operation',
                message: 'Host connection rejected because its daemon identity did not match.',
                closeCode: 4003,
            });
            socket.close(4003, 'Invalid daemon instance nonce.');
            return;
        }
        if (this.host && this.isLeaseHealthy(this.host)) {
            this.debug('host.rejected', { reason: 'lease_active' });
            this.reportFailure({
                code: 'host_lease_active',
                stage: 'host_handshake',
                impact: 'operation',
                message: 'Another Host already owns the active connection.',
                closeCode: 4009,
            });
            socket.close(4009, 'A Qwen Live Harness Host is already connected.');
            return;
        }
        if (this.host)
            this.disconnectHost(this.host, 4008, 'Host lease expired.', 'host_lease_expired');
        // Only an accepted lease revives Qwen Live Harness voice: a fresh host connection is
        // the re-activation signal that ends the deactivating window.
        this.deactivating = false;
        this.hostGeneration += 1;
        const lease = {
            socket,
            lastPongAt: this.now(),
            helloTimer: setTimeout(() => {
                if (this.host === lease && !lease.hello) {
                    this.reportHostFailure(lease, 'host_hello_timeout', 'host_handshake', 'Host did not send its hello before the handshake deadline.', 4000);
                    socket.close(4000, 'Host hello timeout.');
                    this.detachHost(lease, 'host_disconnected');
                }
            }, this.helloTimeoutMs),
        };
        lease.helloTimer.unref?.();
        this.host = lease;
        this.debug('host.connected', {});
        socket.on('message', (data, isBinary) => {
            if (this.host !== lease)
                return;
            if (isBinary)
                this.handleAudioFrame(lease, data);
            else
                this.handleTextFrame(lease, data);
        });
        socket.on('close', (code = 0, reason = Buffer.alloc(0)) => {
            this.debug('host.closed', {
                code,
                reason: reason.toString('utf8').slice(0, 256),
            });
            if (this.host === lease) {
                this.reportHostFailure(lease, 'host_disconnected', 'host_transport', 'The Host connection closed unexpectedly.', code);
                this.detachHost(lease, 'host_disconnected');
            }
        });
        socket.on('error', (error) => {
            this.debug('host.error', { message: error.message.slice(0, 256) });
            if (this.host === lease) {
                this.reportHostFailure(lease, 'host_socket_error', 'host_transport', 'The Host connection reported a transport error.');
                this.detachHost(lease, 'host_disconnected');
            }
        });
    }
    getStatus() {
        return this.buildStatus(true);
    }
    buildStatus(stopOnReadinessLoss) {
        const provider = this.readProviderReadiness();
        const appshot = this.appshotReadiness;
        const hello = this.host?.hello;
        const requirements = {
            host: hello
                ? 'ready'
                : this.lastHostFailure === 'host_version'
                    ? 'unavailable'
                    : this.hadConnectedHost
                        ? 'unavailable'
                        : 'missing',
            provider: provider.state === 'ready'
                ? 'ready'
                : provider.state === 'checking'
                    ? 'checking'
                    : 'unavailable',
        };
        if (hello) {
            requirements.microphone = permissionRequirement(hello.permissions.microphone);
            if (this.visualInput.source === 'camera') {
                requirements.camera = permissionRequirement(hello.permissions.camera);
            }
            else {
                requirements.screenRecording = permissionRequirement(hello.permissions.screenRecording);
            }
            requirements.audioInput = hello.selfChecks.audioInput
                ? 'ready'
                : 'unavailable';
            requirements.audioOutput = hello.selfChecks.audioOutput
                ? 'ready'
                : 'unavailable';
            requirements.globalShortcut = hello.selfChecks.globalShortcut
                ? 'ready'
                : 'unavailable';
            if (this.visualInput.source === 'screen' &&
                this.visualInput.mode === 'on-demand') {
                requirements.appshot = hello.selfChecks.appshot
                    ? appshot.state
                    : 'unavailable';
            }
        }
        else if (this.visualInput.source === 'screen' &&
            this.visualInput.mode === 'on-demand' &&
            appshot.state !== 'ready') {
            requirements.appshot = appshot.state;
        }
        const blocker = this.resolveBlocker(provider, appshot, hello);
        const providerChecking = provider.state === 'checking';
        const available = !providerChecking && blocker === undefined;
        const preserveCheckingCall = providerChecking && blocker === undefined && this.call !== undefined;
        if (!available &&
            this.call &&
            stopOnReadinessLoss &&
            !preserveCheckingCall) {
            if (this.call.state !== 'stopping') {
                this.reportFailure({
                    code: blocker ?? 'readiness_lost',
                    stage: 'host_readiness',
                    impact: 'call',
                    message: 'An active call lost a required Host or provider capability.',
                });
            }
            this.stopForReadinessLoss();
        }
        const active = this.call;
        return {
            v: 1,
            available,
            shortcut: this.shortcut,
            state: preserveCheckingCall
                ? (active?.state ?? 'starting')
                : available
                    ? (active?.state ?? (this.lastCallError ? 'error' : 'idle'))
                    : 'unavailable',
            ...(blocker ? { blocker } : {}),
            ...(blocker
                ? { message: this.blockerMessage(blocker, provider, appshot, hello) }
                : this.lastCallError
                    ? { message: this.lastCallError }
                    : {}),
            ...(active ? { callId: active.callId } : {}),
            inputMuted: this.inputMuted,
            outputMuted: this.outputMuted,
            ...(active?.transcript ? { transcript: active.transcript } : {}),
            ...(active?.caption ? { caption: active.caption } : {}),
            ...(active?.statusText ? { statusText: active.statusText } : {}),
            ...(active?.pendingPermission && active.coordinator?.workspaceId
                ? {
                    pendingPermission: {
                        workspaceId: active.coordinator.workspaceId,
                        sessionId: active.coordinator.sessionId,
                    },
                }
                : {}),
            requirements,
            ...(hello
                ? {
                    host: {
                        version: hello.hostVersion,
                        protocolVersion: hello.protocolVersion,
                    },
                }
                : {}),
        };
    }
    start(mode) {
        if (this.options.getVoice?.().creating)
            throw new Error(liveMessage('voice.creating'));
        const status = this.getStatus();
        if (!status.available)
            throw new LiveUnavailableError(status);
        if (mode === 'resume' && this.call) {
            return {
                epoch: this.call.epoch,
                callId: this.call.callId,
                status,
            };
        }
        if (this.call) {
            const replacedCall = this.call;
            this.pendingStartMode = 'new';
            this.beginCallStop(replacedCall);
            const reportedCall = this.call ?? replacedCall;
            return {
                epoch: reportedCall.epoch,
                callId: reportedCall.callId,
                status: this.getStatus(),
            };
        }
        return this.startCall(mode);
    }
    startCall(mode) {
        const call = {
            epoch: ++this.nextEpoch,
            callId: randomUUID(),
            mode,
            state: 'starting',
            pendingPermission: false,
            workers: [],
        };
        this.call = call;
        this.debug('call.start', { epoch: call.epoch, mode });
        this.lastCallError = undefined;
        this.broadcastState();
        try {
            void Promise.resolve(this.handlers.onStart?.({
                epoch: call.epoch,
                callId: call.callId,
                mode,
                visualInput: { ...this.visualInput },
            })).catch(() => {
                this.failCall(call.epoch, this.uiText('runtime.startFailed'), {
                    code: 'call_start_failed',
                    stage: 'call_start',
                });
            });
        }
        catch {
            this.failCall(call.epoch, this.uiText('runtime.startFailed'), {
                code: 'call_start_failed',
                stage: 'call_start',
            });
        }
        return { epoch: call.epoch, callId: call.callId, status: this.getStatus() };
    }
    stop() {
        this.pendingStartMode = undefined;
        if (this.call)
            this.beginCallStop(this.call);
        return this.getStatus();
    }
    setMute(update) {
        if (update.inputMuted !== undefined &&
            update.inputMuted !== this.inputMuted) {
            this.inputMuted = update.inputMuted;
            this.debug('audio.input_mute_changed', {
                epoch: this.call?.epoch,
                inputMuted: this.inputMuted,
            });
            if (this.call && this.call.state !== 'stopping') {
                this.handlers.onInputMuteChanged?.({
                    epoch: this.call.epoch,
                    inputMuted: this.inputMuted,
                });
            }
        }
        if (update.outputMuted !== undefined) {
            const becameMuted = update.outputMuted && !this.outputMuted;
            this.outputMuted = update.outputMuted;
            if (becameMuted && this.call) {
                this.clearOutput(this.call.epoch);
                this.handlers.onOutputMuted?.({ epoch: this.call.epoch });
            }
        }
        this.broadcastState();
        return this.getStatus();
    }
    setShortcut(shortcut) {
        const normalized = shortcut.trim();
        if (normalized.length > MAX_SHORTCUT_LENGTH) {
            return Promise.reject(new Error('The Qwen Live Harness shortcut is too long.'));
        }
        if (normalized === this.shortcut) {
            return Promise.resolve(this.getStatus());
        }
        if (this.pendingShortcut) {
            return Promise.reject(new Error('Another Qwen Live Harness shortcut update is already in progress.'));
        }
        const host = this.host;
        if (!host?.hello || !this.isLeaseHealthy(host)) {
            return Promise.reject(new Error('Qwen Live Harness Host must be connected to change the shortcut.'));
        }
        const requestId = randomUUID();
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.rejectPendingShortcut(new Error('Qwen Live Harness Host did not confirm the shortcut change.'));
            }, DEFAULT_SHORTCUT_TIMEOUT_MS);
            timer.unref?.();
            this.pendingShortcut = {
                requestId,
                shortcut: normalized,
                timer,
                resolve,
                reject,
            };
            if (!this.sendHost({
                type: 'host.set_shortcut',
                requestId,
                shortcut: normalized,
            })) {
                this.rejectPendingShortcut(new Error('Qwen Live Harness Host is unavailable for shortcut changes.'));
            }
        });
    }
    setCallState(epoch, state) {
        if (!this.call || this.call.epoch !== epoch)
            return false;
        if (this.call.state === state)
            return true;
        this.call.state = state;
        this.broadcastState();
        return true;
    }
    setCoordinator(epoch, locator) {
        if (!this.call || this.call.epoch !== epoch)
            return false;
        this.call.coordinator = locator;
        this.broadcastState();
        return true;
    }
    setPendingPermission(epoch, pending) {
        if (!this.call || this.call.epoch !== epoch)
            return false;
        if (this.call.pendingPermission === pending)
            return true;
        this.call.pendingPermission = pending;
        this.broadcastState();
        return true;
    }
    setTranscript(epoch, transcript) {
        if (!this.call || this.call.epoch !== epoch)
            return false;
        const truncated = transcript.slice(0, MAX_TRANSCRIPT_LENGTH);
        if (this.call.transcript === truncated)
            return true;
        this.call.transcript = truncated;
        this.broadcastState();
        return true;
    }
    setCaption(epoch, caption) {
        if (!this.call || this.call.epoch !== epoch)
            return false;
        const truncated = caption.slice(0, MAX_TRANSCRIPT_LENGTH);
        if (this.call.caption === truncated)
            return true;
        this.call.caption = truncated || undefined;
        this.broadcastState();
        return true;
    }
    setStatusText(epoch, statusText) {
        if (!this.call || this.call.epoch !== epoch)
            return false;
        const truncated = statusText?.trim().slice(0, MAX_STATUS_TEXT_LENGTH);
        if (this.call.statusText === truncated)
            return true;
        this.call.statusText = truncated || undefined;
        this.broadcastState();
        return true;
    }
    setWorkers(epoch, workers) {
        if (!this.call || this.call.epoch !== epoch)
            return false;
        this.call.workers = [...workers];
        this.broadcastState();
        return true;
    }
    isActiveSession(sessionId) {
        const call = this.call;
        return (call !== undefined &&
            (call.coordinator?.sessionId === sessionId ||
                call.workers.some((worker) => worker.sessionId === sessionId)));
    }
    captureVisualContext(callerSessionId, options = {}) {
        const call = this.call;
        const host = this.host;
        const display = this.visualInput.source === 'screen';
        if (display && !host?.hello?.displayCaptureV1)
            return Promise.reject(new Error(this.uiText('runtime.displayCaptureUnsupported')));
        const sourceReady = this.visualInput.source === 'camera'
            ? host?.hello?.permissions.camera === 'granted'
            : host?.hello?.permissions.screenRecording === 'granted';
        if (!call ||
            call.coordinator?.sessionId !== callerSessionId ||
            !host?.hello ||
            !this.isLeaseHealthy(host) ||
            this.visualInput.mode !== 'on-demand' ||
            !sourceReady) {
            return Promise.reject(new Error('On Demand capture is available only to the active Qwen Live Harness session with a ready selected source.'));
        }
        const requestId = randomUUID();
        const source = this.visualInput.source;
        const screenDisplayId = display
            ? (this.visualInput.screenDisplayId ?? 'primary')
            : undefined;
        // Background Monitor/Memory callers explicitly request the bounded
        // display feed size. The Appshot tool keeps its own snapshot resolution.
        const backgroundDisplay = display && options.screenScope === 'display';
        const snapshotWidth = backgroundDisplay
            ? this.visualInput.liveWidth
            : source === 'camera'
                ? this.visualInput.cameraSnapshotWidth
                : this.visualInput.snapshotWidth;
        const snapshotHeight = backgroundDisplay
            ? this.visualInput.liveHeight
            : source === 'camera'
                ? this.visualInput.cameraSnapshotHeight
                : this.visualInput.snapshotHeight;
        this.debug('visual.capture_requested', {
            epoch: call.epoch,
            source,
            ...(screenDisplayId ? { screenScope: 'display', screenDisplayId } : {}),
        });
        return new Promise((resolve, reject) => {
            const timer = setTimeout(() => {
                this.pendingVisualCaptures.delete(requestId);
                this.reportFailure({
                    code: 'visual_capture_timeout',
                    stage: 'visual_capture',
                    impact: 'operation',
                    message: 'Host visual capture did not complete before its deadline.',
                    epoch: call.epoch,
                    callId: call.callId,
                });
                this.debug('visual.capture_failed', {
                    epoch: call.epoch,
                    source,
                    reason: 'timeout',
                });
                reject(new Error('Qwen Live Harness Host On Demand capture timed out.'));
            }, this.visualCaptureTimeoutMs);
            timer.unref?.();
            this.pendingVisualCaptures.set(requestId, {
                epoch: call.epoch,
                source,
                ...(screenDisplayId ? { screenDisplayId } : {}),
                persistAsset: options.persistAsset !== false,
                timer,
                resolve,
                reject,
            });
            if (!this.sendHost({
                type: 'host.capture_visual',
                requestId,
                epoch: call.epoch,
                source,
                ...(screenDisplayId
                    ? { screenScope: 'display', screenDisplayId }
                    : {}),
                ...(snapshotWidth !== undefined ? { snapshotWidth } : {}),
                ...(snapshotHeight !== undefined ? { snapshotHeight } : {}),
                ...(options.persistAsset !== undefined
                    ? { persistAsset: options.persistAsset }
                    : {}),
            })) {
                this.rejectPendingVisualCapture(requestId, new Error('Qwen Live Harness Host is unavailable for On Demand capture.'));
            }
        });
    }
    setProviderReachability(readiness) {
        this.providerOverride = readiness;
        const status = this.getStatus();
        this.sendState(status);
    }
    setAppshotReadiness(readiness) {
        this.appshotReadiness = { ...readiness };
        this.sendState(this.getStatus());
    }
    failCall(epoch, message = this.uiText('runtime.callFailed'), diagnostic) {
        if (!this.call ||
            this.call.epoch !== epoch ||
            this.call.state === 'stopping') {
            return false;
        }
        this.debug('call.failed', { epoch, message });
        this.reportFailure({
            code: diagnostic?.code ?? 'call_failed',
            stage: diagnostic?.stage ?? 'call',
            impact: 'call',
            message,
            epoch,
        });
        const call = this.call;
        this.pendingStartMode = undefined;
        this.lastCallError = message;
        this.beginCallStop(call);
        return true;
    }
    sendOutputAudio(epoch, pcm16) {
        if (!this.call ||
            this.call.epoch !== epoch ||
            pcm16.byteLength === 0 ||
            pcm16.byteLength > MAX_DAEMON_AUDIO_BYTES ||
            pcm16.byteLength % 2 !== 0) {
            return false;
        }
        if (this.outputMuted)
            return false;
        const socket = this.host?.socket;
        if (!socket ||
            socket.readyState !== WebSocket.OPEN ||
            socket.bufferedAmount > MAX_SOCKET_BUFFERED_BYTES) {
            if (this.call.state !== 'stopping') {
                this.reportFailure({
                    code: socket?.readyState === WebSocket.OPEN
                        ? 'audio_output_backpressure'
                        : 'audio_output_unavailable',
                    stage: 'audio_output',
                    impact: 'response',
                    message: 'Response audio could not be delivered to the Host.',
                    epoch,
                });
            }
            return false;
        }
        const outputId = this.writableOutputId ?? this.allocateOutputId();
        const output = this.outputAudio.get(outputId) ?? {
            finished: false,
            drained: false,
            samples: 0,
        };
        const frame = Buffer.allocUnsafe(LIVE_OUTPUT_AUDIO_HEADER_BYTES + pcm16.byteLength);
        frame.writeBigUInt64BE(BigInt(epoch), 0);
        frame.writeBigUInt64BE(BigInt(outputId), LIVE_OUTPUT_AUDIO_EPOCH_BYTES);
        frame.set(pcm16, LIVE_OUTPUT_AUDIO_HEADER_BYTES);
        try {
            socket.send(frame, { binary: true });
        }
        catch (error) {
            this.reportFailure({
                code: 'audio_output_send_failed',
                stage: 'audio_output',
                impact: 'response',
                message: 'Sending response audio to the Host failed.',
                epoch,
            });
            throw error;
        }
        this.writableOutputId = outputId;
        if (!this.supportsOutputAudioEndMarker()) {
            output.finished = false;
            output.drained = false;
        }
        output.samples += pcm16.byteLength / 2;
        this.outputAudio.set(outputId, output);
        this.debug('audio.output_sent', {
            epoch,
            outputId,
            bytes: pcm16.byteLength,
            socketBufferedBytes: socket.bufferedAmount,
        });
        return true;
    }
    finishOutputAudio(epoch) {
        const call = this.call;
        const outputId = this.writableOutputId;
        if (!call || call.epoch !== epoch || outputId === undefined) {
            return;
        }
        const output = this.outputAudio.get(outputId);
        if (!output || output.finished)
            return;
        output.finished = true;
        if (this.supportsOutputAudioEndMarker()) {
            if (!this.sendHost({
                type: 'host.output_audio_finished',
                epoch,
                outputId,
                expectedSamples: output.samples,
                sampleRate: 24000,
            })) {
                output.finished = false;
                if (call.state !== 'stopping') {
                    this.reportFailure({
                        code: 'audio_output_end_marker_failed',
                        stage: 'audio_output',
                        impact: 'response',
                        message: 'The Host did not accept the response audio end marker.',
                        epoch: call.epoch,
                        callId: call.callId,
                    });
                }
            }
            else {
                this.writableOutputId = undefined;
            }
            return;
        }
        if (output.drained)
            this.completeOutputAudio(call, outputId);
    }
    tagOutputAudio(epoch, metadata) {
        const outputId = this.writableOutputId;
        const output = outputId === undefined ? undefined : this.outputAudio.get(outputId);
        if (this.call?.epoch !== epoch || outputId === undefined || !output)
            return;
        if (!this.sendHost({ type: 'host.output_audio_receipt', epoch, outputId, expectedSamples: output.samples, sampleRate: 24000, ...metadata }))
            return;
        return outputId;
    }
    isOutputMuted() {
        return this.outputMuted;
    }
    isInputMuted() {
        return this.inputMuted;
    }
    clearOutput(epoch) {
        if (this.call && this.call.epoch !== epoch)
            return;
        this.resetOutputAudio();
        this.debug('audio.output_cleared', { epoch });
        this.sendHost({ type: 'host.clear_output', epoch });
    }
    dispose() {
        this.pendingStartMode = undefined;
        if (this.host)
            this.host.expectedClose = true;
        if (this.call)
            this.finishCall(this.call);
        if (this.host) {
            const lease = this.host;
            this.host = undefined;
            this.clearLeaseTimers(lease);
            if (lease.socket.readyState === WebSocket.OPEN) {
                lease.socket.close(1001, 'Daemon shutting down.');
            }
        }
        this.rejectPendingVisualCaptures(new Error('Qwen Live Harness voice is shutting down.'));
        this.rejectPendingShortcut(new Error('Qwen Live Harness voice is shutting down.'));
        this.notifyInactive();
    }
    readProviderReadiness() {
        if (this.providerOverride)
            return this.providerOverride;
        try {
            return this.options.getProviderReadiness();
        }
        catch {
            return {
                state: 'unavailable',
                blocker: 'provider_config',
                message: this.uiText('runtime.providerConfig'),
            };
        }
    }
    resolveBlocker(provider, appshot, hello) {
        if (provider.state === 'unavailable') {
            return provider.blocker ?? 'provider_config';
        }
        if (!hello) {
            if (this.lastHostFailure === 'host_version')
                return 'host_version';
            return this.hadConnectedHost ? 'host_disconnected' : 'host_missing';
        }
        if (hello.permissions.microphone !== 'granted') {
            return 'microphone_permission';
        }
        if (this.visualInput.source === 'camera' &&
            hello.permissions.camera !== 'granted')
            return 'camera_permission';
        if (this.visualInput.source === 'screen' && !hello.displayCaptureV1)
            return 'host_version';
        if (this.visualInput.source === 'screen' &&
            hello.permissions.screenRecording !== 'granted')
            return 'screen_recording_permission';
        if (!hello.selfChecks.audioInput)
            return 'audio_input';
        if (!hello.selfChecks.audioOutput)
            return 'audio_output';
        // The explicitly enabled robot browser Host has an in-page shortcut, not an OS-global one.
        // All device, authentication, nonce, and epoch checks remain required.
        const robotBrowser = process.env['ROBOT_BROWSER_HOST'] === '1' &&
            hello.hostVersion === '1.0.0-browser';
        // The authenticated replay client intentionally has no OS shortcut.
        // Keep its explicit opt-in separate from native and browser admission.
        const robotAudioBenchmark = process.env['ROBOT_AUDIO_BENCHMARK_HOST'] === '1' &&
            !!process.env['ROBOT_GATEWAY_URL'] &&
            hello.hostVersion === 'audio-benchmark-cli-v1';
        if (!hello.selfChecks.globalShortcut && !robotBrowser && !robotAudioBenchmark)
            return 'global_shortcut';
        if (this.visualInput.source === 'screen' &&
            this.visualInput.mode === 'on-demand' &&
            !hello.selfChecks.appshot)
            return 'appshot';
        if (this.visualInput.source === 'screen' &&
            this.visualInput.mode === 'on-demand' &&
            appshot.state !== 'ready')
            return 'appshot';
        return undefined;
    }
    blockerMessage(blocker, provider, appshot, hello) {
        if ((blocker === 'provider_config' || blocker === 'provider_unreachable') &&
            provider.message) {
            return provider.message;
        }
        if (blocker === 'appshot' && hello?.selfChecks.appshot && appshot.message) {
            return appshot.message;
        }
        const messages = {
            host_missing: 'runtime.hostMissing',
            host_disconnected: 'runtime.hostDisconnected',
            host_version: 'runtime.hostVersion',
            microphone_permission: 'runtime.microphonePermission',
            camera_permission: 'runtime.cameraPermission',
            accessibility_permission: 'runtime.accessibilityPermission',
            screen_recording_permission: 'runtime.screenPermission',
            audio_input: 'runtime.audioInput',
            audio_output: 'runtime.audioOutput',
            global_shortcut: 'runtime.shortcut',
            appshot: 'runtime.appshot',
            provider_config: 'runtime.providerConfig',
            provider_unreachable: 'runtime.providerUnavailable',
        };
        return this.uiText(messages[blocker]);
    }
    uiText(key) {
        return this.options.getUiLanguage ? liveMessage(key) : liveText('en', key);
    }
    isLeaseHealthy(lease) {
        return (lease.socket.readyState === WebSocket.OPEN &&
            this.now() - lease.lastPongAt <= this.heartbeatTimeoutMs);
    }
    handleTextFrame(lease, data) {
        const text = Buffer.isBuffer(data)
            ? data.toString('utf8')
            : Array.isArray(data)
                ? Buffer.concat(data).toString('utf8')
                : Buffer.from(data).toString('utf8');
        if (Buffer.byteLength(text) > MAX_HOST_TEXT_BYTES) {
            this.reportHostFailure(lease, 'host_message_too_large', 'host_protocol', 'Host control message exceeded the supported size.', 1009);
            lease.socket.close(1009, 'Host message is too large.');
            return;
        }
        const message = parseHostMessage(text);
        if (!message) {
            this.reportHostFailure(lease, 'host_message_invalid', 'host_protocol', 'Host sent an invalid control message.', 1002);
            this.sendHostError('invalid_message', 'Invalid Qwen Live Harness Host message.');
            lease.socket.close(1002, 'Invalid Qwen Live Harness Host message.');
            return;
        }
        if (message.type === 'host.hello') {
            try {
                this.options.onDebug?.('host.hello', { ...message });
            }
            catch {
                // Diagnostic observation must not affect Host readiness.
            }
            this.handleHello(lease, message);
            return;
        }
        if (!lease.hello) {
            this.reportHostFailure(lease, 'host_hello_required', 'host_protocol', 'Host sent a control message before its hello.', 1002);
            lease.socket.close(1002, 'host.hello must be the first message.');
            return;
        }
        if (message.type === 'host.pong') {
            if (message.pingId === lease.pingId) {
                lease.lastPongAt = this.now();
                lease.pingId = undefined;
            }
            return;
        }
        if (message.type === 'host.visual_capture_result') {
            this.handleVisualCaptureResult(message);
            return;
        }
        if (message.type === 'host.shortcut_result') {
            this.handleShortcutResult(message);
            return;
        }
        if (message.type === 'host.playback_started') {
            this.handlePlaybackStarted(message);
            return;
        }
        if (message.type === 'host.playback_completed') {
            this.handlePlaybackCompleted(message);
            return;
        }
        if (message.type === 'host.visual_frame') {
            this.handleVisualFrame(message);
            return;
        }
        if (message.type === 'host.visual_settings') {
            this.handleVisualSettings(message);
            return;
        }
        if (message.type === 'host.memory_action') {
            void this.handleMemoryAction(lease, message);
            return;
        }
        if (message.type === 'host.language_action') {
            this.handleLanguageAction(lease, message);
            return;
        }
        if (message.type === 'host.permission_mode_action') {
            this.handlePermissionModeAction(lease, message);
            return;
        }
        if (message.type === 'host.voice_action') {
            this.handleVoiceAction(lease, message);
            return;
        }
        this.handleAction(message);
    }
    handlePermissionModeAction(lease, message) {
        if (this.host !== lease)
            return;
        lease.permissionModeResults ??= new Map();
        const cached = lease.permissionModeResults.get(message.requestId);
        let result;
        const identity = {
            type: 'host.permission_mode_result',
            requestId: message.requestId,
            epoch: message.epoch,
            daemonInstanceNonce: this.daemonInstanceNonce,
        };
        try {
            if (message.epoch !== this.nextEpoch ||
                message.daemonInstanceNonce !== this.daemonInstanceNonce)
                throw new Error(liveMessage('permissionMode.callChanged'));
            if (cached) {
                if (cached.request.mode !== message.mode ||
                    cached.request.epoch !== message.epoch ||
                    cached.request.daemonInstanceNonce !== message.daemonInstanceNonce)
                    throw new Error(liveMessage('permissionMode.invalid'));
                this.sendHost(cached.result);
                return;
            }
            if (!this.options.onPermissionModeAction ||
                !this.options.getPermissionMode)
                throw new Error(liveMessage('permissionMode.unavailable'));
            const permissionModeV1 = this.options.onPermissionModeAction(message.mode);
            if (permissionModeV1.mode !== message.mode)
                throw new Error(liveMessage('permissionMode.saveFailed'));
            result = { ...identity, ok: true, permissionModeV1 };
        }
        catch (error) {
            result = {
                ...identity,
                ok: false,
                error: error instanceof Error &&
                    error.message.startsWith('qwen-live-harness-ui:')
                    ? error.message
                    : liveMessage('permissionMode.saveFailed'),
                ...(this.options.getPermissionMode
                    ? { permissionModeV1: this.options.getPermissionMode() }
                    : {}),
            };
        }
        if (!cached) {
            lease.permissionModeResults.set(message.requestId, {
                request: message,
                result,
            });
            if (lease.permissionModeResults.size > 64)
                lease.permissionModeResults.delete(lease.permissionModeResults.keys().next().value);
        }
        this.sendHost(result);
        this.broadcastState();
    }
    voiceCreationGuard(epoch) {
        const lease = this.host;
        const current = () => Boolean(lease &&
            this.host === lease &&
            lease.hello &&
            this.isLeaseHealthy(lease) &&
            !this.call &&
            !this.deactivating &&
            this.nextEpoch === epoch);
        if (!current())
            throw new Error(liveMessage('voice.cloneIdle'));
        return current;
    }
    refreshVoiceSettings() {
        this.broadcastState();
    }
    handleVoiceAction(lease, message) {
        if (this.host !== lease)
            return;
        lease.voiceResults ??= new Map();
        const cached = lease.voiceResults.get(message.requestId);
        let result;
        const identity = {
            type: 'host.voice_result',
            requestId: message.requestId,
            epoch: message.epoch,
            daemonInstanceNonce: this.daemonInstanceNonce,
        };
        try {
            if (message.epoch !== this.nextEpoch ||
                message.daemonInstanceNonce !== this.daemonInstanceNonce)
                throw new Error(liveMessage('voice.callChanged'));
            if (cached) {
                if (cached.request.voice !== message.voice ||
                    cached.request.epoch !== message.epoch ||
                    cached.request.daemonInstanceNonce !== message.daemonInstanceNonce)
                    throw new Error(liveMessage('voice.invalid'));
                this.sendHost(cached.result);
                return;
            }
            if (!this.options.onVoiceAction || !this.options.getVoice)
                throw new Error(liveMessage('voice.unavailable'));
            const voiceSettingsV1 = this.options.onVoiceAction(message.voice);
            if (voiceSettingsV1.voice !== message.voice)
                throw new Error(liveMessage('voice.saveFailed'));
            result = { ...identity, ok: true, voiceSettingsV1 };
        }
        catch (error) {
            result = {
                ...identity,
                ok: false,
                error: error instanceof Error &&
                    error.message.startsWith('qwen-live-harness-ui:')
                    ? error.message
                    : liveMessage('voice.saveFailed'),
                ...(this.options.getVoice
                    ? { voiceSettingsV1: this.options.getVoice() }
                    : {}),
            };
        }
        if (!cached) {
            lease.voiceResults.set(message.requestId, {
                request: message,
                result,
            });
            if (lease.voiceResults.size > 64)
                lease.voiceResults.delete(lease.voiceResults.keys().next().value);
        }
        this.sendHost(result);
        this.broadcastState();
    }
    handleLanguageAction(lease, message) {
        lease.languageResults ??= new Map();
        const cached = lease.languageResults.get(message.requestId);
        if (cached) {
            this.sendHost(cached);
            return;
        }
        let result;
        try {
            if (message.epoch !== this.nextEpoch)
                throw new Error(liveMessage('language.callChanged'));
            if (!this.options.onLanguageAction)
                throw new Error(liveMessage('language.unavailable'));
            const uiLanguageV1 = this.options.onLanguageAction(message.language);
            result = {
                type: 'host.language_result',
                requestId: message.requestId,
                ok: true,
                uiLanguageV1,
            };
        }
        catch (error) {
            result = {
                type: 'host.language_result',
                requestId: message.requestId,
                ok: false,
                error: error instanceof Error &&
                    error.message.startsWith('qwen-live-harness-ui:')
                    ? error.message
                    : liveMessage('language.saveFailed'),
                ...(this.options.getUiLanguage
                    ? { uiLanguageV1: this.options.getUiLanguage() }
                    : {}),
            };
        }
        lease.languageResults.set(message.requestId, result);
        if (lease.languageResults.size > 64)
            lease.languageResults.delete(lease.languageResults.keys().next().value);
        this.sendHost(result);
        this.broadcastState();
    }
    refreshMemoryState() {
        this.broadcastState();
    }
    refreshSubagentsState() {
        const subagentsV1 = this.options.getSubagents?.();
        if (subagentsV1 && this.host?.hello?.subagentsV1)
            this.sendHost({ type: 'host.subagents', subagentsV1 });
    }
    memoryState() {
        const state = this.options.getMemoryState?.();
        return state ? { ...state, locked: this.call !== undefined } : undefined;
    }
    async handleMemoryAction(lease, message) {
        lease.memoryResults ??= new Map();
        lease.memoryPending ??= new Set();
        const cached = lease.memoryResults.get(message.requestId);
        if (cached) {
            this.sendHost(cached);
            return;
        }
        if (lease.memoryPending.has(message.requestId))
            return;
        if (lease.memoryPending.size >= 16) {
            this.sendHost({
                type: 'host.memory_result',
                requestId: message.requestId,
                ok: false,
                error: this.uiText('memoryUI.pending'),
            });
            return;
        }
        lease.memoryPending.add(message.requestId);
        let result;
        try {
            if (message.epoch !== this.nextEpoch)
                throw new Error(this.uiText('memoryUI.callChanged'));
            if (!this.options.onMemoryAction)
                throw new Error(this.uiText('memoryUI.unavailable'));
            if (this.call &&
                ['select', 'create', 'set_model'].includes(message.action))
                throw new Error(this.uiText('memoryUI.locked'));
            await this.options.onMemoryAction(message);
            const memory = this.memoryState();
            if (!memory)
                throw new Error(this.uiText('memoryUI.stateUnavailable'));
            result = {
                type: 'host.memory_result',
                requestId: message.requestId,
                ok: true,
                memory,
            };
        }
        catch (error) {
            const memory = this.memoryState();
            result = {
                type: 'host.memory_result',
                requestId: message.requestId,
                ok: false,
                error: error instanceof Error
                    ? error.message.slice(0, 1024)
                    : this.uiText('memoryUI.updateFailed'),
                ...(memory ? { memory } : {}),
            };
        }
        lease.memoryPending.delete(message.requestId);
        if (this.host !== lease)
            return;
        lease.memoryResults.set(message.requestId, result);
        if (lease.memoryResults.size > 64)
            lease.memoryResults.delete(lease.memoryResults.keys().next().value);
        this.sendHost(result);
        this.broadcastState();
    }
    handleShortcutResult(message) {
        const pending = this.pendingShortcut;
        if (!pending || message.requestId !== pending.requestId)
            return;
        this.pendingShortcut = undefined;
        clearTimeout(pending.timer);
        if (message.shortcut !== pending.shortcut) {
            pending.reject(new Error('Qwen Live Harness Host returned a mismatched shortcut.'));
            return;
        }
        if (!message.success) {
            this.reportFailure({
                code: 'shortcut_registration_failed',
                stage: 'host_readiness',
                impact: 'operation',
                message: 'Host could not register the requested global shortcut.',
            });
            pending.reject(new Error(message.error ||
                'The Qwen Live Harness shortcut could not be registered.'));
            return;
        }
        this.shortcut = pending.shortcut;
        const status = this.getStatus();
        this.sendState(status);
        pending.resolve(status);
    }
    handleVisualCaptureResult(message) {
        const pending = this.pendingVisualCaptures.get(message.requestId);
        if (!pending)
            return;
        const call = this.call;
        if (!call || call.epoch !== pending.epoch) {
            this.rejectPendingVisualCapture(message.requestId, new Error('The Qwen Live Harness call changed before visual capture completed.'));
            return;
        }
        this.pendingVisualCaptures.delete(message.requestId);
        clearTimeout(pending.timer);
        if (!message.success) {
            this.reportFailure({
                code: 'visual_capture_failed',
                stage: 'visual_capture',
                impact: 'operation',
                message: 'Host could not capture the selected visual source.',
                epoch: pending.epoch,
            });
            this.debug('visual.capture_failed', {
                epoch: pending.epoch,
                reason: message.error.slice(0, 256),
            });
            pending.reject(new Error(message.error));
            return;
        }
        if (message.source !== pending.source) {
            this.reportFailure({
                code: 'visual_source_mismatch',
                stage: 'visual_capture',
                impact: 'operation',
                message: 'Host visual capture returned the wrong source.',
                epoch: pending.epoch,
            });
            this.debug('visual.capture_failed', {
                epoch: pending.epoch,
                source: pending.source,
                reason: 'source_mismatch',
            });
            pending.reject(new Error('Qwen Live Harness Host returned the wrong visual capture source.'));
            return;
        }
        if (pending.screenDisplayId &&
            (message.source !== 'screen' ||
                message.screenScope !== 'display' ||
                !message.displayId ||
                (pending.screenDisplayId !== 'primary' &&
                    message.displayId.toLowerCase() !==
                        pending.screenDisplayId.toLowerCase()))) {
            this.reportFailure({
                code: 'visual_display_mismatch',
                stage: 'visual_capture',
                impact: 'operation',
                message: 'Host visual capture did not match the selected display.',
                epoch: pending.epoch,
            });
            pending.reject(new Error(this.uiText('runtime.displayCaptureMismatch')));
            return;
        }
        if (!pending.screenDisplayId &&
            message.source === 'screen' &&
            message.screenScope === 'display') {
            this.reportFailure({
                code: 'visual_display_mismatch',
                stage: 'visual_capture',
                impact: 'operation',
                message: 'Host returned a display capture for a different capture scope.',
                epoch: pending.epoch,
            });
            pending.reject(new Error(this.uiText('runtime.displayCaptureMismatch')));
            return;
        }
        if (pending.persistAsset && !message.screenshotPath) {
            this.reportFailure({
                code: 'visual_asset_missing',
                stage: 'visual_capture',
                impact: 'operation',
                message: 'Host did not return the requested persisted screenshot asset.',
                epoch: pending.epoch,
            });
            this.debug('visual.capture_failed', {
                epoch: pending.epoch,
                source: pending.source,
                reason: 'asset_missing',
            });
            pending.reject(new Error('Qwen Live Harness Host did not persist the requested visual capture.'));
            return;
        }
        this.debug('visual.capture_completed', {
            epoch: pending.epoch,
            source: message.source,
            ...(message.source === 'screen' && message.displayId
                ? { displayId: message.displayId }
                : {}),
            width: message.width,
            height: message.height,
            bytes: Buffer.byteLength(message.image, 'base64'),
            frameHash: createHash('sha256')
                .update(Buffer.from(message.image, 'base64'))
                .digest('hex')
                .slice(0, 16),
        });
        pending.resolve({
            source: message.source,
            image: message.image,
            ...(message.source === 'screen' && message.screenScope === 'display'
                ? { screenScope: 'display', displayId: message.displayId }
                : {}),
            width: message.width,
            height: message.height,
            ...(message.source === 'screen'
                ? {
                    appName: message.appName,
                    ...(message.windowTitle
                        ? { windowTitle: message.windowTitle }
                        : {}),
                    accessibilityText: message.accessibilityText,
                    ...(message.screenshotPath
                        ? { screenshotPath: message.screenshotPath }
                        : {}),
                }
                : message.screenshotPath
                    ? { screenshotPath: message.screenshotPath }
                    : {}),
        });
    }
    handleHello(lease, hello) {
        if (hello.protocolVersion !== LIVE_HOST_PROTOCOL_VERSION ||
            hello.bundleId !== LIVE_HOST_BUNDLE_ID ||
            (lease.hello && lease.hello.instanceNonce !== hello.instanceNonce)) {
            this.lastHostFailure = 'host_version';
            this.reportHostFailure(lease, 'host_version', 'host_handshake', 'Host identity or protocol version is incompatible.', 4006);
            this.detachHost(lease, 'host_version');
            lease.socket.close(4006, 'Incompatible Qwen Live Harness Host.');
            return;
        }
        lease.hello = hello;
        lease.lastPongAt = this.now();
        this.hadConnectedHost = true;
        this.lastHostFailure = undefined;
        this.debug('host.ready', {
            hostVersion: hello.hostVersion,
            protocolVersion: hello.protocolVersion,
            microphone: hello.permissions.microphone,
            camera: hello.permissions.camera,
            accessibility: hello.permissions.accessibility,
            screenRecording: hello.permissions.screenRecording,
            audioInput: hello.selfChecks.audioInput,
            audioOutput: hello.selfChecks.audioOutput,
            appshot: hello.selfChecks.appshot,
        });
        clearTimeout(lease.helloTimer);
        if (!lease.heartbeatTimer) {
            lease.heartbeatTimer = setInterval(() => this.heartbeat(lease), this.heartbeatIntervalMs);
            lease.heartbeatTimer.unref?.();
        }
        try {
            void Promise.resolve(this.handlers.onHostReady?.()).catch(() => undefined);
        }
        catch {
            /* readiness remains fail-closed until a later Host hello */
        }
        const status = this.getStatus();
        const memory = this.memoryState();
        this.sendHost({
            type: 'host.welcome',
            displayCaptureV1: true,
            ...(this.options.subagentsControlV1
                ? { subagentsControlV1: true }
                : {}),
            ...(this.host?.hello?.subagentsV1 && this.options.getSubagents
                ? { subagentsV1: this.options.getSubagents() }
                : {}),
            protocolVersion: LIVE_HOST_PROTOCOL_VERSION,
            daemonInstanceNonce: this.daemonInstanceNonce,
            ...(this.options.getPermissionMode
                ? { permissionModeV1: this.options.getPermissionMode() }
                : {}),
            ...(this.options.getVoice
                ? { voiceSettingsV1: this.options.getVoice() }
                : {}),
            ...(this.options.getUiLanguage
                ? { uiLanguageV1: this.options.getUiLanguage() }
                : {}),
            ...(this.options.daemonShutdownV1
                ? { daemonShutdownV1: true }
                : {}),
            heartbeatIntervalMs: this.heartbeatIntervalMs,
            epoch: this.nextEpoch,
            ...(hello.capabilities?.outputAudioEndMarkerV1 === true
                ? { capabilities: { outputAudioEndMarkerV1: true } }
                : {}),
            visualInput: { ...this.visualInput },
            status: projectStatusForHost(status),
            ...(memory ? { memory } : {}),
        });
        this.sendState(status);
    }
    handlePlaybackStarted(message) {
        const call = this.call;
        if (!call ||
            call.epoch !== message.epoch ||
            !this.outputAudio.has(message.outputId) ||
            this.outputMuted) {
            return;
        }
        if (!this.perOutputStarted.has(message.outputId)) {
            this.perOutputStarted.add(message.outputId);
            this.handlers.onOutputPlaybackStarted?.({ epoch: call.epoch, outputId: message.outputId });
        }
        if (this.playbackStartedNotified)
            return;
        this.playbackStartedNotified = true;
        this.handlers.onPlaybackStarted?.({ epoch: call.epoch });
    }
    handlePlaybackCompleted(message) {
        const call = this.call;
        if (!call ||
            call.epoch !== message.epoch ||
            !this.outputAudio.has(message.outputId) ||
            this.outputMuted) {
            return;
        }
        const output = this.outputAudio.get(message.outputId);
        if (!output)
            return;
        if (this.supportsOutputAudioEndMarker() && !output.finished)
            return;
        output.drained = true;
        if (output.finished)
            this.completeOutputAudio(call, message.outputId);
    }
    completeOutputAudio(call, outputId) {
        this.outputAudio.delete(outputId);
        this.perOutputStarted.delete(outputId);
        if (this.writableOutputId === outputId)
            this.writableOutputId = undefined;
        if (this.outputAudio.size > 0)
            return;
        this.playbackStartedNotified = false;
        this.handlers.onPlaybackCompleted?.({ epoch: call.epoch, outputId });
    }
    resetOutputAudio() {
        this.writableOutputId = undefined;
        this.outputAudio.clear();
        this.perOutputStarted.clear();
        this.playbackStartedNotified = false;
    }
    handleVisualFrame(message) {
        const call = this.call;
        if (!call ||
            call.epoch !== message.epoch ||
            call.state === 'stopping' ||
            this.visualInput.mode !== 'live-feed' ||
            this.visualInput.source !== message.source ||
            (message.source === 'screen' &&
                (!this.host?.hello?.displayCaptureV1 ||
                    message.screenScope !== 'display' ||
                    !message.displayId ||
                    ((this.visualInput.screenDisplayId ?? 'primary') !== 'primary' &&
                        message.displayId.toLowerCase() !==
                            this.visualInput.screenDisplayId?.toLowerCase())))) {
            return;
        }
        const frameHash = createHash('sha256')
            .update(Buffer.from(message.image, 'base64'))
            .digest('hex')
            .slice(0, 16);
        try {
            const accepted = this.handlers.onInputImage?.({
                epoch: call.epoch,
                callId: call.callId,
                source: message.source,
                image: message.image,
                ...(message.displayId ? { displayId: message.displayId } : {}),
            }) ?? false;
            this.debug('visual.frame', {
                epoch: call.epoch,
                source: message.source,
                bytes: Buffer.byteLength(message.image, 'base64'),
                frameHash,
                accepted,
            });
            if (!accepted) {
                this.reportFailure({
                    code: 'visual_frame_rejected',
                    stage: 'visual_input',
                    impact: 'feature',
                    message: 'The active call did not accept a visual input frame.',
                    epoch: call.epoch,
                    callId: call.callId,
                });
            }
        }
        catch (error) {
            this.reportFailure({
                code: 'visual_input_failed',
                stage: 'visual_input',
                impact: 'feature',
                message: 'Handling an input frame from the Host failed.',
                epoch: call.epoch,
                callId: call.callId,
            });
            this.debug('visual.frame', {
                epoch: call.epoch,
                source: message.source,
                bytes: Buffer.byteLength(message.image, 'base64'),
                frameHash,
                accepted: false,
                reason: error instanceof Error ? error.message : String(error),
            });
        }
    }
    handleVisualSettings(message) {
        const call = this.call;
        if (message.epoch !== (call?.epoch ?? this.nextEpoch) ||
            call?.state === 'stopping') {
            return;
        }
        const hello = this.host?.hello;
        if (hello) {
            hello.permissions.camera = message.permissions.camera;
            hello.permissions.accessibility = message.permissions.accessibility;
            hello.permissions.screenRecording = message.permissions.screenRecording;
            hello.selfChecks.appshot = message.appshot;
        }
        const changed = this.visualInput.source !== message.source ||
            this.visualInput.mode !== message.mode ||
            (message.screenDisplayId !== undefined &&
                (this.visualInput.screenDisplayId ?? 'primary').toLowerCase() !==
                    message.screenDisplayId);
        if (message.screenDisplayId !== undefined &&
            (this.visualInput.screenDisplayId ?? 'primary').toLowerCase() !==
                message.screenDisplayId) {
            try {
                this.options.onScreenDisplayChange?.(message.screenDisplayId);
            }
            catch {
                this.sendHostError('invalid_message', this.uiText('runtime.displaySaveFailed'));
                this.broadcastState();
                return;
            }
        }
        this.visualInput = {
            ...this.visualInput,
            source: message.source,
            mode: message.mode,
            ...(message.screenDisplayId !== undefined
                ? { screenDisplayId: message.screenDisplayId }
                : {}),
        };
        if (call && changed) {
            this.rejectPendingVisualCaptures(new Error('The visual settings changed before capture completed.'), call.epoch);
        }
        this.debug('visual.settings', {
            epoch: message.epoch,
            source: message.source,
            mode: message.mode,
            screenDisplayId: this.visualInput.screenDisplayId ?? 'primary',
        });
        if (call && changed) {
            this.handlers.onVisualSettings?.({
                epoch: call.epoch,
                callId: call.callId,
                visualInput: { ...this.visualInput },
            });
        }
        this.broadcastState();
    }
    handleAction(action) {
        if (action.epoch !== undefined &&
            action.epoch !== (this.call?.epoch ?? this.nextEpoch)) {
            this.sendHostError('stale_epoch', 'The Qwen Live Harness action epoch is stale.');
            return;
        }
        switch (action.action) {
            case 'toggle':
                if (this.call)
                    this.stop();
                else
                    this.startFromHost('resume');
                return;
            case 'new':
                this.startFromHost('new');
                return;
            case 'stop':
                this.stop();
                return;
            case 'mute':
                this.setMute(action);
                return;
            default:
                return;
        }
    }
    startFromHost(mode) {
        if (this.deactivating)
            return;
        try {
            this.start(mode);
        }
        catch (error) {
            if (error instanceof LiveUnavailableError) {
                this.reportFailure({
                    code: error.status.blocker ?? 'call_start_unavailable',
                    stage: 'call_start',
                    impact: 'operation',
                    message: 'The Host could not start a call because a required capability is unavailable.',
                });
                this.debug('call.start_blocked', {
                    mode,
                    ...(error.status.blocker ? { blocker: error.status.blocker } : {}),
                    ...(error.status.message ? { message: error.status.message } : {}),
                });
                this.sendState(error.status);
                return;
            }
            this.debug('call.start_failed', {
                mode,
                message: error instanceof Error ? error.message : String(error),
            });
            this.reportFailure({
                code: 'call_start_failed',
                stage: 'call_start',
                impact: 'operation',
                message: 'The Host could not start the requested call.',
            });
            this.sendState({
                ...this.getStatus(),
                state: 'error',
                message: this.uiText('runtime.startFailed'),
            });
        }
    }
    handleAudioFrame(lease, data) {
        if (!lease.hello) {
            this.reportHostFailure(lease, 'host_hello_required', 'host_protocol', 'Host sent audio before its hello.', 1002);
            lease.socket.close(1002, 'host.hello must precede audio.');
            return;
        }
        const audio = Buffer.isBuffer(data)
            ? data
            : Array.isArray(data)
                ? Buffer.concat(data)
                : Buffer.from(data);
        if (audio.byteLength <= LIVE_INPUT_AUDIO_EPOCH_BYTES ||
            audio.byteLength > MAX_HOST_AUDIO_WIRE_BYTES ||
            (audio.byteLength - LIVE_INPUT_AUDIO_EPOCH_BYTES) % 2 !== 0) {
            this.reportHostFailure(lease, 'host_audio_frame_invalid', 'audio_input', 'Host sent an invalid audio frame.', 1009);
            lease.socket.close(1009, 'Invalid Qwen Live Harness audio frame.');
            return;
        }
        const encodedEpoch = audio.readBigUInt64BE(0);
        if (encodedEpoch > BigInt(Number.MAX_SAFE_INTEGER)) {
            this.reportHostFailure(lease, 'host_audio_frame_invalid', 'audio_input', 'Host audio frame had an invalid epoch.', 1009);
            lease.socket.close(1009, 'Invalid Qwen Live Harness audio frame.');
            return;
        }
        const epoch = Number(encodedEpoch);
        const call = this.call;
        if (!call ||
            epoch !== call.epoch ||
            call.state === 'stopping' ||
            this.inputMuted) {
            return;
        }
        const pcm16 = audio.subarray(LIVE_INPUT_AUDIO_EPOCH_BYTES);
        if(qaAudioFrameLog)qaAudioFrameLog.write(JSON.stringify({time:Date.now()/1000,system_monotonic:Number(process.hrtime.bigint())/1e9,epoch,samples:pcm16.length/2,sha256:createHash('sha256').update(pcm16).digest('hex'),source:'daemon_accepted_frame_before_onInputAudio'})+'\n');
        try {
            const accepted = this.handlers.onInputAudio?.({
                epoch,
                callId: call.callId,
                pcm16: Buffer.from(pcm16),
            });
            if (accepted === false) {
                this.failCall(call.epoch, this.uiText('runtime.audioDropped'), {
                    code: 'audio_input_rejected',
                    stage: 'audio_input',
                });
            }
        }
        catch {
            this.failCall(call.epoch, this.uiText('runtime.audioInputFailed'), {
                code: 'audio_input_failed',
                stage: 'audio_input',
            });
        }
    }
    heartbeat(lease) {
        if (this.host !== lease)
            return;
        if (this.now() - lease.lastPongAt > this.heartbeatTimeoutMs) {
            this.disconnectHost(lease, 4008, 'Qwen Live Harness Host heartbeat timed out.', 'host_heartbeat_timeout');
            return;
        }
        const pingId = randomUUID();
        lease.pingId = pingId;
        this.sendHost({ type: 'host.ping', pingId });
    }
    finishCall(call) {
        if (this.call !== call)
            return;
        this.pendingStartMode = undefined;
        call.state = 'stopping';
        this.sendState(this.buildStatus(false));
        this.clearOutput(call.epoch);
        this.call = undefined;
        this.notifyInactive();
        this.rejectPendingVisualCaptures(new Error('The Qwen Live Harness call ended before visual capture completed.'), call.epoch);
        ++this.nextEpoch;
        try {
            void Promise.resolve(this.handlers.onStop?.({ epoch: call.epoch, callId: call.callId })).catch(() => {
                this.reportFailure({
                    code: 'call_stop_failed',
                    stage: 'call_stop',
                    impact: 'call',
                    message: 'The call stop handler failed after local teardown.',
                    epoch: call.epoch,
                    callId: call.callId,
                    executionUncertain: true,
                });
            });
        }
        catch {
            // The call is already stopped. Handler failures cannot restore it.
            this.reportFailure({
                code: 'call_stop_failed',
                stage: 'call_stop',
                impact: 'call',
                message: 'The call stop handler failed after local teardown.',
                epoch: call.epoch,
                callId: call.callId,
                executionUncertain: true,
            });
        }
        this.broadcastState();
    }
    beginCallStop(call) {
        if (this.call !== call || call.state === 'stopping')
            return;
        call.state = 'stopping';
        this.sendState(this.buildStatus(false));
        this.clearOutput(call.epoch);
        let result;
        try {
            result = this.handlers.onStop?.({
                epoch: call.epoch,
                callId: call.callId,
            });
        }
        catch {
            this.failStoppingCall(call, this.uiText('runtime.stopFailed'));
            return;
        }
        if (!result || !('then' in result)) {
            this.finishStoppingCall(call, result);
            return;
        }
        void Promise.resolve(result).then((outcome) => this.finishStoppingCall(call, outcome), () => this.failStoppingCall(call, this.uiText('runtime.stopFailed')));
    }
    finishStoppingCall(call, outcome) {
        if (this.call !== call || call.state !== 'stopping')
            return;
        if (outcome?.error) {
            this.failStoppingCall(call, outcome.error);
            return;
        }
        this.call = undefined;
        this.resetOutputAudio();
        this.notifyInactive();
        this.rejectPendingVisualCaptures(new Error('The Qwen Live Harness call ended before visual capture completed.'), call.epoch);
        ++this.nextEpoch;
        const pendingStartMode = this.pendingStartMode;
        this.pendingStartMode = undefined;
        if (pendingStartMode) {
            const status = this.getStatus();
            if (status.available) {
                this.startCall(pendingStartMode);
                return;
            }
        }
        this.broadcastState();
    }
    failStoppingCall(call, message) {
        if (this.call !== call || call.state !== 'stopping')
            return;
        this.reportFailure({
            code: 'call_stop_failed',
            stage: 'call_stop',
            impact: 'call',
            message,
            epoch: call.epoch,
            callId: call.callId,
            executionUncertain: true,
        });
        this.pendingStartMode = undefined;
        this.call = undefined;
        this.resetOutputAudio();
        this.notifyInactive();
        this.rejectPendingVisualCaptures(new Error(message), call.epoch);
        this.lastCallError = message;
        ++this.nextEpoch;
        this.broadcastState();
    }
    stopForReadinessLoss() {
        const call = this.call;
        if (!call)
            return;
        this.pendingStartMode = undefined;
        this.beginCallStop(call);
    }
    disconnectHost(lease, code, reason, failureCode = 'host_disconnected') {
        this.reportHostFailure(lease, failureCode, 'host_transport', reason, code);
        if (lease.socket.readyState === WebSocket.OPEN) {
            lease.socket.close(code, reason);
        }
        this.detachHost(lease, 'host_disconnected');
    }
    detachHost(lease, failure) {
        if (this.host !== lease)
            return;
        this.host = undefined;
        this.clearLeaseTimers(lease);
        this.lastHostFailure = failure;
        this.rejectPendingVisualCaptures(new Error('Qwen Live Harness Host disconnected.'));
        this.rejectPendingShortcut(new Error('Qwen Live Harness Host disconnected.'));
        this.stopForReadinessLoss();
    }
    rejectPendingShortcut(error) {
        const pending = this.pendingShortcut;
        if (!pending)
            return;
        this.pendingShortcut = undefined;
        clearTimeout(pending.timer);
        pending.reject(error);
    }
    rejectPendingVisualCapture(requestId, error) {
        const pending = this.pendingVisualCaptures.get(requestId);
        if (!pending)
            return;
        this.pendingVisualCaptures.delete(requestId);
        clearTimeout(pending.timer);
        pending.reject(error);
    }
    rejectPendingVisualCaptures(error, epoch) {
        for (const [requestId, pending] of this.pendingVisualCaptures) {
            if (epoch !== undefined && pending.epoch !== epoch)
                continue;
            this.rejectPendingVisualCapture(requestId, error);
        }
    }
    clearLeaseTimers(lease) {
        clearTimeout(lease.helloTimer);
        if (lease.heartbeatTimer)
            clearInterval(lease.heartbeatTimer);
    }
    broadcastState() {
        this.sendState(this.getStatus());
    }
    sendState(status) {
        const memory = this.memoryState();
        this.sendHost({
            type: 'host.state',
            ...(this.options.getPermissionMode
                ? { permissionModeV1: this.options.getPermissionMode() }
                : {}),
            ...(this.options.getVoice
                ? { voiceSettingsV1: this.options.getVoice() }
                : {}),
            ...(this.host?.hello?.subagentsV1 && this.options.getSubagents
                ? { subagentsV1: this.options.getSubagents() }
                : {}),
            epoch: this.nextEpoch,
            ...(this.options.getUiLanguage
                ? { uiLanguageV1: this.options.getUiLanguage() }
                : {}),
            visualInput: { ...this.visualInput },
            status: projectStatusForHost(status),
            ...(memory ? { memory } : {}),
        });
    }
    sendHostError(code, message) {
        this.sendHost({ type: 'host.error', code, message });
    }
    sendHost(message) {
        const lease = this.host;
        const socket = lease?.socket;
        if (!socket || socket.readyState !== WebSocket.OPEN)
            return false;
        if (socket.bufferedAmount > MAX_SOCKET_BUFFERED_BYTES) {
            this.disconnectHost(lease, 4008, 'Qwen Live Harness Host is not consuming messages.', 'host_message_backpressure');
            return false;
        }
        try {
            socket.send(JSON.stringify(message));
        }
        catch (error) {
            if (this.call?.state !== 'stopping' && !this.deactivating) {
                this.reportHostFailure(lease, 'host_message_send_failed', 'host_transport', 'Sending a control message to the Host failed.');
            }
            throw error;
        }
        return true;
    }
    allocateOutputId() {
        if (this.nextOutputId >= Number.MAX_SAFE_INTEGER) {
            this.nextOutputId = 0;
        }
        this.nextOutputId += 1;
        return this.nextOutputId;
    }
    supportsOutputAudioEndMarker() {
        return this.host?.hello?.capabilities?.outputAudioEndMarkerV1 === true;
    }
    debug(event, details) {
        this.logger.debug(`${event} ${JSON.stringify(details)}`);
    }
    reportHostFailure(lease, code, stage, message, closeCode) {
        if (lease.expectedClose || lease.failureReported || this.host !== lease)
            return;
        lease.failureReported = true;
        this.reportFailure({
            code,
            stage,
            message,
            impact: this.call && this.call.state !== 'stopping' ? 'call' : 'feature',
            ...(closeCode !== undefined ? { closeCode } : {}),
        });
    }
    reportFailure(failure) {
        if (!this.options.onFailure)
            return;
        const epoch = failure.epoch ?? this.call?.epoch;
        const key = `${epoch === undefined ? `host:${this.hostGeneration}` : `call:${epoch}`}:${failure.code}`;
        if (this.reportedFailures.has(key))
            return;
        this.reportedFailures.add(key);
        if (this.reportedFailures.size > MAX_REPORTED_FAILURES) {
            const oldest = this.reportedFailures.values().next().value;
            if (oldest !== undefined)
                this.reportedFailures.delete(oldest);
        }
        emitRuntimeFailure(this.options.onFailure, {
            source: 'host',
            ...(epoch !== undefined ? { epoch } : {}),
            ...(this.call && this.call.epoch === epoch
                ? { callId: this.call.callId }
                : {}),
            ...failure,
        });
    }
    notifyInactive() {
        if (this.call)
            return;
        for (const resolve of this.inactiveWaiters)
            resolve();
        this.inactiveWaiters.clear();
    }
}
