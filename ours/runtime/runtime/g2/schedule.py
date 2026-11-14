"""Fixed preregistered order; preserve first attempt, no best-of selection."""
import argparse,concurrent.futures,json,os,subprocess,sys,time
from pathlib import Path
B=Path(__file__).resolve().parents[1];PY='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
CASES=json.loads((B/'g2/fixed32.json').read_text());slots=[(4,19866),(5,19867),(6,19868),(7,19869)]
args=argparse.ArgumentParser();args.add_argument('--label',default='G2_fixed32_v2');args.add_argument('--natural',action='store_true');options=args.parse_args()
if options.natural:
 selected=json.loads((B/'g2/natural8.json').read_text())['cases'];CASES=[c for c in CASES if c['case_id']in selected]
runroot=B/'runs'/options.label;runroot.mkdir(parents=True,exist_ok=True);reportroot=B/'reports'/options.label;reportroot.mkdir(parents=True,exist_ok=True);logroot=B/'logs'/options.label;logroot.mkdir(parents=True,exist_ok=True)
def worker(slot):
 gpu,port=slots[slot];results=[]
 for i in range(slot,len(CASES),len(slots)):
  case=CASES[i];out=runroot/case['case_id'];log=logroot/(case['case_id']+'.log')
  if out.exists():raise RuntimeError('First attempt already exists: '+str(out))
  cmd=[PY,'-u',str(B/'g2/run_case.py'),'--case-id',case['case_id'],'--out',str(out),'--port',str(port),'--gpu',str(gpu)]
  if options.natural:cmd.append('--natural-source')
  with log.open('w')as f:p=subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,cwd=str(B),timeout=1800 if options.natural else 1300)
  result=json.loads((out/'result.json').read_text())if(out/'result.json').exists()else dict(case_id=case['case_id'],status='launch_or_environment_error',success=False,log=str(log))
  score=result.get('metrics',{}).get('instruction_adjusted',{}).get('success',False)
  item=dict(case_id=case['case_id'],group=case['group'],status=result['status'],success=score,returncode=p.returncode,seconds=result.get('seconds'));results.append(item)
  with(reportroot/'completed_cases.jsonl').open('a')as f:f.write(json.dumps(item)+'\n')
  print(json.dumps(item),flush=True)
 return results
with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:results=sum(list(pool.map(worker,range(4))),[])
(reportroot/'batch_complete.json').write_text(json.dumps(dict(cases=len(results),results=results,completed_unix=time.time()),indent=2)+'\n')
