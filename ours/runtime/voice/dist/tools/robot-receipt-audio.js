import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, statSync, writeFileSync, } from 'node:fs';
import { join } from 'node:path';
import { ROBOT_ACCEPTED_SPEECH, ROBOT_QUEUED_SPEECH } from './robot-turn.js';
const validatedAudio = new Map();
const normalize = (text) => text.normalize('NFKC').replace(/[\p{P}\p{Z}\s]/gu, '');
const digest = (value) => createHash('sha256').update(value).digest('hex');
const identity = (o) => JSON.stringify([
    o.endpoint,
    o.model,
    o.voice ?? '',
    o.language,
    o.fixedAnnouncement,
]);
const FIXED_RECEIPTS = new Set([
    ROBOT_ACCEPTED_SPEECH,
    ROBOT_QUEUED_SPEECH,
    '机械臂已开始执行当前任务。',
    '已暂停机械臂，保持当前位置。',
    '当前任务仍在进行，没有暂停或取消。',
    '当前任务继续执行，完成后停止。',
    '已恢复当前任务，继续执行原目标。',
    '已取消任务，机械臂保持当前位置。',
    '已记录等待任务，当前任务通过完成检查后才会执行。',
    '已取消等待任务，当前任务保持原状态。',
    '已拒绝这条待确认任务，未下发动作。',
    '已取消这次任务澄清，未下发新任务。',
]);
const allowed = (o) => o.purpose === 'task_result' && !!o.fixedAnnouncement && FIXED_RECEIPTS.has(o.fixedAnnouncement);
/** A local voice asset is only delivery material, never task authorization. */
export function readRobotReceiptAudio(directory, options) {
    if (!directory || !allowed(options))
        return undefined;
    try {
        const cacheKey = directory + '|' + identity(options);
        if (validatedAudio.has(cacheKey))
            return validatedAudio.get(cacheKey);
        const file = join(directory, digest(identity(options)) + '.json');
        if (statSync(file).size > 2_000_000)
            return undefined;
        const data = JSON.parse(readFileSync(file, 'utf8'));
        if (data['schema'] !== 1 ||
            data['identity'] !== identity(options) ||
            data['sampleRate'] !== 24000 ||
            typeof data['transcript'] !== 'string' ||
            normalize(data['transcript']) !== normalize(options.fixedAnnouncement) ||
            typeof data['pcm16'] !== 'string')
            return undefined;
        const audio = Buffer.from(data['pcm16'], 'base64');
        if (!audio.length ||
            audio.length % 2 ||
            audio.length > 24000 * 2 * 30 ||
            data['sha256'] !== digest(audio))
            return undefined;
        const result = { audio, sampleRate: 24000, transcript: data['transcript'] };
        if (validatedAudio.size >= 32)
            validatedAudio.delete(validatedAudio.keys().next().value);
        validatedAudio.set(cacheKey, result);
        return result;
    }
    catch {
        return undefined;
    }
}
/** Called by the explicit preparation script after the cloud readout validates. */
export function writeRobotReceiptAudio(directory, options, result) {
    if (!allowed(options) ||
        result.sampleRate !== 24000 ||
        !result.audio.length ||
        result.audio.length % 2 ||
        result.audio.length > 24000 * 2 * 30 ||
        normalize(result.transcript) !== normalize(options.fixedAnnouncement))
        throw new Error('Invalid robot receipt audio');
    mkdirSync(directory, { recursive: true, mode: 0o700 });
    const file = join(directory, digest(identity(options)) + '.json');
    const temporary = file + '.' + process.pid + '.tmp';
    writeFileSync(temporary, JSON.stringify({
        schema: 1,
        identity: identity(options),
        sampleRate: 24000,
        transcript: result.transcript,
        pcm16: Buffer.from(result.audio).toString('base64'),
        sha256: digest(result.audio),
    }), { mode: 0o600 });
    renameSync(temporary, file);
}
