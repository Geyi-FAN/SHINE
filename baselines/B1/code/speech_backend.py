"""Real synthesis of Agent-authored text; no task planning or action tools."""
import os,base64,importlib.util,json,time,wave,threading
from pathlib import Path
R=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('existing_tts','/mnt/disk_2/geyi/voice_pi05_harness/scripts/audio_switch_benchmark/tts.py');tts=importlib.util.module_from_spec(spec);spec.loader.exec_module(tts)
_session=None;_lock=threading.Lock()
def prepare():
 """Warm one tool-free synthesis session before admitting evaluation audio."""
 global _session
 if _session is not None:return
 from websockets.sync.client import connect
 cfg=json.loads((R/'config/MODELS.json').read_text())['tts']
 ws=connect('wss://dashscope.aliyuncs.com/api-ws/v1/realtime?model='+cfg['model'],additional_headers={'Authorization':'Bearer '+Path(os.environ['COMMON_TTS_KEY_FILE']).read_text().strip()},open_timeout=20,close_timeout=3)
 def until(kind):
  while True:
   e=json.loads(ws.recv(timeout=20))
   if e.get('type')=='error':raise RuntimeError('TTS provider error: '+str(e.get('error',{}).get('code')))
   if e.get('type')==kind:return e
 until('session.created')
 ws.send(json.dumps(dict(type='session.update',session=dict(modalities=['text','audio'],audio=dict(input=dict(format=dict(type='pcm',sample_rate=16000)),output=dict(voice=cfg['voice'],format=dict(type='pcm',sample_rate=24000))),turn_detection=None,tools=[],instructions='You are only a speech synthesizer. Read ONLY the latest supplied JSON sentence verbatim. Do not answer, translate, execute, add words, or repeat earlier sentences.'))))
 until('session.updated');_session=ws

def close():
 global _session
 if _session is not None:_session.close();_session=None

def synthesize(text,out):
 cfg=json.loads((R/'config/MODELS.json').read_text())['tts'];started=time.monotonic()
 with _lock:
  prepare();ws=_session;chunks=[];transcripts=[]
  ws.send(json.dumps({'type':'conversation.item.create','item':{'type':'message','role':'user','content':[{'type':'input_text','text':'Read only the sentence inside this JSON string, verbatim: '+json.dumps(text,ensure_ascii=False)}]}}))
  while True:
   e=json.loads(ws.recv(timeout=20))
   if e.get('type')=='error':raise RuntimeError('TTS provider error')
   if e.get('type')=='conversation.item.created':break
  ws.send(json.dumps({'type':'response.create','response':{'modalities':['text','audio']}}))
  while True:
   e=json.loads(ws.recv(timeout=20));kind=e.get('type')
   if kind=='error':raise RuntimeError('TTS provider error')
   if kind in ['response.audio.delta','response.output_audio.delta']:chunks.append(base64.b64decode(e['delta']))
   if kind in ['response.audio_transcript.done','response.output_audio_transcript.done']:transcripts.append(e.get('transcript',''))
   if kind=='response.done':
    if e.get('response',{}).get('status')not in [None,'completed']:raise RuntimeError('Incomplete TTS response')
    break
   if time.monotonic()-started>90:raise TimeoutError('TTS request deadline')
  pcm=b''.join(chunks);spoken=''.join(transcripts);elapsed=time.monotonic()-started
 if not pcm or len(pcm)%2:raise RuntimeError('Empty or malformed real PCM')
 if tts.norm(text)!=tts.norm(spoken):raise ValueError('TTS changed the Agent reply; no mismatched audio released')
 Path(out).parent.mkdir(parents=True,exist_ok=True)
 with wave.open(str(out),'wb')as f:f.setnchannels(1);f.setsampwidth(2);f.setframerate(24000);f.writeframes(pcm)
 return dict(text=text,provider_transcript=spoken,seconds=elapsed,samples=len(pcm)//2,path=str(out),model=cfg['model'],voice=cfg['voice'])
