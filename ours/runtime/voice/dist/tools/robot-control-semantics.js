import {mixedControlIntent} from './robot-mixed-control.js';
/** Only full standalone controls. This module never generates manipulation goals. */
export function controlIntent(text) {
    const t = text.trim().toLowerCase().replace(/’/g, "'");
    if (!t)
        return;
    if (/\b(?:don't|do not|never|must not)\s+(?:stop|pause|cancel|resume)\b|不要停|别停|不要暂停|不能停/.test(t))
        return 'protected';
    if (/\b(?:what|why|means?|said|says|suppose|if|unless)\b|如果|假如|是否|什么意思/.test(t) && /stop|pause|cancel|暂停|停止|取消/.test(t))
        return 'protected';
    // A trailing keep-until clause does not delay a separate leading Stop.
    if (/^(?:please\s+)?(?:stop|pause)(?:\s+(?:the\s+)?(?:robot|arm|task))?[.!。！]+\s*(?:(?:first|then|please|instead)\s*[,，:]?\s+)*(?:put|place|return|open|close|turn|push|move|take)\b/.test(t))
        return undefined;
    if (/\b(?:stop|pause)\b.*\b(?:after|once|when|until)\b|\b(?:after|once|when)\b.*\b(?:stop|pause)\b|完成.*(?:后|再).*(?:停|暂停)/.test(t))
        return 'deferred_stop';
    const mixed=mixedControlIntent(t);if(mixed)return mixed;
    // A hold-only tail preserves current grasp; it does not locate, pick up,
    // place, release or otherwise manipulate the noun mentioned by ASR.
    // Negations, questions, conditionals and deferred stops were rejected above.
    if (/^(?:please\s+)?(?:stop|pause)(?:\s+(?:the\s+)?(?:current\s+)?(?:robot|arm|task|motion|execution))?(?:\s+now)?\s*[,;.!]?\s+(?:and\s+)?keep\s+(?:(?:the\s+)?(?:queued|waiting|deferred)\s+task\s+(?:waiting|pending|queued)|holding\s+(?:it|(?:the\s+)?(?:bowl|ball|cream cheese|cheese|wine bottle|bottle|object))|(?:the\s+)?(?:gripper|hand)\s+(?:still|in place)|(?:your|the current)\s+position)[.!\s]*$/i.test(t))
        return 'pause';
    if (/^(?:please\s+)?(?:cancel|remove|delete)\s+(?:(?:the|my|this)\s+)?(?:waiting|queued|deferred)\s+task[.!\s]*$|^(?:请)?取消(?:等待|排队|后续)任务[。！\s]*$/.test(t))
        return 'cancel_waiting';
    if (/^(?:please\s+)?(?:cancel|abort)\s+(?:(?:the|my|this|current)\s+)*(?:task|job|execution)[.!\s]*$|^(?:请)?取消(?:当前)?任务[。！\s]*$/.test(t))
        return 'cancel';
    if (/^(?:please\s+)?(?:stop|pause|halt)\s+(?:now|immediately|first)[.!。！\s]*$/.test(t))
        return 'pause';
    if (/^(?:(?:please|hey|okay|ok)\s*[,!.]?\s*)?(?:(?:hold\s+on|wait\s+(?:a\s+)?(?:moment|second))\s*[,!.]?\s*)?(?:please\s+)?(?:stop|pause)(?:\s+(?:the\s+)?(?:robot|arm|task|motion|execution))?(?:\s+please)?[.!\s]*$|^(?:please\s+)?hold\s+on[.!\s]*$/.test(t))
        return 'pause';
    if (/^(?:can|could|would)\s+you\s+(?:please\s+)?(?:stop|pause)(?:\s+the\s+(?:robot|arm|task))?[?.!\s]*$/.test(t))
        return 'pause';
    if (/^(?:请你?|麻烦你)?(?:现在|先)?(?:暂停|停下|停止|停一下|别动)(?:一下|当前任务|机械臂|任务)?[。！\s]*$/.test(t))
        return 'pause';
    if (/^(?:please\s+)?(?:resume|continue)(?:\s+(?:the\s+)?(?:same|current)\s+task|\s+the\s+task\s+you\s+were\s+doing)?[.!\s]*$|^go\s+ahead\s+and\s+carry\s+on\s+with\s+the\s+task\s+you\s+paused[.!\s]*$|^(?:请)?继续(?:刚才的|当前|原来)?任务[。！\s]*$/.test(t))
        return 'resume';
    return undefined;
}
export function controlToolAllowed(intent, name) {
    const controls = new Set(['robot_pause', 'robot_resume', 'robot_cancel_task','robot_cancel_deferred']);
    const expected = { pause: 'robot_pause', resume: 'robot_resume', cancel: 'robot_cancel_task', cancel_waiting: 'robot_cancel_deferred' };
    if (intent && expected[intent])
        return !(controls.has(name) || new Set(['robot_start_task','robot_revise_task','robot_restore_task','robot_propose_task','robot_resolve_proposal','robot_schedule_task','robot_replace_deferred','robot_answer_clarification']).has(name)) || name === expected[intent];
    return !((intent === 'protected' || intent === 'deferred_stop') && controls.has(name));
}
