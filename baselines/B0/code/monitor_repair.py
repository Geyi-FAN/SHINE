"""Read-only supplemental progress; fixed registration and immutable old results."""
import csv,datetime,json,os,time
from pathlib import Path
N=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def write(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(x,indent=2,ensure_ascii=False));q.replace(p)
def alive(pid):
 try:os.kill(pid,0);return True
 except(ProcessLookupError,ValueError,TypeError):return False
def update():
 registered=read(N/'config/REPAIR_REGISTERED.json');ids={x['trial_uid']for x in registered};rows=[];lanes=[]
 for lane in [0,1]:
  run=N/'runs'/f'supplement193_lane{lane}';p=run/'PROGRESS.json';c=run/'COORDINATOR.json';state=read(p)if p.exists()else dict(state='not_started',active=None)
  if c.exists():state['process_alive']=alive(read(c)['pid'])
  if state['state']=='running'and state.get('process_alive')is False:state['state']='coordinator_exited'
  lanes.append(dict(lane=lane,**state))
  for p in(run/'cases').glob('*/REPAIR_OUTCOME.json'):
   r=read(p);assert r['trial_uid']in ids;rows.append(r)
 assert len({r['trial_uid']for r in rows})==len(rows)
 done=len(rows)==len(registered);blocked=any(x['state']in ['stopped_with_error','coordinator_exited']for x in lanes)
 status='completed'if done else'stopped_needs_inspection'if blocked else'running'if any(x.get('process_alive')for x in lanes)else'not_started'
 summary=dict(updated_beijing=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),state=status,registered=len(registered),finished=len(rows),remaining=len(registered)-len(rows),lanes=lanes,by_branch={},T6_excluded=True,T8_speech_overlap_unsupported=48,selection='predeclared technical/PCM criteria and whole applicable T8 cohort; no success-based retry',scoring='audio-logical-goal-attribution-v4-20261109')
 for b in ['T2','T3','T4','T5','T7','T8']:
  xs=[r for r in rows if r['branch']==b];summary['by_branch'][b]=dict(registered=sum(x['branch']==b for x in registered),finished=len(xs),audio_pass=sum(x.get('audio_quality_passed')is True for x in xs),engineering_error=sum(x.get('engine_error',False)or x['status']=='technical_or_setup_failure'or x.get('scoring_returncode',0)!=0 or x.get('v4_scoring_returncode',0)!=0 for x in xs),target_success=sum(x.get('score_v4',{}).get('target')=='pass'for x in xs),instruction_success=sum(x.get('score_v4',{}).get('instruction')=='pass'for x in xs))
 write(N/'PROGRESS.json',summary)
 md='# 纯ASR补评：传输与归因修复\n\n'+f"更新：{summary['updated_beijing']}；状态：{status}；完成 **{len(rows)}/{len(registered)}**。\n\n"+'| 类别 | 登记 | 已结束 | 音频准入通过 | 工程错误 |\n|---|---:|---:|---:|---:|\n'+''.join(f"| {b} | {r['registered']} | {r['finished']} | {r['audio_pass']} | {r['engineering_error']} |\n"for b,r in summary['by_branch'].items())+'\nT6仍排除。T8有72个可适用实例进入新版本，48个需系统自身出声的实例标为不支持，不制造播放事件。当前是补评进度，不是完整正式成功率。\n\n'
 for lane in lanes:
  if lane.get('active'):md+=f"- 通道{lane['lane']}：`{lane['active']['trial_uid']}`。\n"
 md+='\n[修复说明](README.md) · [旧840轨迹仅重评分](reports/original840_v4/SUMMARY.json) · [真实4例预检](reports/PREFLIGHT_ACCEPTANCE.json) · [预登记清单](config/REPAIR_REGISTERED.json)。\n'
 (N/'PROGRESS.md').write_text(md)
 if rows:
  path=N/'SUPPLEMENT_CASES.csv.tmp'
  with path.open('w',newline='')as f:
   w=csv.DictWriter(f,fieldnames=['trial_uid','branch','audio_quality_passed','engine_error','status','target_v4','instruction_v4','directory','original_case_directory']);w.writeheader()
   for r in rows:w.writerow({k:r.get(k)for k in ['trial_uid','branch','audio_quality_passed','engine_error','status','directory','original_case_directory']}|dict(target_v4=r.get('score_v4',{}).get('target'),instruction_v4=r.get('score_v4',{}).get('instruction')))
  path.replace(N/'SUPPLEMENT_CASES.csv')
 if done:write(N/'SUPPLEMENT_RESULTS.json',summary);(N/'SUPPLEMENT_RESULTS.md').write_text(md+'\n补评已结束；模型失败原样保留，不用补评成功覆盖未登记的旧失败。\n')
 return done
if __name__=='__main__':
 while True:
  try:
   if update():break
  except Exception as e:write(N/'MONITOR_ERROR.json',dict(error=repr(e),time=time.time()))
  time.sleep(10)
