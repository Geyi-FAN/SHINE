/** Bounded bilingual control grammar; never creates a manipulation goal. */
const normalize = (text) => text.normalize('NFKC').toLowerCase().replace(/’/g, "'").trim();
const polite = '(?:(?:please|请你?|麻烦你?|嗯|好的?|那)\\s*)*';
const end = '[.!。！\\s]*';
const pauseAtom = new RegExp('^' + polite + '(?:stop|pause|暂停|停下|停止|停一下)(?:\\s*(?:(?:the|的|current)\\s*)?(?:robot|arm|task|机器人|机械臂|任务))?(?:\\s*(?:一下|now|please))?' + end + '$', 'i');
export function currentResumeReference(text) {
    const t = normalize(text);
    if (/[?？"“”「」]|\b(?:not|never|don't|completed|finished|yesterday|earlier|former|first)\b|不要|别|不能|已经完成|昨天|上上|上一个/.test(t))
        return false;
    const reference = '(?:(?:(?:the|that)\\s+)?(?:(?:same|current|paused)\\s+)?task|the\\s+task\\s+you\\s+were\\s+doing|(?:刚才|当前|之前|原来)?(?:那个|那一个|同一个|相同的|的)*任务|(?:the\\s+)?(?:same|current)\\s*任务|(?:刚才|当前|同一个)(?:的)?\\s*task)';
    return new RegExp('^' + polite + '(?:continue|resume|继续|恢复)\\s*' + reference + '(?:\\s*(?:吧|please))?' + end + '$', 'i').test(t);
}
export function mixedControlIntent(text) {
    const t = normalize(text);
    if (!t)
        return;
    if (/(?:不要|别|不能|不许)\s*(?:stop|pause|resume|continue|暂停|停止|恢复|继续|取消)|\b(?:don't|do not|never)\s*(?:暂停|停下|停止|恢复|继续)/.test(t))
        return 'protected';
    if (/[?？"“”「」]|\b(?:what|why|if|unless|means?|said|say)\b|如果|是否|什么意思/.test(t))
        return;
    if (/(?:完成|结束).*(?:后|再).*(?:stop|pause)|\b(?:after|when|once|until)\b.*(?:暂停|停下|停止)/.test(t))
        return 'deferred_stop';
    if (/^(?:请)?取消\s*(?:waiting|queued|deferred)\s*(?:task|任务)[.!。！\s]*$/.test(t))
        return 'cancel_waiting';
    const clauses = t.split(/[,，;；]+/).map(s => s.trim()).filter(Boolean);
    if (clauses.length > 0 && clauses.length <= 2 && clauses.every(s => pauseAtom.test(s)))
        return 'pause';
    if (currentResumeReference(t))
        return 'resume';
    return;
}
