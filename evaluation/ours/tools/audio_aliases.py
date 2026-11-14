"""Recognize ONLY proven same-PCM terminal metadata aliases; never merge outputs."""
import hashlib,json,wave
from pathlib import Path

def read_lines(p):return [json.loads(s)for s in Path(p).read_text().splitlines()if s.strip()]if Path(p).exists()else[]
def canonical_events(directory):
 d=Path(directory);events=read_lines(d/'client/events.jsonl');starts=[e['time']for e in events if e.get('type')=='client.input_clip_start']
 if not starts:return events,[]
 groups={}
 for i,e in enumerate(events):
  if e.get('type')=='host.output_audio_receipt'and e['time']>=starts[0]:groups.setdefault((e.get('epoch'),e.get('outputId')),[]).append((i,e))
 aliases=[];omit=set();voice=None
 for key,group in groups.items():
  if len(group)!=2:continue
  (i,first),(j,last)=group
  if first.get('source')!='isolated_result'or last.get('source')!='fresh_terminal_receipt'or not first.get('text')or first['text']!=last.get('text')or last['time']<first['time']:continue
  try:rk=json.loads(first['receiptKey'])
  except(ValueError,KeyError,TypeError):continue
  if not isinstance(rk,list)or len(rk)!=4 or rk[0]!='isolated_result':continue
  wav=d/'client'/f'output_{key[0]}_{key[1]}.wav'
  if not wav.exists():continue
  try:
   with wave.open(str(wav))as w:
    samples=w.getnframes();valid_format=w.getframerate()==24000 and w.getnchannels()==1 and w.getsampwidth()==2;pcm=w.readframes(samples)
  except(wave.Error,OSError):continue
  if not valid_format or not samples or not any(pcm)or last.get('expectedSamples')!=samples or not 0<first.get('expectedSamples',0)<=samples:continue
  if voice is None:voice=[r for f in(d/'voice/sessions').glob('*.jsonl')for r in read_lines(f)]
  hashes={v.get('payload',{}).get('audio_sha256')for v in voice if v.get('type')=='transcript.assistant'and v.get('payload',{}).get('receipt_key')==first.get('receiptKey')and v.get('payload',{}).get('text')==first['text']}
  digest=hashlib.sha256(pcm).hexdigest()
  if hashes!={digest}:continue
  same=lambda e:e.get('epoch')==key[0]and e.get('outputId')==key[1]
  receipts={kind:[e for e in events if e.get('type')==kind and same(e)]for kind in ['client.output_clocked_start','client.output_clocked_complete','host.output_audio_finished','host.playback_completed','host.playback_started']}
  if any(len(v)>1 for v in receipts.values()) or len(receipts['host.output_audio_finished'])!=1:continue
  finish=receipts['host.output_audio_finished'][0]
  if finish.get('expectedSamples')!=samples or finish['time']<last['time']:continue
  if any(v and v[0].get('samples')!=samples for k,v in receipts.items()if k in ['client.output_clocked_complete','host.playback_completed']):continue
  complete=all(len(v)==1 for v in receipts.values())
  cancelled=[e for e in events if e.get('type')=='client.output_cancelled'and same(e)]
  # A late, unrelated notice may be cancelled at the fixed observation boundary.
  # Its identity is still provable; its incomplete-playback flag must stay false.
  if not complete and len(cancelled)!=1:continue
  omit.add(j);aliases.append(dict(epoch=key[0],output_id=key[1],reason='same_PCM_terminal_evidence_alias',canonical_receipt=first,terminal_annotation=last,received_generated_pcm_sha256=digest,full_samples=samples,observed_clock_receipts_unambiguous=True,playback_complete=complete,cancelled=cancelled,not_a_second_audio=True))
 return [e for i,e in enumerate(events)if i not in omit],aliases
