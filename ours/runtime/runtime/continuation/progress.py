"""Read-only experiment progress. No model/API calls or metric rewriting."""
import json,time,os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
def load(p):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return None
def update():
 rounds=[]
 runs=sorted(ROOT.glob('formal24_r3_*'))
 for version in sorted(ROOT.glob('R[45678]*')):
  if version.is_dir():
   runs+=sorted(version.glob('formal24_*'))+sorted((version/'expanded96').glob('formal96_*'))
   for special in version.glob('regression*'):runs+=sorted(special.glob('regression*_r6*'))
   for special in version.glob('qa3'):runs+=sorted(special.glob('qa3_r[78]*'))
 for run in runs:
  started=load(run/'STARTED.json')or{};cases=[]
  for d in sorted((run/'cases').glob('*')):
   result=load(d/'result.json');quality=load(d/'AUDIO_QUALITY.json');v=load(d/'verdict.json')or{};r=dict(case_id=d.name,completed=result is not None,audio_quality=None if not quality else quality['passed'],interaction=v.get('interaction'),target=v.get('target'),instruction=v.get('instruction'),errors=None if result is None else result.get('errors'),termination=None if result is None else result.get('termination'))
   if not result:
    f=d/'physical.jsonl'
    if f.exists():
     with f.open('rb')as stream:
      stream.seek(max(0,f.stat().st_size-32000));lines=stream.read().splitlines()
     if lines:
      try:
       s=json.loads(lines[-1]);r.update(mode=s['mode'],physics_step=s['step'],controls=s['policy_actions'])
      except ValueError:pass
   cases.append(r)
  status='aborted_implementation'if(run/'ABORTED_IMPLEMENTATION.json').exists()else'completed'if(run/'COMPLETED.json').exists()else'blocked_cloud'if(run/'BLOCKED_CLOUD.json').exists()else'invalid_audio'if(run/'INVALID_AUDIO_TIMING.json').exists()else'running_or_interrupted'
  rounds.append(dict(label=run.name,path=str(run),status=status,planned=started.get('cases'),finished=sum(c['completed']for c in cases),quality_passed=sum(c['audio_quality']is True for c in cases),cases=cases,summary=load(run/'reports/summary.json'),audited_summary_wait45=load(run/'reports_audited/v1.9_wait45/summary.json')or load(run/'reports_audited/v1.8_wait45/summary.json')or load(run/'reports_audited/v1.7_wait45/summary.json'),audited_summary_wait10=load(run/'reports_audited/v1.9_wait10/summary.json')or load(run/'reports_audited/v1.8_wait10/summary.json')or load(run/'reports_audited/v1.7_wait10/summary.json'),score_note='raw scorer and independently corrected applicability/receipt scores are separate; do not compare without scorer version'))
  rounds[-1]['primary_summary']=rounds[-1]['audited_summary_wait45']or rounds[-1]['summary']
  rounds[-1]['primary_score_revision']=(rounds[-1]['primary_summary']or{}).get('audit_revision','legacy raw; no independent audit available')
 output=dict(updated_beijing=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),active_chain=load(ROOT/'R8_FULL_CHAIN.json'),cloud_probe=load(ROOT/'CLOUD_RECOVERED.json'),rounds=rounds,production_8787=load(ROOT/'deployment/DEPLOYMENT.json')or'unchanged pending evidence-based acceptance',note='Use primary_summary / primary_score_revision. summary is retained legacy raw scoring, not the chosen v1.9 result. Partial counts are not final SR; old invalid rounds not pooled')
 p=ROOT/'reports/LIVE_AUDIO_PROGRESS.json';temp=p.with_name(p.name+'.'+str(os.getpid())+'.tmp');temp.write_text(json.dumps(output,ensure_ascii=False,indent=2));temp.replace(p)
 return output
if __name__=='__main__':
 import sys
 if '--watch'in sys.argv:
  while True:update();time.sleep(10)
 else:print(json.dumps(update(),ensure_ascii=False))
