"""After formal collection: fixed-QA first judge + fixed-denominator tables.

No model rollout or output generation is retried. This daemon is read-only
except for new scoring/export directories and calls the frozen offline judge.
"""
from pathlib import Path
import sys,json,stat,time,subprocess,hashlib,csv,collections
Q=Path(__file__).resolve().parents[1];B=Q.parents[1];N=Q.parent/'ours_full930_readiness_20261114';OLD=Q.parent/'ours_final_c3r_20261110';J=OLD/'finalization_20261111/frozen_judge'
sys.path.insert(0,str(Q.parent/'c3r_cloud04_240_20261108/tools'));from remote import connect
F=Q/'finalization/formal1770_v1'
def read(p):return json.loads(Path(p).read_text())
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def fetch_file(s,p):p.parent.mkdir(parents=True,exist_ok=True);s.get(str(p),str(p))
def run(args,name):
 (F/'logs').mkdir(parents=True,exist_ok=True)
 with(F/'logs'/name).open('x')as f:subprocess.run([sys.executable,'-I','-S']+args,stdout=f,stderr=f,check=True)
def main():
 if F.exists():assert read(F/'STATUS.json')['phase']=='waiting_for_complete_formal1770','Do not restart an already begun judge'
 F.mkdir(parents=True,exist_ok=True);save(F/'STATUS.json',dict(phase='waiting_for_complete_formal1770',no_rollout_retry=True))
 while True:
  c=connect();s=c.open_sftp()
  try:
   status=json.loads(s.open(str(Q/'runs/formal1770_v1/COMPLETED.json')).read())
  except OSError:s.close();c.close();time.sleep(30);continue
  if status['phase']=='stopped' or status['completed']!=1770:
   s.close();c.close();raise RuntimeError('Formal cohort stopped/incomplete; no automatic semantic grading or case replacement')
  break
 fetch_file(s,Q/'runs/formal1770_v1/PROGRESS.json');rows=read(Q/'runs/formal1770_v1/PROGRESS.json')['rows']
 assert len(rows)==1770
 qa=[x for x in rows if x['branch']=='T6'];assert len(qa)==90
 # Restore fixed dataset order for anonymous indices, independent of outcome.
 order={x['case_id']:i for i,x in enumerate(read(B/'T6/current/dataset/selected90.private.json'))};qa.sort(key=lambda x:order[x['case_id']])
 evidence=[];controls=[];audits=[]
 for index,row in enumerate(qa,1):
  case=Path(row['directory'])
  for f in ['EVIDENCE.json','CONTROL_AUDIT.json','DELIVERY_AUDIT.json','OUTCOME.json']:
   fetch_file(s,case/f)
  ev=read(case/'EVIDENCE.json');ev['index']=index
  for frame in ev['frames']:
   p=Path(frame['image']);fetch_file(s,p);assert hashlib.sha256(p.read_bytes()).hexdigest()==frame['sha256']
  evidence.append(ev);controls.append(read(case/'CONTROL_AUDIT.json'));audits.append(read(case/'DELIVERY_AUDIT.json'))
 save(F/'EVIDENCE90.private.json',evidence);save(F/'CONTROL90.private.json',controls);save(F/'DELIVERY90.json',audits)
 for name in s.listdir(str(Q/'reports')):
  if name.startswith('ours_common_full_'):
   for filename in ['PROGRESS.json','COMPLETED.json']:fetch_file(s,Q/'reports'/name/filename)
 fetch_file(s,Q/'plans/FROZEN.json')
 s.close();c.close()
 # Original Ours fixed judge hashes are mandatory; no silent prompt changes.
 for path,digest in read(N/'FORMAL_RUN_LOCK.json')['offline_judge_files'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
 run([str(J/'prepare_judge_inputs.py'),'--evidence',str(F/'EVIDENCE90.private.json'),'--control',str(F/'CONTROL90.private.json'),'--fixture',str(OLD/'finalization_20261111/FIXTURE_LOCAL.private.json'),'--out',str(F/'judge_inputs90')],'prepare_qa.log')
 idx=F/'judge_inputs90/SCORING_INDEX.private.json'
 run([str(J/'judge_fixed.py'),'--index',str(idx),'--out',str(F/'judge90_first')],'judge90_first.log')
 save(F/'STATUS.json',dict(phase='collected1770_first_QA_judged90',judge='GLM-4.6V v4/r3',original_Ours_and_legacy_scores_preserved=True,judgment_dir=str(F/'judge90_first'),at=time.time()))
 from export_new_table import export
 export()
 print('1770 collection preserved,90 new B1 first frozen-model judgments completed',flush=True)
if __name__=='__main__':
 try:main()
 except BaseException as e:save(F/'ERROR.json',dict(type=type(e).__name__,reason=str(e),at=time.time()));raise
