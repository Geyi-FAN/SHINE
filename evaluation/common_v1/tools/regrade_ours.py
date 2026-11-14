import argparse,concurrent.futures,json,subprocess,sys,time,hashlib
from pathlib import Path
Q=Path(__file__).resolve().parents[1];N=Q.parent/'ours_full930_readiness_20261114';B=Q.parents[1]
def read(p):return json.loads(Path(p).read_text())
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def one(row,out):
 uid=row['trial_uid'];d=out/uid;d.mkdir(parents=True,exist_ok=False)
 case=Path(row['case_directory']);item=next(dict(x)for x in read(N/'CASE_REGISTRY370.private.json')if x['public_case_id']==row['case_id']);item.update(method='Ours',paired_trial_uid=uid)
 write(d/'ITEM.json',item)
 p=subprocess.run([sys.executable,'-B',str(Q/'common/score.py'),'--case',str(case),'--item',str(d/'ITEM.json'),'--out',str(d/'score')],capture_output=True,text=True)
 (d/'process.log').write_text(p.stdout+'\n'+p.stderr)
 score=read(d/'score/SCORE.json')if(d/'score/SCORE.json').exists()else{}
 result=dict(trial_uid=uid,branch=row['branch'],case_id=row['case_id'],returncode=p.returncode,old=row.get('scores'),score=score)
 write(d/'COMPARE.json',result);return result
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--mode',choices=['smoke','full'],required=True);a=p.parse_args();allrows=read(N/'runs/formal930_v1/PROGRESS.json')['rows'];rows=[x for x in allrows if x['branch']!='T6']
 if a.mode=='smoke':rows=[next(x for x in rows if x['branch']==b)for b in ['T1','T2','T3','T4','T5','T7','T8']]
 out=Q/'reports'/('ours_common_'+a.mode+'_'+__import__('os').environ.get('COMMON_CANDIDATE','r2'));out.mkdir(exist_ok=False);results=[]
 for r in rows:
  ans=one(r,out);results.append(ans);write(out/'PROGRESS.json',dict(planned=len(rows),completed=len(results),errors=sum(x['returncode']!=0 for x in results),rows=results))
  print(ans['branch'],ans['trial_uid'],ans['returncode'],{k:ans['score'].get(k)for k in ['interaction','target','instruction']},flush=True)
  if ans['returncode']!=0 and a.mode=='smoke':raise SystemExit('real-evidence smoke failed; raw Ours unchanged')
 write(out/'COMPLETED.json',dict(completed=len(results),errors=sum(x['returncode']!=0 for x in results),original_results_preserved=True))
