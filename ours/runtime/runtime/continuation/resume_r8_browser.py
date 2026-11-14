"""Resume only after the archived browser-driver defect, without replaying QA3."""
import json,subprocess,time
from continuation.chain_r8 import B,ROOT,NODE,launch,prepare96,record,score

def main():
 try:
  qa=ROOT/'R8/qa3'
  s=json.loads((qa/'qa3_r8_20261102/reports_audited/v1.9_wait45/summary.json').read_text())
  assert s['valid_for_audio_benchmark']and s['micro']['interaction']['passed']==3
  assert json.loads((ROOT/'deployment/DEPLOYMENT.json').read_text())['state']=='deployed'
  record('main_browser_audio_retry_after_driver_fix',prior_evidence=str(ROOT/'ui_main_audio_attempt1_early_driver_stop'))
  subprocess.run([NODE,str(B/'ui_acceptance/audio.mjs')],cwd=B,check=True)
  assert json.loads((ROOT/'ui_main_audio/RESULT.json').read_text())['passed']
  out=prepare96(qa);label='formal96_r8_20261102'
  launch(out,label,'audio_repair_96_R8_20261102')
  record('running96',directory=str(out/label),main_browser_verified=True)
  count=-1
  while not(out/label/'COMPLETED.json').exists():
   for marker in ['BLOCKED_CLOUD.json','INVALID_AUDIO_TIMING.json','ABORTED_IMPLEMENTATION.json']:
    if(out/label/marker).exists():raise RuntimeError('96_evidence_stop:'+marker)
   n=len(list((out/label/'cases').glob('*/verdict.json')))
   if n>0 and n!=count:score(out,label,False);count=n
   time.sleep(30)
  score(out,label);record('completed96',directory=str(out/label),main_browser_verified=True)
 except Exception as e:record('halted_for_evidence_review',error=repr(e));raise

if __name__=='__main__':main()
