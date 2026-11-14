"""Compare source PCM against independently recorded ASR receiver bytes/clocks."""
import hashlib,json,shutil,subprocess,time,wave
from pathlib import Path
def lines(p):return[json.loads(x)for x in p.read_text().splitlines()if x.strip()]if p.exists()else[]
def pcm(path):
 return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-f','s16le','-ar','16000','-ac','1','-'])
def stats(rows,count):
 times=[r['system_monotonic']for r in rows];return dict(frames=len(rows),max_gap_ms=max([1000*(b-a)for a,b in zip(times,times[1:])],default=0),duration_ratio=(times[-1]-times[0]+.02)/(count*.02)if times else None)
def audit(case,service):
 events=lines(case/'client/events.jsonl');ready=next((x for x in events if x['type']=='asr.ready'),None)
 if not ready:return dict(passed=False,reason='ASR_connection_not_established',clips=[])
 source=Path(service)/'sessions'/ready['session'];deadline=time.monotonic()+10
 while not(source/'received.wav').exists()and time.monotonic()<deadline:time.sleep(.1)
 if not(source/'received.wav').exists():return dict(passed=False,reason='independent_receiver_recording_missing',clips=[])
 archive=case/'asr_evidence';archive.mkdir(exist_ok=True)
 for name in ['received.wav','frames.jsonl','events.jsonl']:shutil.copy2(source/name,archive/name)
 with wave.open(str(archive/'received.wav'),'rb')as f:received=f.readframes(f.getnframes())
 arrivals=lines(archive/'frames.jsonl');rx=[];last=0
 for row in arrivals:
  end=int(row['total_samples'])*2;block=received[last:end];last=end
  if len(block)!=row['samples']*2:raise ValueError('receiver PCM length inconsistent with actual arrival log')
  rx.append(dict(sha256=hashlib.sha256(block).hexdigest(),system_monotonic=row['received'],samples=row['samples']))
 (case/'audio_received.jsonl').write_text(''.join(json.dumps(x)+'\n'for x in rx))
 start=0;results=[]
 for queued in [x for x in events if x['type']=='client.input_clip_queued']:
  clip=queued['clip_id'];original=queued.get('source_file');cfg=case/'qa_client.private.json'
  if original:expected=pcm(Path(original))
  elif cfg.exists():expected=Path(json.loads(cfg.read_text())['pcm_file']).read_bytes()
  else:raise ValueError('cannot verify clip source identity')
  expected_hashes=[]
  for i in range(0,len(expected),640):expected_hashes.append(hashlib.sha256(expected[i:i+640].ljust(640,b'\0')).hexdigest())
  position=None
  for i in range(start,max(start,len(rx)-len(expected_hashes)+1)):
   if[ x['sha256']for x in rx[i:i+len(expected_hashes)]]==expected_hashes:position=i;break
  actual=[]if position is None else rx[position:position+len(expected_hashes)]
  if position is not None:start=position+len(expected_hashes)
  sender=stats([x for x in events if x['type']=='client.input_frame'and x.get('clip_id')==clip],len(expected_hashes));receiver=stats(actual,len(expected_hashes))
  exact=len(actual)==len(expected_hashes)
  passed=exact and sender['frames']==len(expected_hashes)and all(x['duration_ratio']is not None and .95<=x['duration_ratio']<=1.05 and x['max_gap_ms']<100 for x in [sender,receiver])
  results.append(dict(clip_id=clip,source_file=original,source_pcm_sha256=hashlib.sha256(expected).hexdigest(),exact_received_pcm=exact,sender=sender,receiver=receiver,passed=passed))
 report=dict(schema='audio-clock-admission-v1',frame_ms=20,ratio_bounds=[.95,1.05],max_gap_ms=100,clips=results,passed=bool(results)and all(x['passed']for x in results),receiver_source=str(source),reference_text_used=False)
 (case/'AUDIO_QUALITY.json').write_text(json.dumps(report,indent=2));return report
