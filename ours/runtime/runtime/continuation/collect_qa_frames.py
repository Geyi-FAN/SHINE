"""Copy exact hash-bound visual requests into their case's replay evidence.

The legacy web host writes new captures beside its frozen code. Existing
frozen files are never edited; case-local copies remove global-path ambiguity.
"""
import hashlib,json,shutil
from pathlib import Path
B=Path(__file__).resolve().parents[1]
def collect(directory):
 directory=Path(directory);requests=[]
 for f in(directory/'voice/sessions').glob('*.jsonl'):
  for line in f.open():
   try:e=json.loads(line)
   except ValueError:continue
   if e.get('type')=='visual.analysis'and e.get('payload',{}).get('event')=='robot_visual.request':requests.append(e['payload'])
 if not requests:return
 destination=directory/'qa_frames';destination.mkdir(exist_ok=True);wanted={r['image_sha256']for r in requests};rows=[]
 for f in(B/'freeze/voice/data/visual_captures').glob('*.jpg'):
  h=hashlib.sha256(f.read_bytes()).hexdigest()
  if h not in wanted:continue
  target=destination/(h+'.jpg');shutil.copy2(f,target);rows.append(dict(image_sha256=h,file=str(target),capture_time=f.stat().st_mtime,requests=[r for r in requests if r['image_sha256']==h]))
 (destination/'manifest.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
