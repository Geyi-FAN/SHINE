/** Opt-in route resilience: multiple connection handshakes, ONE voice channel.
 * Original URL, SNI and certificate checks remain. No user frames/tools are sent
 * until a single successful connection is selected; all losers are destroyed.
 */
import { EventEmitter } from 'node:events';
import { readFileSync, appendFileSync } from 'node:fs';
import { join } from 'node:path';
import { isIP } from 'node:net';
import WebSocket, {} from 'ws';
function diagnostic(phase, data) {
    const directory = process.env['VOICE_EVAL_RECORD_DIR'];
    if (!directory)
        return;
    try {
        appendFileSync(join(directory, 'voice_connections.jsonl'), JSON.stringify({ time: Date.now() / 1000, phase, ...data }) + '\n');
    }
    catch { /* Diagnostics never control the call. */ }
}
export function createVoiceWebSocket(url, options) {
    const file = process.env['VOICE_NETWORK_ROUTE_FILE'];
    if (!file)
        return new WebSocket(url, options);
    const target = new URL(url), route = JSON.parse(readFileSync(file, 'utf8'));
    if (target.hostname !== route.hostname)
        return new WebSocket(url, options);
    if (target.protocol !== 'wss:' || route.hostname !== 'dashscope.aliyuncs.com' || !route.tls_verified || !route.websocket_verified ||
        !Array.isArray(route.addresses) || !route.addresses.length || route.addresses.length > 8 || route.addresses.some(x => isIP(x) !== 4) ||
        !(route.expires_at > Date.now() / 1000))
        throw Error('Invalid or expired voice network route');
    return new RacingVoiceSocket(url, options, route.addresses);
}
export class RacingVoiceSocket extends EventEmitter {
    OPEN = 1;
    readyState = 0;
    sockets = [];
    winner;
    failed = new Set();
    ended = false;
    firstSend = true;
    initialMessages = 0;
    constructor(url, options, addresses, factory = (u, o) => new WebSocket(u, o)) {
        super();
        for (const address of addresses) {
            const candidateOptions = { ...options, rejectUnauthorized: true,
                lookup: ((_host, opts, callback) => queueMicrotask(() => opts.all ? callback(null, [{ address, family: 4 }]) : callback(null, address, 4))) };
            const socket = factory(url, candidateOptions);
            this.sockets.push(socket);
            diagnostic('attempt', { address });
            socket.on('open', () => {
                if (this.ended || this.winner) {
                    socket.terminate();
                    return;
                }
                this.winner = socket;
                this.readyState = this.OPEN;
                diagnostic('selected', { address });
                for (const other of this.sockets)
                    if (other !== socket)
                        other.terminate();
                this.emit('open');
            });
            socket.on('message', (...args) => {
                if (this.winner !== socket || this.ended)
                    return;
                if (this.initialMessages++ < 4) {
                    try {
                        const type = JSON.parse(String(args[0])).type;
                        diagnostic('initial_message', { address, type });
                    }
                    catch {
                        diagnostic('invalid_initial_message', { address });
                    }
                }
                this.emit('message', ...args);
            });
            socket.on('error', (error) => {
                if (!this.winner)
                    diagnostic('connection_error', { address, code: error.code });
                if (this.winner === socket) {
                    if (!this.ended)
                        this.emit('error', error);
                }
                else
                    this.fail(socket, addresses.length);
            });
            socket.on('unexpected-response', (request, response) => {
                response.resume();
                request.destroy();
                this.fail(socket, addresses.length);
            });
            socket.on('close', (...args) => {
                if (this.winner === socket) {
                    this.readyState = 3;
                    this.ended = true;
                    this.emit('close', ...args);
                }
                else
                    this.fail(socket, addresses.length);
            });
        }
    }
    get bufferedAmount() { return this.winner?.bufferedAmount ?? 0; }
    send(data) {
        if (!this.winner || this.ended)
            throw Error('Voice channel is not open');
        if (this.firstSend) {
            this.firstSend = false;
            diagnostic('first_send', { bytes: Buffer.byteLength(data) });
        }
        this.winner.send(data);
    }
    close() {
        if (this.ended)
            return;
        this.ended = true;
        for (const socket of this.sockets)
            socket === this.winner ? socket.close() : socket.terminate();
        if (!this.winner) {
            this.readyState = 3;
            queueMicrotask(() => this.emit('close', 1000, Buffer.alloc(0)));
        }
    }
    terminate() {
        if (this.ended)
            return;
        this.ended = true;
        this.readyState = 3;
        for (const socket of this.sockets)
            socket.terminate();
        if (!this.winner)
            queueMicrotask(() => this.emit('close', 1000, Buffer.alloc(0)));
    }
    fail(socket, total) {
        this.failed.add(socket);
        if (this.winner || this.ended || this.failed.size < total)
            return;
        this.ended = true;
        this.readyState = 3;
        queueMicrotask(() => { this.emit('error', Error('All verified voice service addresses failed')); this.emit('close', 1006, Buffer.alloc(0)); });
    }
}
