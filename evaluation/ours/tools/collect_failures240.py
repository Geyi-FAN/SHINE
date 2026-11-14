"""Read-only failure evidence, never supplied to the planner or action policy."""
import json,re,time,collections
from pathlib import Path
N=Path(__file__).resolve().parents[1]
def read(p,default=None):
 try:return json.loads(Path(p).read_text())
 except (OSError,ValueError):return default

def short(x,n=900):return str(x)[:n]
def records_tail(p,limit=2000000):
 try:
  with p.open('rb')as f:
   f.seek(0,2);size=f.tell();f.seek(max(0,size-limit));s=f.read().decode(errors='replace')
 except OSError:return []
 rows=[]
 for line in s.splitlines():
  try:rows.append(json.loads(line))
  except ValueError:pass
 return rows

def safe_error(e):
 p=e.get('payload',e);result={k:p.get(k)for k in ['source','code','stage','impact','message','event','error','errorName','kind','closeCode','fatal']if p.get(k)is not None}
 return dict(ts=e.get('ts',e.get('time')),type=e.get('type'),payload=result)
rows=[]
for r in read(N/'diagnostics/BASE930_ENGINEERING.json'):
 if not any(r.get(m)in ['fail','unknown']for m in ['interaction','target','instruction']):continue
 case=Path(r['case_directory']);out=read(case/'PREFLIGHT_OUTCOME.json',{});result=read(case/'result.json',{});score=read(case/'SCORE_AUDITED.json',{})
 final=out.get('final_status')or result.get('final')or{}
 started=out.get('started_at',0)
 finish=result.get('finished')or{}
 ended=finish.get('time',out.get('finished_at',float('inf')))if isinstance(finish,dict)else out.get('finished_at',float('inf'))
 def during_trial(e):
  t=e.get('ts')/1000 if isinstance(e.get('ts'),(int,float))else e.get('time')
  return isinstance(t,(int,float))and started<=t<=ended
 logs=records_tail(case/'gateway.jsonl');inputs=[x for x in logs if x.get('kind')=='executor_input'];errors=[];visual=[]
 for f in (case/'voice/logs').glob('*.jsonl'):
  if 'error'in f.name:
   errors.extend(safe_error(e)for e in records_tail(f,300000)if during_trial(e))
  elif'visual'in f.name:
   for e in records_tail(f,1000000):
    if any(w in json.dumps(e).lower()for w in ['failed','error','parse','invalid','retry']):visual.append(safe_error(e))
 agent=final.get('agent_execution')or{}
 row=dict(trial_uid=r['trial_uid'],branch=r['branch'],case_id=r['case_id'],version_group=r['version_group'],directory=str(case),interaction=r.get('interaction'),target=r.get('target'),instruction=r.get('instruction'),reason=r.get('reason'),audio_played=out.get('audio_played',r.get('audio_played')),client_errors=result.get('errors',[]),final_state=final.get('state'),failure_detail=final.get('failure_detail'),agent_execution={k:agent.get(k)for k in ['phase','operation','subgoal','stop_reason','reason','error','completion_status','verifier','last_error']if k in agent},last_logged_policy_inputs=len(inputs),tail_policy_inputs_are_complete_count=False,runtime_errors=errors[-16:],visual_errors=visual[-10:],score_failures=score.get('failures'),failed_checks=[x for x in score.get('checks',[])if x.get('status')not in ['pass','na']],trace_missing=not bool(logs),sampled_log_bytes_limit=2000000)
 if r['branch']=='T1':
  row['timings']={k:score.get(k)for k in ['accepted_latency_s','first_action_latency_s','first_reply_pcm_latency_s']}
 rows.append(row)
(N/'diagnostics/FAILURE_EVIDENCE.json').write_text(json.dumps(dict(at=time.time(),rows=rows,note='Tail events describe observed failure, not necessarily underlying model capability'),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(failure_cases=len(rows),by_branch=dict(collections.Counter(r['branch']for r in rows)),runtime_error_cases=sum(bool(r['runtime_errors'])for r in rows),visual_error_cases=sum(bool(r['visual_errors'])for r in rows))))
