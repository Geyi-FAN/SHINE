"""Causal PCM receiver: no task ids, scripts, object lists or reference prompts."""
import argparse,asyncio,hashlib,json,time,wave,uuid
from pathlib import Path
import numpy as np
import torch
import websockets
from transformers import WhisperProcessor,WhisperForConditionalGeneration
from silero_vad import load_silero_vad,VADIterator

async def main(a):
 torch.set_num_threads(2)
 torch.cuda.set_per_process_memory_fraction(.25)
 processor=WhisperProcessor.from_pretrained(a.model,local_files_only=True)
 model=WhisperForConditionalGeneration.from_pretrained(a.model,torch_dtype=torch.float16,local_files_only=True,attn_implementation='sdpa').to('cuda').eval()
 def decode(pcm):
  audio=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
  inputs=processor(audio,sampling_rate=16000,return_tensors='pt',return_attention_mask=True)
  with torch.inference_mode():
   ids=model.generate(input_features=inputs.input_features.to('cuda',dtype=torch.float16),attention_mask=inputs.attention_mask.to('cuda'),language='english',task='transcribe',num_beams=5,do_sample=False,max_new_tokens=256)
  return processor.batch_decode(ids,skip_special_tokens=True)[0]
 decode(np.zeros(16000,dtype='<i2').tobytes())
 vad_model=load_silero_vad();lock=asyncio.Lock();client_lock=asyncio.Lock()
 vad_warm_iterator=VADIterator(vad_model,sampling_rate=16000,min_silence_duration_ms=400,speech_pad_ms=0)
 for _ in range(64):
  with torch.no_grad():vad_warm_iterator(torch.zeros(512,dtype=torch.float32),return_seconds=False)
 vad_warm_iterator.reset_states()
 a.out.mkdir(parents=True,exist_ok=True)
 meta={'ready':True,'model_path':str(a.model),'model':'openai/whisper-large-v3','dtype':'float16','beam':5,'device':'cuda','sample_rate':16000,'reference_prompt':None,'vad':'silero-vad','min_silence_ms':400,'pre_roll_ms':200,'gpu_memory_fraction':.25,'transport_revision':'r2_memory_clock_logs_SSD; neural_decode_unchanged'}
 (a.out/'READY.json').write_text(json.dumps(meta,indent=2));print('ASR_READY',flush=True)
 async def handle(ws,path=None):
  if client_lock.locked():await ws.close(code=1013,reason='one live audio session at a time');return
  async with client_lock:
   token=uuid.uuid4().hex;directory=a.out/'sessions'/token;directory.mkdir(parents=True)
   vad=VADIterator(vad_model,sampling_rate=16000,min_silence_duration_ms=400,speech_pad_ms=0)
   audio=bytearray();pending=bytearray();active=None;consumed=0;tasks=[];segment=0;event_rows=[];frame_rows=[]
   def record(kind,**kw):
    row={'kind':kind,'time':time.monotonic(),'wall_time':time.time(),**kw};event_rows.append(row);return row
   async def submit(start,end,reason):
    nonlocal segment
    if end-start<1600:return
    segment+=1;sid=segment;data=bytes(audio[start*2:end*2]);record('segment_finalized',segment=sid,start_sample=start,end_sample=end,reason=reason)
    async def work():
     async with lock:
      begin=time.monotonic();text=await asyncio.to_thread(decode,data);event=record('transcript',segment=sid,text=text,asr_latency_s=time.monotonic()-begin,segment_sha256=hashlib.sha256(data).hexdigest(),reason=reason)
      await ws.send(json.dumps(event))
    tasks.append(asyncio.create_task(work()))
   await ws.send(json.dumps({'kind':'ready','session':token,'metadata':meta}))
   try:
    async for message in ws:
     if isinstance(message,bytes):
      if len(message)%2 or len(message)>6400:raise ValueError('invalid PCM frame')
      arrived=time.monotonic();audio.extend(message);pending.extend(message);frame_rows.append({'received':arrived,'samples':len(message)//2,'total_samples':len(audio)//2})
      while len(pending)>=1024:
       block=bytes(pending[:1024]);del pending[:1024];consumed+=512
       with torch.no_grad():event=vad(torch.from_numpy(np.frombuffer(block,dtype='<i2').astype(np.float32)/32768),return_seconds=False)
       if event and 'start' in event:
        active=max(0,event['start']-3200);record('speech_start',sample=active)
       if event and 'end' in event and active is not None:
        await submit(active,min(consumed,event['end']+1600),'vad_silence');active=None
       if active is not None and consumed-active>30*16000:raise ValueError('speech exceeds 30 s; no partial command execution')
     else:
      control=json.loads(message)
      if set(control)!={'kind'}:raise ValueError('control metadata is forbidden')
      if control.get('kind')=='end':
       if active is not None:await submit(active,len(audio)//2,'transport_end_flush');active=None
       if tasks:await asyncio.gather(*tasks)
       record('input_end',samples=len(audio)//2,pcm_sha256=hashlib.sha256(audio).hexdigest(),segments=segment)
       await ws.send(json.dumps({'kind':'done','session':token,'segments':segment,'samples':len(audio)//2,'pcm_sha256':hashlib.sha256(audio).hexdigest()}));break
      else:raise ValueError('only end control allowed; no task metadata')
   except Exception as exc:
    record('error',type=type(exc).__name__,detail=str(exc))
    for t in tasks:t.cancel()
    raise
   finally:
    with wave.open(str(directory/'received.wav'),'wb') as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(16000);f.writeframes(audio)
    (directory/'events.jsonl').write_text(''.join(json.dumps(x)+'\n'for x in event_rows));(directory/'frames.jsonl').write_text(''.join(json.dumps(x)+'\n'for x in frame_rows));vad.reset_states()
 async with websockets.serve(handle,'127.0.0.1',a.port,max_size=1<<20,max_queue=64,ping_interval=20):await asyncio.Future()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--model',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--port',type=int,default=49440);asyncio.run(main(p.parse_args()))
