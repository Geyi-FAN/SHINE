"""Evidence-gated 18 -> idle deployment/browser -> full96, one cloud session.

This orchestrator is outside the frozen runtime. It never edits a running
method or retries a failed case. Any regression failure halts for inspection.
"""
import hashlib,json,os,shutil,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1]
ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
NODE=str(B/'freeze/voice/runtime/node-v22.23.3-linux-x64/bin/node')
REGROOT=ROOT/'R6/regression18b';REG=REGROOT/'regression18_r6b_20261102'

def record(state,**kw):
 p=ROOT/'R6_FULL_CHAIN.json';p.write_text(json.dumps(dict(time=time.time(),state=state,**kw),indent=2));print(state,kw,flush=True)

def score(root,label,final=False):
 for seconds in [10,45]:
  subprocess.run([SIM,'-m','continuation.audited_score','--root',str(root),'--label',label,'--waiting',str(seconds),*(['--final']if final else[])],cwd=B,check=True)

def prepare96():
 out=ROOT/'R6/expanded96';out.mkdir(exist_ok=False);shutil.copytree(ROOT/'expanded96/dataset',out/'dataset')
 for name in ['initial_states.json','physical_v2.5.0-candidate.frozen.json']:
  shutil.copy2(REGROOT/'dataset'/name,out/'dataset'/name)
 protocol=json.loads((REGROOT/'dataset/PROTOCOL.json').read_text());protocol['setup']['predecessor_input']='unscored_public_text_policy_execution';protocol['setup']['method']='same policy actual execution after public text task authorization; all scored user turns reviewed real-time PCM; no hidden pose write or reset'
 (out/'dataset/PROTOCOL.json').write_text(json.dumps(protocol,indent=2))
 cases=json.loads((out/'dataset/selected.private.json').read_text());assert len(cases)==96 and sum(c['private_contract']['physical_eligible']for c in cases)==81
 manifest=json.loads((REGROOT/'FREEZE.json').read_text())
 for p,h in manifest['files'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
 for p in list((out/'dataset').glob('*.json'))+[B/'continuation/audited_score.py',B/'continuation/test_audited_score.py',B/'continuation/run96.py']:
  manifest['files'][str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
 manifest.update(time=time.time(),revision='R6-expanded96-frozen-runtime',evaluation='32scripts x3 states, no pooling; unscored source preparation is public text;45s and10s waiting scores both reported; physical denominator81; after-result facade wait removed,30s cloud cooldown preserved',out_of_training_goal=['T4_04_S1','T4_04_S2','T4_04_S3'])
 (out/'FREEZE.json').write_text(json.dumps(manifest,indent=2));return out

def main():
 record('waiting_for_complete_repair18')
 while not(REG/'COMPLETED.json').exists():
  for marker in ['INVALID_AUDIO_TIMING.json','BLOCKED_CLOUD.json','ABORTED_IMPLEMENTATION.json']:
   if(REG/marker).exists():record('halted_regression_evidence',marker=marker);return
  time.sleep(10)
 score(REGROOT,REG.name,True)
 s=json.loads((REG/'reports_audited/v1.7_wait45/summary.json').read_text());v=json.loads((REG/'reports_audited/v1.7_wait45/verdicts.json').read_text())
 bad=[dict(case_id=x['case_id'],failures=[c['name']for c in x['checks']if c['status']!='pass'])for x in v if x['interaction']!='pass']
 if not s['valid_for_audio_benchmark']or bad:record('needs_actual_audio_failure_review',failures=bad);return
 record('repair18_passed_preparing_main_idle_acceptance')
 subprocess.run([SIM,'-m','ui_acceptance.prepare_profile'],cwd=B,check=True)
 subprocess.run([SIM,'-m','ui_acceptance.deploy'],cwd=B,check=True)
 deployed=json.loads((ROOT/'deployment/DEPLOYMENT.json').read_text()).get('state')=='deployed'
 if deployed:
  subprocess.run([NODE,str(B/'ui_acceptance/audio.mjs')],cwd=B,check=True)
  assert json.loads((ROOT/'ui_main_audio/RESULT.json').read_text())['passed']
  record('main_audio_verified_starting96')
 else:record('main_user_active_preserved_starting96',note='No existing task or voice session interrupted; main acceptance deferred')
 out=prepare96();label='formal96_r6b_20261102'
 command=f'cd {B} && AUDIO_REPAIR_EXECUTION_GPU=4 AUDIO_REPAIR_POLICY_PORT=19866 AUDIO_REPAIR_OUT={out} exec {SIM} -u -m continuation.run96 --label {label} > {out}/console.log 2>&1'
 subprocess.run(['tmux','new-session','-d','-s','audio_repair_96_R6b_20261102',command],check=True)
 record('running96',directory=str(out/label),main_browser_audio_passed=deployed)
 count=-1
 while not(out/label/'COMPLETED.json').exists():
  for marker in ['INVALID_AUDIO_TIMING.json','BLOCKED_CLOUD.json','ABORTED_IMPLEMENTATION.json']:
   if(out/label/marker).exists():record('halted96_input_or_infrastructure',marker=marker);return
  now=len(list((out/label/'cases').glob('*/verdict.json')))
  if now!=count and now>0:score(out,label);count=now
  time.sleep(30)
 score(out,label,True);record('complete96',directory=str(out/label),main_browser_audio_passed=deployed)

if __name__=='__main__':main()
