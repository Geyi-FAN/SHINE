/** Read-only speech classification. This module never plans or dispatches an action. */
export function robotTaskQuestionKind(question) {
    const q = question.trim().replace(/[。.!！?？]+$/u, '').trim();
    if (/\bthen\s+(?:put|place|move|open|close|return)\b|然后|再把/iu.test(q))
        return undefined;
    if (/^(?:please\s+)?where\s+(?:are|were)\s+you\s+(?:taking|putting|placing|moving)\s+.{1,80}$/iu.test(q) ||
        /^(?:请问|请你|告诉我|你|现在|目前|正|正在|打算|准备|要|会|把|将)*(?:碗|奶酪|酒瓶|它|这个|那个).{0,10}(?:放|拿|搬|移|送).{0,10}(?:哪里|哪儿|什么地方)$/u.test(q))
        return 'destination';
    if (/^(?:what\s+are\s+you\s+doing(?:\s+(?:now|right\s+now))?|what(?:'s|\s+is)\s+(?:the\s+)?(?:current\s+)?task(?:\s+(?:now|right\s+now))?)$/iu.test(q) ||
        /^(?:请问|请你|告诉我|你|现在|目前|当前|正在|在)*(?:做什么|执行什么任务|做什么任务|任务是什么)$/u.test(q))
        return 'task';
    return undefined;
}
export function robotReadOnlyQuestion(text) {
    if (robotTaskQuestionKind(text))
        return true;
    return /^(?:what|where|why|how|is|are|does|do|has|have)\b/iu.test(text.trim()) ||
        /吗|呢[?？。]?\s*$|什么|哪里|哪儿|是否|有没有|怎么|如何/u.test(text);
}
/** Keep the model's destination answer; remove stale present-tense action wording. */
export function completedTaskAnswer(question, answer, status) {
    if (!robotTaskQuestionKind(question) || status?.['state'] !== 'completed' ||
        !status['task_id'] || !status['instruction'])
        return undefined;
    const revised = answer.replace(/^(?:(?:我|机器人|机械臂)(?:现在)?|现在)?正在(?:执行)?/u, '本次任务的目标是');
    return revised !== answer ? revised : undefined;
}
