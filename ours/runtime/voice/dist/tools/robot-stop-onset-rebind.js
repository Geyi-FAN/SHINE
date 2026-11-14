/** A final standalone Stop may have a VAD start in the preceding silence.
 * Rebind only to a separately observed, fresh PRIMARY speech onset, retaining
 * that onset's original robot identity. Never fetch a newer identity at commit.
 */
export function rebindSilentStopLease(context,event,now=Date.now()) {
    const old=context.independentStopLeases?.at(-1), primary=context.fastStopOnsets?.at(-1);
    const end=event.audioEndMs, audioNow=(context.fastStopAudioBytes??0)/32;
    if(!old||old.itemId!==event.itemId||old.used||!primary||!primary.identity||
       !Number.isFinite(end)||!Number.isFinite(primary.audioMs)||
       !Number.isFinite(event.audioStartMs)||end-event.audioStartMs<4000||
       old.audioMs>primary.audioMs-1500||primary.audioMs<event.audioStartMs||
       end-primary.audioMs<0||end-primary.audioMs>2400||
       audioNow-end < -500||audioNow-end>3000||now-event.receivedAt>3000||
       now-primary.startedAt>4000||primary.version!==context.taskInputVersion||
       primary.generation!==context.realtimeGeneration)return;
    const lease={...old,version:primary.version,generation:primary.generation,
      startedAt:primary.startedAt,audioMs:primary.audioMs,identity:primary.identity,
      reboundFromAudioMs:old.audioMs,reboundFromVersion:old.version};
    context.independentStopLeases[context.independentStopLeases.length-1]=lease;
    return lease;
}
