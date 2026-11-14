/** Explicit control only: no plan/subgoal, no guessed object or task ID. */
const namedCancel=/^(?:please\s+)?(?:cancel|skip)\s+(?:the\s+)?(.+?)\s+task[.!]*(?:\s*(?:keep going|carry on|keep working)[.!]*)?$/i;
const chineseCancel=/^\s*(?:请)?取消([\u4e00-\u9fff]{1,5}?)(?:的)?任务[。.!！]*(?:\s*(?:keep going|carry on|继续|继续当前任务)[。.!！]*)?\s*$/i;
const entities={bowl:/\bbowl\b|碗/i,cheese:/\b(?:cream\s+)?cheese\b|奶油奶酪|奶酪|芝士/i,bottle:/\b(?:wine\s+)?bottle\b|酒瓶/i,plate:/\bplate\b|盘子|盘|碟子/i,drawer:/\bdrawer\b|抽屉/i,stove:/\bstove\b|炉灶|炉子|炉台|灶台/i,cabinet:/\bcabinet\b|柜子|柜顶/i};
function subject(text){return (namedCancel.exec(text.trim())??chineseCancel.exec(text.trim()))?.[1];}
export function explicitNamedPendingCancel(text){return typeof text==='string'&&!/[?？"“”「」]/.test(text)&&!/^\s*(?:please )?(?:do not|don't|never)\b|不要|别取消|如果|是否/i.test(text)&&!!subject(text);}
export function pendingCancellationQuestion(text,status,inputId){
    const slot=status?.deferred_task,q=slot?.cancel_clarification;
    if(!explicitNamedPendingCancel(text)||!status?.ready||!q||slot.state!=='update_pending'||
       slot.episode_id!==status.episode_id||slot.predecessor_task_id!==status.task_id||
       slot.dispatch_blocked_by_input!==inputId||slot.update_utterance!==text||
       q.schema!=='pending_cancel_clarification.v1'||q.episode_id!==status.episode_id||
       q.predecessor_task_id!==status.task_id||q.deferred_id!==slot.deferred_id||
       q.input_id!==inputId||q.original_transcript!==text||q.pending_task_cancelled!==false||
       q.state!=='awaiting_explicit_task_reference'||typeof q.question!=='string'||
       !(q.expires_at>Date.now()/1000))return;
    return{text:q.question,binding:{inputId,episodeId:status.episode_id,taskId:status.task_id,
      deferredId:slot.deferred_id,originalText:text}};
}
export function pendingCancelArguments(text,status,inputId,audioEvidence){
    if(!explicitNamedPendingCancel(text)||!status?.ready||!['running','verifying','completed'].includes(status.state))return;
    const pending=status.deferred_task;
    if(!pending||pending.state!=='update_pending'||pending.episode_id!==status.episode_id||
       pending.predecessor_task_id!==status.task_id||pending.dispatch_blocked_by_input!==inputId||
       pending.update_utterance!==text||!pending.deferred_id||pending.transaction_id!==pending.deferred_id||
       !Number.isInteger(pending.transaction_revision)||pending.transaction_revision<1||
       !status.task_id||!Number.isInteger(status.task_version))return;
    let phrase=text;
    const direct=subject(phrase);
    // An explicit queue scope names the one actual waiting slot, not an object
    // spelling correction. The same transaction/input/version guards above apply.
    if(/^(?:queued|waiting|pending|next)$/i.test(direct))
        return{episode_id:status.episode_id,expected_task_version:status.task_version,deferred_id:pending.deferred_id};
    if(!Object.values(entities).some(re=>re.test(direct))){
        // The server has already validated THIS input and installed its fence.
        // The alternative is used only to reject active/pending ambiguity.
        if(!audioEvidence||audioEvidence.primary!==text||audioEvidence.reference_sent!==false||audioEvidence.scene_sent!==false||
           !['audio_only_grounding.v2','audio_only_relisten.v1'].includes(audioEvidence.kind)||
           !explicitNamedPendingCancel(audioEvidence.transcript))return;
        phrase=audioEvidence.transcript;
    }
    const noun=subject(phrase);
    const selected=Object.entries(entities).filter(([,re])=>re.test(noun));
    if(selected.length!==1)return;
    const re=selected[0][1];
    if(!re.test(pending.instruction)||re.test(status.instruction||''))return;
    return{episode_id:status.episode_id,expected_task_version:status.task_version,deferred_id:pending.deferred_id};
}
