/**
 * @license
 * Copyright 2026 Qwen
 * SPDX-License-Identifier: Apache-2.0
 */
export class AsyncEventQueue {
    capacity;
    onDrop;
    buffered = [];
    waiters = [];
    ended = false;
    constructor(options = {}) {
        this.capacity = options.capacity ?? 500;
        this.onDrop = options.onDrop;
    }
    push(item) {
        if (this.ended)
            return;
        const waiter = this.waiters.shift();
        if (waiter) {
            if (waiter.detach)
                waiter.detach();
            waiter.resolve({ value: item, done: false });
            return;
        }
        this.buffered.push(item);
        if (this.buffered.length > this.capacity) {
            this.evictOne();
        }
    }
    end() {
        if (this.ended)
            return;
        this.ended = true;
        for (const waiter of this.waiters.splice(0)) {
            if (waiter.detach)
                waiter.detach();
            waiter.resolve({ value: undefined, done: true });
        }
    }
    subscribe(options = {}) {
        // A new subscription takes over: the previous iterator must end or
        // the pump's resubscribe would double-consume.
        for (const stale of this.waiters.splice(0)) {
            if (stale.detach)
                stale.detach();
            stale.resolve({ value: undefined, done: true });
        }
        const signal = options.signal;
        if (signal?.aborted) {
            return this.abortedIterable();
        }
        // The iterator closures below need the queue instance; an arrow-bound
        // alternative would re-alias `this` anyway.
        // eslint-disable-next-line @typescript-eslint/no-this-alias
        const queue = this;
        return {
            [Symbol.asyncIterator]() {
                return {
                    next: async () => {
                        if (queue.buffered.length > 0) {
                            const value = queue.buffered.shift();
                            return { value, done: false };
                        }
                        if (queue.ended) {
                            return { value: undefined, done: true };
                        }
                        return await new Promise((resolve) => {
                            const waiter = { resolve };
                            queue.waiters.push(waiter);
                            const onAbort = () => {
                                const index = queue.waiters.indexOf(waiter);
                                if (index !== -1)
                                    queue.waiters.splice(index, 1);
                                resolve({ value: undefined, done: true });
                            };
                            waiter.detach = () => signal?.removeEventListener('abort', onAbort);
                            signal?.addEventListener('abort', onAbort, { once: true });
                        });
                    },
                };
            },
        };
    }
    get size() {
        return this.buffered.length;
    }
    evictOne() {
        // Progress-shaped events drop first; identify by the `type` field the
        // BackendEvent union carries. Anything without it falls back to
        // oldest-first.
        let index = this.buffered.findIndex((item) => ['progress', 'activity'].includes(item.type ?? ''));
        if (index === -1)
            index = 0;
        this.buffered.splice(index, 1);
        this.onDrop?.(1);
    }
    abortedIterable() {
        let done = false;
        return {
            [Symbol.asyncIterator]: () => ({
                next: () => {
                    if (done)
                        return Promise.resolve({ value: undefined, done: true });
                    done = true;
                    return Promise.resolve({ value: undefined, done: true });
                },
            }),
        };
    }
}
