"""Invoke original independent per-category judges; never changes input evidence."""
import sys,json,importlib.util,subprocess,hashlib
from pathlib import Path
D=Path('/mnt/disk_4/geyi/audio_switch_benchmark');Q=D/'deployments/ours_full930_readiness_20261114';R=D/'regressions/c3r_pi05_70_serial_20261108'
def read(p):return json.loads(Path(p).read_text())
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def main():
 cid=sys.argv[1];case=Path(sys.argv[2]);out=Path(sys.argv[3]);item=next(x for x in read(Q/'CASE_REGISTRY370.private.json')if x['public_case_id']==cid);b=item['branch'];root=D/b/'current';c=item['case'];before=hashlib.sha256((case/'result.json').read_bytes()).hexdigest()if(case/'result.json').exists()else None
 if b=='T1':
  sys.path.insert(0,str(root/'adapter/judge'));import score_t1_cli
  c=next(x for x in read(R/'data/T1/selected.private.json')if x['case_id']==cid);v=score_t1_cli.evaluate(case,c,read(root/'dataset/PROTOCOL.json'))
 elif b=='T2':
  subprocess.run([sys.executable,'-B',str(root/'tools/score.py'),'--root',str(root),'--case-id',cid,'--evidence',str(case),'--output',str(out)],check=True);return
 elif b=='T3':
  sys.path.insert(0,'/mnt/disk_2/geyi/t3_final40_dedicated_20261104/tools');import nostop_scope
  spec=read(R/'data/T3/specs'/(cid+'.json'));v=nostop_scope.evaluate(case,spec,spec['rules'],True)
 elif b=='T4':
  m=load('t4_fixed_private_judge',root/'scoring/legacy/easy10/report.py');p=read(root/'dataset/PROTOCOL.json');p['_dataset_dir']=str(root/'dataset');v=m.evaluate(case,c,p)
 elif b=='T5':
  sys.path[:0]=[str(root/'adapter/judge'),str(root/'adapter/evaluator')];import score_t5
  from score_question import question_kind
  score_t5.question_kind=question_kind;p=read(root/'dataset/PROTOCOL.json');p['_dataset_dir']=str(root/'dataset');v=score_t5.evaluate(case,c,p)
 elif b=='T7':
  sys.path.insert(0,str(root/'adapter/judge'));m=load('t7_fixed_behavior_physical',root/'adapter/judge/score.py');judge,derive=m.load_judge(out.parent/'t7_judge_work');mapping=next(x for x in read(root/'dataset/CASE_ID_MAP.json')if x['case_id']==cid);cat=mapping['condition'];c=next(x for x in read(root/'dataset/legacy'/cat/'cases.private.json')if x['case_id']==mapping['runtime_case_id']);p=read(root/'dataset/legacy'/cat/'PROTOCOL.json');p['_dataset_dir']=str(root/'dataset');_,old=m.evaluate_one(judge,derive,case,c,p)
  sys.path.insert(0,str(D/'distribution/current/scoring/t7'));import review_t7
  result=read(case/'result.json');voice=[x for f in(case/'voice/sessions').glob('*.jsonl')for x in review_t7.lines(f)];audible=review_t7.load_pure_audibility_helper(root);v=review_t7.score_case(old,audible(voice,result.get('messages',[])),review_t7.load_events(case,result),result)
 elif b=='T8':
  sys.path.insert(0,str(root/'judge'));import score_t8
  v=score_t8.evaluate(case,c,read(root/'dataset/PROTOCOL.json'))
 else:raise ValueError('T6 requires separately reviewed factual labels; no invented QA score')
 if b=='T7':
  from deadline_pairs import add_t7_10s
  v=add_t7_10s(v)
 if before:assert hashlib.sha256((case/'result.json').read_bytes()).hexdigest()==before,'Original result changed during scoring'
 out.parent.mkdir(parents=True,exist_ok=True);assert not out.exists();out.write_text(json.dumps(v,indent=2,ensure_ascii=False));print(json.dumps({k:v.get(k)for k in ['interaction','interaction45','target','instruction','failures']},ensure_ascii=False))
if __name__=='__main__':main()
