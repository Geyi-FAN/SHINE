"""Typed infrastructure evidence within the actual trial window, not cleanup."""
import json
from pathlib import Path

def records(path):
 try:
  text=Path(path).read_text()
 except OSError:return []
 result=[]
 for line in text.splitlines():
  try:result.append(json.loads(line))
  except ValueError:pass
 return result

def provider_failure(case,started_at,finished_at):
 found=[]
 for f in(Path(case)/'voice/logs').glob('*errors*.jsonl'):
  for e in records(f):
   t=e.get('ts')/1000 if isinstance(e.get('ts'),(float,int))else e.get('time')
   if not isinstance(t,(float,int)):continue
   if not started_at<=t<=finished_at:continue
   p=e.get('payload')or{};message=str(p.get('message',''))
   if p.get('source')=='realtime'and(p.get('closeCode')==1007 or'1007'in message and'Access denied'in message):
    found.append(dict(time=t,code='realtime_account_access_denied',close_code=1007,source_file=str(f)))
 return found

def delivered_audio(case):
 # Turn metadata may be created BEFORE the first packet is sent. It cannot
 # prove delivery. Count packet events or server-side received PCM evidence.
 events=records(Path(case)/'client/events.jsonl')
 packets=[e for e in events if e.get('type')=='client.input_frame']
 server_received=any(isinstance(e.get('samples'),int)and e['samples']>0
                     and e.get('source')=='daemon_accepted_frame_before_onInputAudio'
                     for e in records(Path(case)/'audio_received.jsonl'))
 return dict(started=bool(packets or server_received),client_frames=len(packets),server_pcm_logged=server_received)

def must_stop_dispatch(attempt):
 return bool(attempt.get('provider_failure')or attempt.get('input_contract_invalid')or
             attempt.get('infrastructure_error'))
