"""Complete new engineering block; then all10 first attempts, never pooled."""
import hashlib,json,subprocess,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];PY='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
ids=['T3R2_S02_V0_I00','T3SELECT_REF_T03_C0_T01_I00','T3R2_S07_V0_I00'];label='probe3_v6_account_restored'
subprocess.run([PY,'-m','unittest','entryfix.test_entry','entryfix.test_support','entryfix.test_lifecycle','selected_eval.test_adapters'],cwd=B,check=True)
subprocess.run([PY,str(B/'entryfix/freeze.py')],cwd=B,check=True)
subprocess.run([PY,'-u',str(B/'selected_eval/run.py'),'--ids',','.join(ids),'--label',label],cwd=B,check=True)
missing=[i for i in ids if not(B/'runs'/label/i/'verdict.json').exists()]
if missing:
 (B/'reports/PROBE_GATE.json').write_text(json.dumps(dict(time=time.time(),version=label,passed=False,status='incomplete_block',unattempted_or_missing=missing,note='No formal10 admission; inspect cloud/infrastructure log; do not treat missing cases as successes'),indent=2))
 raise SystemExit('Engineering block incomplete; formal10 remains blocked')
vs=[json.loads((B/'runs'/label/i/'verdict.json').read_text())for i in ids]
gate=dict(time=time.time(),version=label,ids=ids,interaction=[v['interaction']for v in vs],target=[v['target']for v in vs],passed=all(v['interaction']=='pass'for v in vs),scope='engineering only; not pooled with formal10')
(B/'reports/PROBE_GATE.json').write_text(json.dumps(gate,indent=2));print(json.dumps(gate),flush=True)
if gate['passed']:
 subprocess.run([PY,'-u',str(B/'selected_eval/run.py'),'--label','formal10'],cwd=B,check=True)
 print('FORMAL10_ALL_FINISHED',flush=True)
