// Evaluation-side selection only; no reference text is sent to the Agent.
export function selectAudio(all,script){
 const rows=all.filter(a=>a.acoustic_condition===script.acoustic_condition&&a.family_id===script.family_id);
 if(!rows.length||new Set(rows.map(a=>a.utterance_id)).size!==rows.length)throw Error('Invalid acoustic/family binding');
 for(const r of rows)if(script.audio_hashes[r.utterance_id]!==r.sha256)throw Error('Authored audio hash mismatch');
 return rows;
}
export function explicitCancellationReply(text){
 text=String(text||'').replace(/hasn't/gi,'has not').replace(/haven't/gi,'have not').replace(/can't/gi,'cannot');
 return /(?:cancelled|canceled|cancel(?:lation)? (?:is |was |has been )?(?:confirmed|complete)|已取消|已经取消|取消了|请求.{0,5}取消|已撤销|(?:已|已经)拒绝.{0,12}(?:待确认|请求|任务)|(?:rejected|declined).{0,20}(?:pending (?:request|task)|proposal))/i.test(text)&&!/(?:not (?:been )?(?:cancel|reject|declin)|cannot (?:cancel|reject|declin)|unable to (?:cancel|reject|declin)|没有取消|未取消|无法取消|取消失败|未拒绝|没有拒绝|无法拒绝|未能拒绝)/i.test(text);
}
