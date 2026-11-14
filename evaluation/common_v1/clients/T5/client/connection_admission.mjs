/** Retry only a task-free pre-audio connection. Never replay user audio. */
export function canRetryConnection({attempt,maxAttempts,turns,snapshot,detail=''}){
 if(attempt>=maxAttempts||turns||!snapshot)return false;
 if(snapshot.task_id||snapshot.state!=='idle'||(snapshot.policy_action_steps||0)!==0)return false;
 if(snapshot.pending_proposal||snapshot.pending_clarification||snapshot.deferred_task)return false;
 if(/access denied|insufficient|quota|rate.limit|invalid.api.key|unauthori[sz]ed/i.test(detail))return false;
 return /handshake|connect|voice readiness|socket|disconnected|voice_start_timeout/i.test(detail);
}

export async function connectBeforeAudio({create,snapshot,turnCount,archive,record,
 maxAttempts=3,sleep=ms=>new Promise(r=>setTimeout(r,ms))}){
 for(let attempt=1;attempt<=maxAttempts;attempt++){
  if(turnCount())throw Error('Pre-audio retry is forbidden after a user clip');
  const before=await snapshot();
  if(before.task_id||before.state!=='idle'||(before.policy_action_steps||0)!==0)
   throw Error('Pre-audio connection requires a task-free idle scene');
  const connection=create(attempt);const started=Date.now()/1000;
  try{
   await connection.connect();
   const after=await snapshot();
   if(after.task_id||after.state!=='idle'||turnCount())throw Error('Scene changed during pre-audio admission');
   record({attempt,started,ended:Date.now()/1000,ready:true,task_audio_clips:0});
   return connection;
  }catch(error){
   connection.close();await connection.flush();
   const after=await snapshot();
   const detail=String(error.message||error)+' '+String(connection.preAudioError||'')+' '+String(await connection.getPrivateTransportFailure?.()||'');
   const retry=canRetryConnection({attempt,maxAttempts,turns:turnCount(),snapshot:after,detail});
   record({attempt,started,ended:Date.now()/1000,ready:false,detail,retry,task_audio_clips:turnCount()});
   await archive(attempt);
   if(!retry)throw error;
   await sleep(attempt*2000);
  }
 }
 throw Error('Pre-audio admission exhausted');
}
