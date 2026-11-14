"""Thirty-case evidence adapter, fixed denominators, same10/45 trajectory grades."""
import argparse,collections,csv,gzip,importlib.util,os,statistics,sys
import json,hashlib,time
from pathlib import Path
B=Path(__file__).resolve().parent
def read(p):return json.loads(Path(p).read_text())
def dump(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix('.tmp');q.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');q.replace(p)
METRICS=('interaction10','interaction45','target','instruction','joint10','joint45')
def grade(checks,seconds):
 statuses=[]
 for c in checks:
  s=c['status']
  if c['name']=='handoff_first_action_within_10s':
   latency=(c.get('evidence')or{}).get('latency_s')if isinstance(c.get('evidence'),dict)else None
   if latency is not None:s='pass'if latency<=seconds else'fail'
  statuses.append(s)
 return'fail'if'fail'in statuses else'unknown'if'unknown'in statuses else'pass'
def status_audit(d):
 from status_identity_audit import audit
 return audit(d)
def load_judge(root):
 os.environ['T7_REPAIR_OUT']=str(root);spec=importlib.util.spec_from_file_location('t7_goal10_parent_evidence',B/'parent_score.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 sys.path.insert(0,str(B));from container_support import derive
 return m.score_t7,derive
def evaluate_one(judge,derive,d,c,protocol):
 base=judge.lines;raw=judge.evaluate(d,c,protocol);audit={}
 def adapted(path):
  rows=base(path)
  if str(path).endswith('control_ticks.jsonl'):
   try:rows,a=derive(rows,d)
   except(EOFError,gzip.BadGzipFile,ValueError,OSError)as e:
    # Raw live contact evidence remains usable if an auxiliary archive was cut short.
    rows,a=derive(rows,d/'__auxiliary_trace_unavailable__');a['auxiliary_archive_error']=type(e).__name__;a['fallback']='direct live raw contacts only, absent contact remains unknown'
   audit.update(a)
  return rows
 judge.lines=adapted
 try:v=judge.evaluate(d,c,protocol)
 finally:judge.lines=base
 for x in(raw,v):
  x['interaction10']=x['interaction'];x['interaction45']=grade(x.get('checks',[]),45)if x.get('checks')else'fail'
  for sec in(10,45):x['joint'+str(sec)]='pass'if x['interaction'+str(sec)]==x['instruction']=='pass'else'fail'
 r=read(d/'result.json');v.update(raw_metrics={m:raw[m]for m in METRICS},support_audit=audit,branch=c['branch'],goal_id=c['private_contract']['final_target_task_id'],
  audio_quality=read(d/'AUDIO_QUALITY.json')if(d/'AUDIO_QUALITY.json').exists()else{},identity_audit=status_audit(d),
  video=str(d/'gateway_environment.mp4'),evidence_directory=str(d),actual_turns=len(r.get('turns',[])),expected_turns=len(c['turns']),
  backend_final_mode=r.get('final',{}).get('state'),runner_errors=r.get('errors',[]),full_case_no_probe=not read(d/'spec.json').get('probe_policy'))
 v['handoff_latency_s']=next((x.get('evidence',{}).get('latency_s')for x in v.get('checks',[])if x['name']=='handoff_first_action_within_10s'and isinstance(x.get('evidence'),dict)),None)
 v['scoring_version']='t7-goal10-v3-frozen-parent-plus-existing-container-support'
 return raw,v
def stats(values,denom,raw=False):
 return{m:dict(passed=sum((v['raw_metrics']if raw else v)[m]=='pass'for v in values),denominator=denom,observed=len(values),rate=sum((v['raw_metrics']if raw else v)[m]=='pass'for v in values)/denom)for m in METRICS}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--root',required=True,type=Path);args=ap.parse_args();root=args.root;data=root/'dataset';report=root/'reports';report.mkdir(exist_ok=True)
 cases=read(data/'selected.private.json');protocol=read(data/'PROTOCOL.json');assert len(cases)==10
 judge,derive=load_judge(root);values=[]
 for c in cases:
  d=root/'cases'/c['case_id']
  if not(d/'RUN_FINISHED.json').exists()or not(d/'result.json').exists():continue
  cache=d/'verdict.json'
  if cache.exists():v=read(cache)
  else:
   raw,v=evaluate_one(judge,derive,d,c,protocol);dump(d/'verdict_raw.json',raw);dump(cache,v)
  values.append(v)
 metrics=stats(values,10);lat=[v['handoff_latency_s']for v in values if v.get('handoff_latency_s')is not None]
 summary=dict(status='complete'if len(values)==10 else'partial',received=len(values),planned=10,metrics=metrics,raw_metrics=stats(values,10,True),
  branches={b:stats([v for v in values if v['branch']==b],sum(c['branch']==b for c in cases))for b in('N','C','R')},
  final_goals={str(g):stats([v for v in values if v['goal_id']==g],1)for g in range(10)},
  failures=dict(collections.Counter(f for v in values for f in v.get('failures',[]))),
  identity={k:sum(v['identity_audit'][k]for v in values)for k in('samples','wrong_task_metadata','invalid_completion')},
  input_quality=dict(passed_cases=sum(v['audio_quality'].get('passed')is True for v in values),observed_cases=len(values)),
  handoff=dict(actual_handoffs=len(lat),within10=sum(x<=10 for x in lat),within45=sum(x<=45 for x in lat),median_s=statistics.median(lat)if lat else None,latencies_s=lat,
   source_failure_not_actual_handoff=sum(v.get('source_failure_truthfully_blocked')is True for v in values)),
  preflight_pooled=False,only_handoff_deadline_changes=True,source_candidate=str(B),new_dataset_not_old_subset=True)
 dump(report/'summary.json',summary);dump(report/'verdicts.json',values)
 cols=['case_id','branch','goal_id']+list(METRICS)+['actual_turns','expected_turns','backend_final_mode','handoff_latency_s','failures','runner_errors','video']
 with(report/'cases.csv').open('w',encoding='utf-8-sig',newline='')as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
  for v in values:w.writerow({k:';'.join(v.get(k,[]))if k in('failures','runner_errors')else v.get(k)for k in cols})
 text=['# T7 Goal10：C3r十例真实音频结果','',f"状态{summary['status']}，已完成{len(values)}/10；10脚本、统一I00初态，各一次。预检独立，不合并。",'',
  '主表使用现有真实容器支撑证据；原冻结评分同时保留。两档只改变交接时限10→45秒，不改变物理约束、受理与播报时限。新脚本不能沿用旧筛选83.33%。','',
  '|指标|主评分|原冻结评分|','|---|---:|---:|']
 for m in METRICS:text.append(f"|{m}|{metrics[m]['passed']}/10（{metrics[m]['rate']:.2%}）|{summary['raw_metrics'][m]['passed']}/10|")
 text+=['','|最终目标|I10|I45|Target|Instruction|Joint45|','|---|---:|---:|---:|---:|---:|']
 for g,s in summary['final_goals'].items():text.append('|'+ '|'.join([g]+[str(s[m]['passed'])+'/1'for m in('interaction10','interaction45','target','instruction','joint45')])+'|')
 text+=['','## 逐例原话、失败项和视频','']
 by={c['case_id']:c for c in cases}
 for v in values:
  c=by[v['case_id']];d=Path(v['evidence_directory']);text +=[f"### {v['case_id']}",'',*[f"- 用户原话：{t['text']}"for t in c['turns']],f"- 结果：{ {m:v[m]for m in METRICS} }。",f"- 失败项：{v.get('failures',[])}；客户端记录：{v['runner_errors']}。",f"- [视频]({v['video']}) · [实际结果]({d/'result.json'}) · [逐项评分]({d/'verdict.json'}) · [语音日志]({d/'voice/sessions'}) · [Agent过程]({d/'kernels'})",'']
 (report/'RESULTS.md').write_text('\n'.join(text)+'\n');print(json.dumps(dict(received=len(values),planned=10,metrics=metrics),ensure_ascii=False),flush=True)
if __name__=='__main__':main()
