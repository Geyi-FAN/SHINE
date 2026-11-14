"""Per-output speech ownership; preserve legacy aggregate playback callbacks."""
from pathlib import Path
B=Path(__file__).resolve().parents[1]
MAIN=Path('/mnt/disk_2/geyi/voice_pi05_harness/vendor/Qwen-Live-Harness/packages/qwen-live-harness/src')
def one(s,a,b):
 assert s.count(a)==1,(a[:90],s.count(a));return s.replace(a,b)
def host(p):
 s=p.read_text();ts=p.suffix=='.ts'
 marker='  private playbackStartedNotified = false;'if ts else'    playbackStartedNotified = false;'
 s=one(s,marker,marker+('\n  private readonly perOutputStarted = new Set<number>();'if ts else'\n    perOutputStarted = new Set();'))
 if ts:
  a='  onPlaybackStarted?: (call: { epoch: number }) => void;'
  s=one(s,a,a+'\n  onOutputPlaybackStarted?: (call: {epoch:number;outputId:number}) => void;')
 a='    if (this.playbackStartedNotified) return;'if ts else'        if (this.playbackStartedNotified)\n            return;'
 add="""if (!this.perOutputStarted.has(message.outputId)) {
      this.perOutputStarted.add(message.outputId);
      this.handlers.onOutputPlaybackStarted?.({epoch:call.epoch,outputId:message.outputId});
    }
    """
 s=one(s,a,('    'if ts else'        ')+add+a.lstrip())
 a='    this.outputAudio.delete(outputId);'if ts else'        this.outputAudio.delete(outputId);'
 s=one(s,a,a+'\n        this.perOutputStarted.delete(outputId);')
 a='    this.outputAudio.clear();'if ts else'        this.outputAudio.clear();'
 s=one(s,a,a+'\n        this.perOutputStarted.clear();');p.write_text(s)
def daemon(p):
 s=p.read_text();a='onPlaybackStarted: (call) => {'
 s=one(s,a,"onOutputPlaybackStarted: (call) => {\n        session.outputPlaybackStarted(call);\n      },\n      "+a);p.write_text(s)
def session(p):
 s=p.read_text();ts=p.suffix=='.ts';s="import { createHash as speechAudioHash } from 'node:crypto';\n"+s
 if ts:s=one(s,'interface IsolatedResultSpeech {','interface IsolatedResultSpeech {\n  outputId?:number;\n  receiptKey?:string;')
 a='    /** LiveCallHandlers.onPlaybackStarted */'if not ts else'  /** LiveCallHandlers.onPlaybackStarted */'
 method="""
  outputPlaybackStarted(CALL) {
    const context=this.active;
    if(!context || context.epoch!==call.epoch || context.stopping || context.playbackSuppressed || this.host.isOutputMuted?.()===true)return;
    const speech=context.resultSpeech;
    if(!speech?.audioForwarded || speech.outputId!==call.outputId)return;
    speech.playbackStarted=true;
    if(context.activeSearchResult && context.activeSearchResult.taskId===speech.searchId)context.activeSearchResult.playbackStarted=true;
    if(context.activePeerReport && context.activePeerReport.id===speech.reportId)context.activePeerReport.playbackStarted=true;
    this.log.write('realtime.protocol',{type:'robot.result_speech',phase:'playback_started',purpose:speech.purpose,id:speech.id,outputId:call.outputId,receiptKey:speech.receiptKey});
  }
""".replace('CALL','call: {epoch:number;outputId:number}'if ts else'call')
 s=one(s,a,method+a)
 a='if (context.resultSpeech?.audioForwarded)\n'+('      'if ts else'            ')+'context.resultSpeech.playbackStarted = true;'
 s=one(s,a,a.replace('context.resultSpeech?.audioForwarded','context.resultSpeech?.audioForwarded && context.resultSpeech.outputId === undefined'))
 a='if (context.resultSpeech?.audioForwarded)\n'+('      'if ts else'            ')+'context.resultSpeech.playbackCompleted = true;'
 s=one(s,a,a.replace('context.resultSpeech?.audioForwarded','context.resultSpeech?.audioForwarded && (context.resultSpeech.outputId === undefined || context.resultSpeech.outputId === call.outputId)'))
 # Aggregate callbacks remain for fallback/legacy speech; bound results use their own start.
 start=s.index('playbackStarted(call');end=s.index('playbackCompleted(call',start)
 part=s[start:end];part=part.replace('if (report?.audioForwarded) {','if (report?.audioForwarded && !(context.resultSpeech?.reportId === report.id && context.resultSpeech?.outputId !== undefined)) {').replace('if (search?.audioForwarded) {','if (search?.audioForwarded && !(context.resultSpeech?.searchId === search.taskId && context.resultSpeech?.outputId !== undefined)) {');s=s[:start]+part+s[end:]
 # The key is known before sending any bytes, the output ID is bound before yielding.
 a="source: 'isolated_result',"
 s=one(s,a,a+"\n                receipt_key: state.receiptKey,\n                result_speech_id: state.id,\n                audio_sha256: speechAudioHash('sha256').update(result.audio).digest('hex'),")
 at=s.index(a);at=s.rfind("this.log.write('transcript.assistant', {",0,at)
 s=s[:at]+"state.receiptKey=JSON.stringify(['isolated_result',context.callId,state.id,state.purpose]);\n            "+s[at:]
 a='state.audioForwarded = true;'
 code="""if(offset===0){
          state.outputId=this.host.tagOutputAudio?.(context.epoch,{receiptKey:state.receiptKey,text:result.transcript,source:'isolated_result'});
          if(state.outputId===undefined)throw new Error('isolated_output_binding_unavailable');
        }
        """
 pos=s.index(a,s.index("source: 'isolated_result',"));s=s[:pos]+code+s[pos:]
 # Retain the external20/40s scoring deadlines; allow queued audio to acquire a real start.
 a='1000) + 5000);'
 if ts:
  a=') + 5000,'
 assert s.count(a)==1,(a,s.count(a));s=s.replace(a,a.replace('5000','15000'))
 p.write_text(s)
def main():
 roots=[B/'artifacts/repair8_audio_daemon/dist',MAIN]
 for root in roots:
  ext='.ts'if root==MAIN else'.js'
  host(root/('host/qwen-live-harness-host-coordinator'+ext));daemon(root/('daemon'+ext));session(root/('orchestrator/live-session'+ext))
if __name__=='__main__':main()
