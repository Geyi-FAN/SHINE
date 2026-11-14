"""Read-only, incrementally regrade all available B0 results into a NEW tree."""
import concurrent.futures,hashlib,json,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[1];D=Path('/mnt/disk_4/geyi/audio_switch_benchmark/experiments');SIM='/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python'
items={x['public_case_id']:x for x in json.loads((R/'data/CASES_PRIVATE.json').read_text())};O=R/'reports/regraded_B0_v3';O.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
jobs=[]
for source in [D/'asr_direct_T2_T8_20261108',D/'asr_direct_pi05_formal_20261108']:
 if not source.exists():continue
 for old in sorted(list((source/'runs').glob('*/cases/*/SCORE.json'))+list((source/'runs').glob('T1_120/trials/*/score.json'))):
  if source.name.endswith('T2_T8_20261108')and not old.parent.parent.parent.name.startswith('formal'):continue
  case=old.parent
  if not(case/'result.json').exists():continue
  if old.name=='SCORE.json'and not(case/'ATTEMPT_OUTCOME.json').exists():continue
  a=read(case/'ATTEMPT_OUTCOME.json')if(case/'ATTEMPT_OUTCOME.json').exists()else {};cid=a.get('case_id',read(case/'result.json').get('case_id'))
  if cid not in items or items[cid]['branch']=='T6':continue
  jobs.append((case,old,items[cid],source.name))
def work(job):
 case,old,item,source=job;out=O/source/case.parent.parent.name/case.name;out.mkdir(parents=True,exist_ok=True);dest=out/'SCORE_V3.json';ip=out/'ITEM.private.json';sources=[case/'result.json',old];before={str(x):digest(x)for x in sources}
 if not dest.exists():
  ip.write_text(json.dumps(item));p=subprocess.run([SIM,'-B',str(R/'scoring_v3/score.py'),'--case',str(case),'--item',str(ip),'--legacy',str(old),'--out',str(dest)],capture_output=True,text=True)
  (out/'scoring.log').write_text(p.stdout+p.stderr)
  if p.returncode:return dict(case=str(case),branch=item['branch'],error=p.stderr[-2000:])
 if before!={str(x):digest(x)for x in sources}:raise RuntimeError('source_changed:'+str(case))
 v=read(dest);row=dict(case=str(case),branch=item['branch'],case_id=item['public_case_id'],old_target=v.get('legacy_target'),new_target=v.get('target'),old_instruction=v.get('legacy_instruction'),new_instruction=v.get('instruction'),interaction=v.get('interaction'),score=str(dest),source_sha256=before)
 (out/'PROVENANCE.json').write_text(json.dumps(row,indent=2));return row
rows=[]
with concurrent.futures.ThreadPoolExecutor(4)as ex:
 for v in ex.map(work,jobs):
  rows.append(v)
  if len(rows)%40==0:print('REGRADED',len(rows),'/',len(jobs),flush=True)
summary=dict(created=time.time(),registered=len(jobs),finished=len(rows),errors=[x for x in rows if'error'in x],all_original_results_preserved=True,scoring_version='audio-causal-attribution-v3-20261109',by_branch={})
for b in ['T1','T2','T3','T4','T5','T7','T8']:
 xs=[x for x in rows if x['branch']==b and'error'not in x];summary['by_branch'][b]=dict(cases=len(xs),old_target=sum(x['old_target']=='pass'for x in xs),new_target=sum(x['new_target']=='pass'for x in xs),changed=sum(x['new_target']!=x['old_target']for x in xs),old_instruction=sum(x['old_instruction']=='pass'for x in xs),new_instruction=sum(x['new_instruction']=='pass'for x in xs))
(O/'CASES.json').write_text(json.dumps(rows,indent=2));(O/'SUMMARY.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2),flush=True)
