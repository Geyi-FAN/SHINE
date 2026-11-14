"""Finish18, verify all3 QA repairs, idle main acceptance, then new full96.

Functional deployment is distinct from deadline scoring: a correct but >45s
handoff remains a failed benchmark case and is recorded in FUNCTIONAL_GATE.
"""
import hashlib,json,shutil,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python';NODE=str(B/'freeze/voice/runtime/node-v22.23.3-linux-x64/bin/node')
REGROOT=ROOT/'R6/regression18b';REG=REGROOT/'regression18_r6b_20261102'
def record(state,**kw):
 (ROOT/'R8_FULL_CHAIN.json').write_text(json.dumps(dict(time=time.time(),state=state,**kw),indent=2));print(state,kw,flush=True)
def wait_round(run):
 while not(run/'COMPLETED.json').exists():
  for marker in ['BLOCKED_CLOUD.json','INVALID_AUDIO_TIMING.json','ABORTED_IMPLEMENTATION.json']:
   if(run/marker).exists():raise RuntimeError('evidence_stop:'+str(run/marker))
  time.sleep(10)
def score(root,label,final=True):
 for seconds in [10,45]:subprocess.run([SIM,'-m','repair8.score','--root',str(root),'--label',label,'--waiting',str(seconds),*(['--final']if final else[])],cwd=B,check=True)
def launch(root,label,session):
 command=f'cd {B} && AUDIO_REPAIR_EXECUTION_GPU=4 AUDIO_REPAIR_POLICY_PORT=19866 AUDIO_REPAIR_OUT={root} exec {SIM} -u -m repair8.run --label {label} > {root}/console.log 2>&1'
 subprocess.run(['tmux','new-session','-d','-s',session,command],check=True)
def prepare96(parent):
 out=ROOT/'R8/expanded96';out.mkdir(exist_ok=False);shutil.copytree(ROOT/'expanded96/dataset',out/'dataset')
 for name in ['initial_states.json','physical_v2.5.0-candidate.frozen.json']:shutil.copy2(parent/'dataset'/name,out/'dataset'/name)
 protocol=json.loads((parent/'dataset/PROTOCOL.json').read_text());protocol['setup']['predecessor_input']='mixed_source_setup_declared_by_case_id_before_run';protocol['setup']['source_audio_case_ids']=[c['case_id']for c in json.loads((ROOT/'R5b/dataset/selected.private.json').read_text())];protocol['setup']['method']='original24 cohort retains the identical reviewed source audio; other scripts use public text authorization + same model actual execution for unscored source; all scored turns reviewed real-time PCM; no hidden pose writes/resets'
 (out/'dataset/PROTOCOL.json').write_text(json.dumps(protocol,indent=2));cases=json.loads((out/'dataset/selected.private.json').read_text());assert len(cases)==96 and sum(c['private_contract']['physical_eligible']for c in cases)==81
 manifest=json.loads((parent/'FREEZE.json').read_text())
 for p,h in manifest['files'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
 for p in(out/'dataset').glob('*.json'):manifest['files'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 manifest.update(revision='R8-expanded96',time=time.time(),evaluation='32scripts x3states; original24 cohort retains identical reviewed source audio, other source setups public text; no prefix pooling; same frozen QA3 runtime; primary45s/supplementary10s waiting; action/geometry budgets unchanged',out_of_training_goal=['T4_04_S1','T4_04_S2','T4_04_S3'])
 (out/'FREEZE.json').write_text(json.dumps(manifest,indent=2));return out
def main():
 try:
  record('waiting_for_complete18_and_R7_engineering');wait_round(REG)
  while not(ROOT/'R8_READY_TO_FREEZE.json').exists():time.sleep(10)
  score(REGROOT,REG.name)
  vs=json.loads((REG/'reports_audited/v1.9_wait45/verdicts.json').read_text())
  bad=[]
  for v in vs:
   if v['category']=='T6':continue
   failure=[c['name']for c in v['checks']if c['status']!='pass']
   if failure and set(failure)!={'handoff_after_independent_predecessor_success'}:bad.append(dict(case_id=v['case_id'],failures=failure))
  if bad:record('needs_unresolved_functional_review',failures=bad);return
  subprocess.run([SIM,'-m','repair8.prepare'],cwd=B,check=True);qa=ROOT/'R8/qa3';label='qa3_r8_20261102';launch(qa,label,'audio_repair_QA3_R8_20261102');record('running_QA3_audio',directory=str(qa/label));wait_round(qa/label);score(qa,label)
  s=json.loads((qa/label/'reports_audited/v1.9_wait45/summary.json').read_text())
  if not s['valid_for_audio_benchmark']or s['micro']['interaction']['passed']!=3:record('needs_actual_QA_audio_review',summary=s);return
  subprocess.run([SIM,'-m','ui_acceptance.prepare_profile'],cwd=B,check=True);subprocess.run([SIM,'-m','ui_acceptance.deploy'],cwd=B,check=True)
  deployed=json.loads((ROOT/'deployment/DEPLOYMENT.json').read_text()).get('state')=='deployed'
  if deployed:
   record('main_deployed_running_browser_audio');subprocess.run([NODE,str(B/'ui_acceptance/audio.mjs')],cwd=B,check=True)
   if not json.loads((ROOT/'ui_main_audio/RESULT.json').read_text())['passed']:raise RuntimeError('main_browser_audio_failed')
  else:record('main_active_preserved_acceptance_deferred')
  out=prepare96(qa);label='formal96_r8_20261102';launch(out,label,'audio_repair_96_R8_20261102');record('running96',directory=str(out/label),main_browser_verified=deployed)
  count=-1
  while not(out/label/'COMPLETED.json').exists():
   for marker in ['BLOCKED_CLOUD.json','INVALID_AUDIO_TIMING.json','ABORTED_IMPLEMENTATION.json']:
    if(out/label/marker).exists():raise RuntimeError('96_evidence_stop:'+marker)
   n=len(list((out/label/'cases').glob('*/verdict.json')))
   if n>0 and n!=count:score(out,label,False);count=n
   time.sleep(30)
  score(out,label);record('completed96',directory=str(out/label),main_browser_verified=deployed)
 except Exception as e:record('halted_for_evidence_review',error=repr(e));raise
if __name__=='__main__':main()
