"""Read-only, crash-aware aggregate progress and evidence index every ten seconds."""
import csv,datetime,json,os,time
from collections import Counter
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def write(p,v):
 q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(v,indent=2,ensure_ascii=False));q.replace(p)
def score_one(v):
 s=v.get('score',{})
 if isinstance(s.get('rows'),list):s=s['rows'][0]if s['rows']else{}
 return s
def alive(pid):
 try:os.kill(int(pid),0);return True
 except(ProcessLookupError,TypeError,ValueError):return False
def tick():
 planned=read(R/'data/FORMAL810.private.json');register={x['trial_uid']:x for x in planned};completed={};lanes=[];active=[]
 for lane in range(2):
  run=R/'runs'/f'formal_lane{lane}';p=run/'PROGRESS.json';coordinator=run/'COORDINATOR.json';entry=dict(lane=lane,run=str(run),state='not_started')
  if p.exists():entry.update(read(p));entry['lane']=lane
  if coordinator.exists():entry['process_alive']=alive(read(coordinator)['pid'])
  if entry.get('phase')=='running'and entry.get('process_alive')is False:entry['phase']='unexpected_coordinator_exit'
  for f in(run/'cases').glob('*/ATTEMPT_OUTCOME.json'):
   v=read(f)
   if v['trial_uid']not in register:raise ValueError('unexpected_trial')
   if v['trial_uid']in completed:raise ValueError('duplicate_trial')
   completed[v['trial_uid']]=v
  if entry.get('active'):
   x=dict(entry['active'],lane=lane)
   attempt=run/'cases'/x['trial_uid'];a=attempt/'ATTEMPT.json'
   if not a.exists():
    candidates=sorted(attempt.glob('preparation_attempts/*/ATTEMPT.json'));a=candidates[-1]if candidates else a
   if a.exists():x['attempt']=read(a)
   active.append(x)
  lanes.append(entry)
 rows=[];by={}
 for branch in ['T2','T3','T4','T5','T6','T7','T8']:
  xs=[v for v in completed.values()if v['branch']==branch];scores=[score_one(v)for v in xs];b=dict(planned=sum(x['branch']==branch for x in planned),finished=len(xs),audio_played=sum(bool(v.get('audio_played'))for v in xs),pcm_audited_pass=sum(v.get('audio_quality_passed')is True for v in xs),engineering_errors=sum(bool(v.get('engine_error'))or v['status']=='technical_or_setup_failure'or v.get('scoring_returncode',0)!=0 for v in xs),setup_unavailable=sum(v['status']=='setup_unavailable'for v in xs))
  for metric in ['interaction','target','instruction','qa_success']:
   vals=[s.get(metric)for s in scores if s.get(metric)in ['pass','fail',True,False]];b[metric]=dict(success=sum(v in ['pass',True]for v in vals),evaluated=len(vals))
  b['qa_asked']=sum(s.get('asked')is True for s in scores);by[branch]=b
 for uid,v in completed.items():
  s=score_one(v);rows.append(dict(trial_uid=uid,branch=v['branch'],case_id=v['case_id'],status=v['status'],interaction=s.get('interaction'),target=s.get('target'),instruction=s.get('instruction'),qa_success=s.get('qa_success'),qa_asked=s.get('asked'),audio_quality_passed=v.get('audio_quality_passed'),engine_error=v.get('engine_error'),elapsed_seconds=v.get('total_elapsed_seconds',v.get('elapsed_seconds')),directory=v['directory'],failures='; '.join(s.get('failures',[]))))
 complete=len(completed)==810;stopped=any(x.get('phase')in ['stopped_with_error','unexpected_coordinator_exit']for x in lanes);state='completed'if complete else'interrupted'if stopped else'running'if any(x.get('process_alive')for x in lanes)else'not_started'
 q=dict(updated_beijing=datetime.datetime.now().astimezone().isoformat(),state=state,scope='pure_ASR_pi05_T2_T8_only',planned=810,finished=len(completed),remaining=810-len(completed),active=active,lanes=lanes,by_branch=by,conditional_denominators='T2 trigger coverage/120; T6 actual QA asked/90. Missing/noneligible cases never silently removed.',estimates_are_final=False)
 write(R/'PROGRESS.json',q)
 md='# 纯 ASR＋π0.5：T2–T8 实时进度\n\n'+f"更新：{q['updated_beijing']}；状态：{state}；已结束 **{len(completed)}/810**。\n\n"+'| 类别 | 计划 | 已结束 | 实际送音频 | 音频核验通过 | 工程错误 |\n|---|---:|---:|---:|---:|---:|\n'+''.join(f"| {b} | {v['planned']} | {v['finished']} | {v['audio_played']} | {v['pcm_audited_pass']} | {v['engineering_errors']} |\n"for b,v in by.items())+'\n实际方法：Whisper large-v3 → 原转写文本 → π0.5 E3 744/30000。没有 Agent、Oracle 子目标/坐标、YOLO、记忆或语音回答。两路独立进程并行。\n\n'
 if active:md+='当前案例：\n\n'+''.join(f"- 通道 {a['lane']}：{a['branch']} / `{a['trial_uid']}`。\n"for a in active)
 md+='\n未完成时不将局部比例报告为正式成功率。T6按实际问题首包锁定分母；准备失败另报覆盖率。旧预检与T1结果不混入本轮810例。\n\n逐例索引：`CASES.csv`；配置与使用说明：`README.md`；全部原始证据：`runs/formal_lane*/cases/`。\n'
 (R/'PROGRESS.md').write_text(md)
 if rows:
  tmp=R/'CASES.csv.tmp'
  with tmp.open('w',newline='')as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
  tmp.replace(R/'CASES.csv')
 if complete:write(R/'RESULTS.json',q);(R/'RESULTS.md').write_text(md+'\n完整机器统计见 `RESULTS.json`。\n')
 return complete
if __name__=='__main__':
 while True:
  try:
   if tick():break
  except Exception as e:write(R/'MONITOR_ERROR.json',dict(error=repr(e),time=time.time()))
  time.sleep(10)
