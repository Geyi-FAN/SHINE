"""Bind received WAV to the actual host output, never borrow an isolated TTS hash.
A streamed robot_reply has no generated-PCM receipt hash: record received hash
and explicit weaker provenance instead of pretending one existed.
"""
import json,wave,hashlib
from pathlib import Path

def lines(p):return [json.loads(s)for s in Path(p).read_text().splitlines()if s.strip()]if Path(p).exists()else []
def bind(directory):
 d=Path(directory);from audio_aliases import canonical_events;events,aliases=canonical_events(d);starts=[x for x in events if x.get('type')=='client.input_clip_start'];ends=[x for x in events if x.get('type')=='client.input_clip_end']
 if len(starts)>1:raise ValueError('question replay forbidden')
 if not starts:return dict(qa_started=False,outputs=[],binding_errors=[],scoring_status='setup_unavailable')
 end=ends[-1]['time']if ends else None;voice=[v for f in(d/'voice/sessions').glob('*.jsonl')for v in lines(f)];outputs=[];errors=[];seen_receipts={}
 for receipt in events:
  if receipt.get('type')!='host.output_audio_receipt' or receipt['time']<starts[0]['time']:continue
  epoch,oid=receipt.get('epoch'),receipt.get('outputId');key=(epoch,oid)
  if key in seen_receipts:
   prior=seen_receipts[key];identity=lambda r:tuple(r.get(k)for k in ['text','source','receiptKey','inputId'])
   if identity(prior)!=identity(receipt):errors.append(dict(key=key,reason='conflicting_output_receipt'))
   continue
  seen_receipts[key]=receipt
  same=lambda x:x.get('epoch')==epoch and x.get('outputId')==oid
  def find(kind):return next((x for x in events if x.get('type')==kind and same(x)),None)
  p=d/'client'/f'output_{epoch}_{oid}.wav';pcm=b'';samples=0;fmt=False
  if p.exists():
   with wave.open(str(p))as f:samples=f.getnframes();fmt=f.getframerate()==24000 and f.getnchannels()==1 and f.getsampwidth()==2;pcm=f.readframes(samples)
  actual=hashlib.sha256(pcm).hexdigest();rk=receipt.get('receiptKey');expected=None;matching=[]
  if rk:matching=[x.get('payload',{})for x in voice if x.get('type')=='transcript.assistant'and x.get('payload',{}).get('receipt_key')==rk and x.get('payload',{}).get('text')==receipt.get('text')]
  if matching:expected=matching[-1].get('audio_sha256')
  # Never locate expected hashes only by nearby time or outputId.
  isolated=receipt.get('source')=='isolated_result' or bool(rk)
  hash_valid=(bool(expected)and actual==expected)if isolated else True
  first=find('client.output_first_pcm');start=find('client.output_clocked_start');done=find('client.output_clocked_complete');host_done=find('host.output_audio_finished');ack=find('host.playback_completed');began=find('host.playback_started')
  text=receipt.get('text','');valid=bool(fmt and samples>0 and any(pcm)and text and start and done and host_done and ack and began and done.get('samples')==samples and host_done.get('expectedSamples')==samples and ack.get('samples')==samples and hash_valid)
  if isolated and not hash_valid:errors.append(dict(key=key,reason='isolated_receipt_PCM_mismatch_or_missing'))
  outputs.append(dict(epoch=epoch,output_id=oid,text=text,audio_file=str(p),wav_samples=samples,valid_clocked_complete=valid,first_pcm_latency_s=(first or start or {}).get('time',0)-end if end and(first or start)else None,completion_latency_s=done['time']-end if end and done else None,audibility_evidence=dict(kind='exact_receipt_key_generated_and_received_PCM'if isolated else'direct_stream_host_text_binding_and_received_PCM_only',receipt_key=rk,sha256=actual,generated_pcm_sha256=expected,generated_hash_available=bool(expected)),input_id=receipt.get('inputId'),output_source=receipt.get('source'),independent_output_ASR_completed=False))
 return dict(qa_started=True,audio_ended=end,outputs=outputs,binding_errors=errors,metadata_aliases=aliases,scoring_status='pending_semantic_judge',output_sink='clocked_pcm_receiver_not_physical_speaker',semantic_correct=None)
if __name__=='__main__':
 import sys
 r=bind(sys.argv[1]);Path(sys.argv[2]).write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(outputs=len(r['outputs']),valid=sum(x['valid_clocked_complete']for x in r['outputs']),binding_errors=r['binding_errors'])))
