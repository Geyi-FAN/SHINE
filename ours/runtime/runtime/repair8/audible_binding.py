"""A transcript is audible only through its exact output key AND received PCM."""
import hashlib,wave
from pathlib import Path
def bound_output(payload,messages,directory=None):
 key=payload.get('receipt_key');digest=payload.get('audio_sha256')
 if not key or not digest:return []
 starts=[m for m in messages if m.get('direction')=='sent'and m.get('type')=='host.playback_started'and not m.get('bindingUpdate')]
 bound=[];seen=set()
 for start in starts:
  identity=(start.get('epoch'),start.get('outputId'))
  if identity in seen:continue
  related=[m for m in messages if(m.get('epoch'),m.get('outputId'))==identity and m.get('receiptKey')==key]
  if start.get('receiptKey')!=key and not related:continue
  if directory is not None:
   p=Path(directory)/'client'/('output_'+str(identity[0])+'_'+str(identity[1])+'.wav')
   try:
    with wave.open(str(p),'rb')as f:
     if f.getframerate()!=24000 or f.getnchannels()!=1 or f.getsampwidth()!=2:continue
     pcm=f.readframes(f.getnframes())
   except(OSError,wave.Error):continue
   if hashlib.sha256(pcm).hexdigest()!=digest:continue
  bound.append(dict(start,receiptKey=key,binding_method='exact_output_key_and_received_PCM_SHA256'if directory else'exact_output_key_only'));seen.add(identity)
 return bound
