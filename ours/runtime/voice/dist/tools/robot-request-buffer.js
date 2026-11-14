/** Actual user fragments only; never supplies a task, referent, or plan. */
export class RobotRequestBuffer {
    fragments = [];
    updated = 0;
    episode;
    bindEpisode(episode) {
        if (this.episode !== undefined && this.episode !== episode)
            this.clear();
        this.episode = episode;
    }
    clear() { this.fragments = []; this.updated = 0; }
    observe(id, raw, now = Date.now()) {
        const text = raw.trim();
        // A new independent question/control never authorizes an unfinished task.
        const independent = /^(?:stop|pause|cancel|reset|resume|continue|thanks|thank you|yes|no)[.!\s]*$/i.test(text) ||
            /^(?:what|where|why|how|is|are|does|did)\b|^(?:can|could) you (?:tell|describe)/i.test(text) ||
            /^(?:暂停|停止|取消|重置|继续|谢谢|确认)[。！\s]*$|^(?:现在|目前).*(?:什么|哪里|状态|有没有|是否).*[？?]$/.test(text);
        if (independent) {
            this.clear();
            return { text, inputIds: [id] };
        }
        const previousText = this.fragments.map(x => x.text).join(' ');
        const continuation = /^(?:then|and|or|next|also|after that|before that)\b|^(?:please\s+)?(?:put|return|place|move)\s+it\b|^(?:然后|接着|再把|先把它|把它)/i.test(text) ||
            /\b(?:then|and|or|next|first)[.!?,;\s]*$/i.test(previousText) ||
            (unresolvedObjectChoice(previousText) && /^(?:first|please|put|return)\b/i.test(text));
        const replacement = /^(?:forget that|new task|instead|actually[, ]|换个任务|算了|改成)/i.test(text);
        if (replacement || now - this.updated > 45_000 ||
            (this.fragments.length && !this.fragments.some(x => x.id === id) && !text.startsWith(previousText) && !continuation))
            this.clear();
        const duplicate = this.fragments.findIndex(x => x.id === id);
        if (duplicate >= 0)
            this.fragments[duplicate] = { id, text };
        else if (text) {
            const previous = this.fragments.map(x => x.text).join(' ');
            // Transport recovery can repeat the complete request under a new item ID.
            if (previous && text.startsWith(previous))
                this.fragments = [{ id, text }];
            else if (!previous.endsWith(text))
                this.fragments.push({ id, text });
        }
        this.updated = now;
        if (this.fragments.length > 12 || this.fragments.map(x => x.text).join(' ').length > 2000) {
            this.clear();
            throw new Error('robot_request_evidence_limit: repeat the complete request');
        }
        return { text: this.fragments.map(x => x.text).join(' '), inputIds: this.fragments.map(x => x.id) };
    }
    settle(receipt) {
        if (['accepted', 'needs_clarification', 'needs_confirmation', 'scheduled', 'replaced',
            'clarification_cancelled', 'proposal_rejected', 'deferred_cancelled', 'unknown'].includes(String(receipt['status'])))
            this.clear();
    }
}
/** A specific unresolved choice is a gate, never permission to choose for the user. */
export function unresolvedObjectChoice(text) {
    const alternatives = /\b(?:bowl|wine bottle|bottle|cheese|plate)[\s,.;:!?]+or[\s,.;:!?]+(?:the\s+)?(?:bowl|wine bottle|bottle|cheese|plate)\b|(?:碗|酒瓶|奶酪|盘子)(?:或者|还是|或)(?:碗|酒瓶|奶酪|盘子)/i;
    return alternatives.test(text) && /\b(?:could mean|might mean|may mean|undecided|not sure|unsure|either)\b|还没决定|不确定|可能指|没选好/i.test(text);
}
/** Independent ASR finals retain their real microphone clock across transport replay. */
export class RobotAcousticEvidence {
    anchor;
    segments = [];
    episode;
    begin(audioMs, now = Date.now()) {
        if (!this.anchor || now - this.anchor.at > 45_000)
            this.anchor = { audioMs: Math.max(0, audioMs - 1200), at: now };
    }
    bindEpisode(episode) {
        if (typeof episode !== 'string')
            return;
        if (this.episode !== undefined && episode !== this.episode)
            this.clear();
        this.episode = episode;
    }
    add(event) {
        if (!event.text.trim() || event.audioStartMs === undefined || event.audioEndMs === undefined)
            return;
        if (this.segments.some(x => x.id === event.itemId))
            return;
        this.segments.push({ id: event.itemId, text: event.text.trim(), start: event.audioStartMs, end: event.audioEndMs });
        this.segments = this.segments.slice(-128);
    }
    recover(endMs, now = Date.now()) {
        if (!this.anchor || now - this.anchor.at > 45_000)
            return;
        const selected = this.segments.filter(x => x.end > this.anchor.audioMs && x.start <= endMs && x.end <= endMs + 500);
        if (!selected.length || endMs - selected.at(-1).end > 2500)
            return;
        const text = selected.map(x => x.text).join(' ');
        if (text.length > 2000)
            return;
        return { text, segmentIds: selected.map(x => x.id) };
    }
    settle(receipt) {
        if (['accepted', 'needs_clarification', 'needs_confirmation', 'scheduled', 'replaced', 'clarification_cancelled', 'proposal_rejected', 'deferred_cancelled', 'unknown'].includes(String(receipt['status'])))
            this.clear();
    }
    clear() { this.anchor = undefined; this.segments = []; }
}
