/** A processing status is not an authorization/question/tool acknowledgement. */
const KINDS=new Set(['execute','revise','amend','next_stage','finish','pause','resume','cancel','propose','clarify','defer','replace_deferred','cancel_deferred','qa','no_action','stop_speech','reply']);
export function isSubstantiveCompletion(event){
 return event.direction==='sent'&&event.type==='host.playback_completed'&&KINDS.has(event.replyKind);
}
