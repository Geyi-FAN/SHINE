/** One bounded read-only listen; no inventory, task reference or tools on wire. */
import WebSocket from 'ws';
import { deriveQwenOmniRealtimeUrl } from '../realtime/realtime-session.js';
// Public tool vocabulary, not evidence that an object is currently present.
// It only gates a read-only listen; it is never sent to the ASR service.
const publicVocabulary = Object.freeze({entities: Object.freeze([
    'bowl', 'plate', 'cheese', 'bottle', 'cabinet', 'stove', 'rack', 'table'
].map(id => Object.freeze({id})))});
function lexicalInventory(inventory) {
    return inventory && Array.isArray(inventory.entities) ? inventory : publicVocabulary;
}
function lexicalDistance(a, b) {
    let row = Array.from({length: b.length + 1}, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
        const next = [i];
        for (let j = 1; j <= b.length; j++)
            next[j] = Math.min(next[j - 1] + 1, row[j] + 1, row[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        row = next;
    }
    return row[b.length];
}
export function needsAudioRelisten(text, inventory) {
    inventory = lexicalInventory(inventory);
    const available = inventory.entities.map((e) => e.id);
    const aliases = available.flatMap((x) => x === 'bottle'
        ? ['wine bottle', 'bottle']
        : x === 'cheese'
            ? ['cream cheese', 'cheese']
            : x === 'cabinet'
                ? ['cabinet', 'drawer']
                : [x]);
    const clauses = text.split(/[.!?;,]|\bthen\b/i);
    // Named waiting cancellation needs the same independent noun check as a
    // manipulation request. Never infer an alias from the queued goal.
    // Final ASR punctuation can split "object task" into "object. Task".
    // Compare the WHOLE lexical command for this read-only trigger. Do not
    // repair a noun, drop a later action, or use a queued task as a reference.
    const cancelWords = (text.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) ?? []).join(' ');
    const cancel = !/[?？"“”「」]/.test(text) &&
        /^(?:please )?(?:cancel|skip) (?:the )?(.+?) task(?: keep going| carry on| keep working)?$/.exec(cancelWords);
    if (cancel && !aliases.some(x => new RegExp('\\b' + x + '\\b', 'i').test(cancel[1])))
        return true;
    // A read-only scene question can contain the same acoustic noun ambiguity
    // as a manipulation request. Trigger another AUDIO-ONLY listen; never
    // substitute a scene object for the spoken noun here.
    const questionNoun = /^(?:(?:is|are)\s+(?:the\s+)?|where\s+(?:is|are)\s+(?:the\s+)?)([a-z]+)\b/i.exec(text.trim());
    if (questionNoun) {
        const noun=questionNoun[1].toLowerCase();
        const known=aliases.flatMap(x=>x.split(' '));
        if (!known.includes(noun) && !known.includes(noun.replace(/s$/,'')) && !['it','this','that','there','they','we','you','robot'].includes(noun) &&
            known.some(x=>x.length>=3 && Math.abs(x.length-noun.length)<=2 && lexicalDistance(x,noun)<=2))
            return true;
    }
    return clauses.some((clause) => {
        const m = /\b(?:put|place|move|return|push|grab|pick up)\s+(?:the\s+|a\s+|an\s+)?(.+?)(?=\s+(?:on|onto|in|into|inside|to|back|from)\b|$)/i.exec(clause);
        if (!m)
            return false;
        const noun = m[1].trim().toLowerCase();
        if (/^(?:it|this|that|them)$/.test(noun))
            return false;
        return !aliases.some((x) => new RegExp('\\b' + x + '\\b', 'i').test(noun));
    });
}
/** Same-input acoustic alternative only; Python revalidates object roles. */
export function streamingGroundingAlternative(primary, alternate, inventory) {
    inventory = lexicalInventory(inventory);
    if (!needsAudioRelisten(primary, inventory) ||
        needsAudioRelisten(alternate, inventory))
        return false;
    const a = primary.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) ?? [], b = alternate.toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) ?? [];
    if (a.length !== b.length)
        return false;
    const changed = a.map((x, i) => (x === b[i] ? -1 : i)).filter((i) => i >= 0);
    if (changed.length < 1 || changed.length > 2)
        return false;
    const known = new Set(inventory.entities.flatMap((e) => e.id === 'bottle'
        ? ['wine', 'bottle']
        : e.id === 'cheese'
            ? ['cream', 'cheese']
            : e.id === 'cabinet'
                ? ['cabinet', 'drawer']
                : [e.id]));
    const immutable = new Set([
        'top',
        'middle',
        'upper',
        'bottom',
        'lower',
        'not',
        "don't",
        'never',
        "isn't",
        "aren't",
        "wasn't",
        "weren't",
        'stop',
        'open',
        'close',
        'turn',
        'put',
        'place',
        'return',
        'release',
        'keep',
        'on',
        'in',
        'into',
        'inside',
        'from',
        'to',
        'before',
        'after',
        'then',
        'instead',
    ]);
    return changed.every((i) => !known.has(a[i]) &&
        !immutable.has(a[i]) &&
        !immutable.has(b[i]) &&
        Math.abs(a[i].length - b[i].length) <= 2 &&
        lexicalDistance(a[i], b[i]) <= 2);
}
/** Ground only the original noun; a separate one-word ASR tail is not intent. */
export function selectStreamingGroundingText(primary, raw, inventory) {
    inventory = lexicalInventory(inventory);
    if (streamingGroundingAlternative(primary, raw, inventory))
        return raw;
    const tokens = [...raw.matchAll(/[a-z]+(?:'[a-z]+)?/gi)];
    const count = (primary.match(/[a-z]+(?:'[a-z]+)?/gi) ?? []).length;
    if (tokens.length !== count + 1 || count === 0)
        return;
    const tail = tokens.at(-1)[0].toLowerCase();
    const blockers = new Set([
        'no',
        'not',
        "don't",
        'never',
        'stop',
        'pause',
        'wait',
        'open',
        'close',
        'turn',
        'put',
        'place',
        'move',
        'return',
        'release',
        'keep',
        'leave',
        'before',
        'after',
        'then',
        'instead',
        'actually',
        'sorry',
        'top',
        'middle',
        'upper',
        'lower',
        'bottom',
    ]);
    const known = (inventory?.entities ??
        []).flatMap((e) => e.id === 'bottle'
        ? ['wine', 'bottle']
        : e.id === 'cheese'
            ? ['cream', 'cheese']
            : e.id === 'cabinet'
                ? ['cabinet', 'drawer']
                : [e.id]);
    if (blockers.has(tail) || known.includes(tail))
        return;
    const last = tokens[count - 1];
    const prefix = raw.slice(0, last.index + last[0].length);
    return streamingGroundingAlternative(primary, prefix, inventory)
        ? prefix
        : undefined;
}
export function transcribeAudioOnly(o) {
    return new Promise((resolve, reject) => {
        if (o.signal.aborted) {
            reject(Error('relisten_cancelled'));
            return;
        }
        const ws = new WebSocket(deriveQwenOmniRealtimeUrl(o.endpoint, o.model), {
            headers: { Authorization: `Bearer ${o.apiKey ?? ''}` },
            handshakeTimeout: 6000,
        });
        let finished = false, text = '';
        const finish = (error) => {
            if (finished)
                return;
            finished = true;
            clearTimeout(timer);
            o.signal.removeEventListener('abort', abort);
            try {
                ws.close();
            }
            catch { }
            if (error)
                reject(error);
            else if (text.trim())
                resolve(text.trim());
            else
                reject(Error('empty_relisten'));
        };
        const abort = () => finish(Error('relisten_cancelled'));
        o.signal.addEventListener('abort', abort, { once: true });
        const timer = setTimeout(() => finish(Error('relisten_timeout')), 8000);
        if (o.signal.aborted) {
            finish(Error('relisten_cancelled'));
            return;
        }
        ws.on('error', () => finish(Error('relisten_transport')));
        ws.on('close', () => {
            if (!finished)
                finish(Error('relisten_closed'));
        });
        ws.on('message', (raw) => {
            try {
                const m = JSON.parse(raw.toString()), type = m['type'];
                if (type === 'session.created')
                    ws.send(JSON.stringify({
                        type: 'session.update',
                        session: {
                            modalities: ['text'],
                            input_audio_transcription: null,
                            audio: {
                                input: { format: { type: 'pcm', sample_rate: 16000 } },
                                output: {
                                    voice: 'Tina',
                                    format: { type: 'pcm', sample_rate: 24000 },
                                },
                            },
                            tools: [],
                            turn_detection: null,
                            instructions: 'You are an audio transcriber. Transcribe the user audio verbatim in its original language. Preserve object names, negations, questions, and all words. Do not answer, interpret commands, infer from a scene, or execute anything. Output only the transcription. If a word is unclear, write [unclear] rather than guessing.',
                        },
                    }));
                if (type === 'session.updated') {
                    for (let i = 0; i < o.pcm16.length; i += 32000)
                        ws.send(JSON.stringify({
                            type: 'input_audio_buffer.append',
                            audio: o.pcm16.subarray(i, i + 32000).toString('base64'),
                        }));
                    ws.send(JSON.stringify({ type: 'input_audio_buffer.commit' }));
                }
                if (type === 'input_audio_buffer.committed')
                    ws.send(JSON.stringify({
                        type: 'response.create',
                        response: { modalities: ['text'] },
                    }));
                if (type === 'response.text.delta' ||
                    type === 'response.output_text.delta')
                    text += String(m['delta'] ?? '');
                if (text.length > 4000)
                    finish(Error('relisten_too_long'));
                if (type === 'response.done')
                    finish();
                if (type === 'error')
                    finish(Error('relisten_provider_error'));
            }
            catch {
                finish(Error('relisten_invalid_event'));
            }
        });
    });
}
