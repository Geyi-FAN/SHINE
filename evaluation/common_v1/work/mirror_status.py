"""Read-only progress mirror; not a trial submitter."""
import json,sys,time
from pathlib import Path
Q=Path(__file__).resolve().parents[1];sys.path.insert(0,str(Q.parent/'c3r_cloud04_240_20261108/tools'));from remote import connect
while True:
 try:
  c=connect();s=c.open_sftp();v=json.loads(s.open(str(Q/'STATUS.json')).read());p=Q/'STATUS.json.tmp';p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n');p.replace(Q/'STATUS.json')
  phase=v.get('phase');labels={'running_auto_network_admission':'正在派发与执行','network_health_admission':'独立网络检查中，暂不派发','loading_own_services':'正在加载模型服务','stopped':'已停止，未继续派发','completed':'注册队列已结束，仍需核对后处理'}
  if phase=='draining_after_error':label='错误收尾：等待在途案例结束；随后自动检查网络'if v.get('automatic_network_admission')else'错误收尾：停止派发，等待在途案例结束'
  else:label=labels.get(phase,phase)
  lines=['# 两条旧配置基线：共同标准重测','',f"状态：{phase}（{label}）；当前阶段 {v.get('completed','?')}/{v.get('planned','?')}。",'本页只读镜像240，不派发/重试案例。预检结果不属于正式1770成绩。']
  if v.get('automatic_network_admission'):lines.append(f"自动网络准入轮次：{v.get('recovery_cycle',0)}；历史异常累计：{v.get('infrastructure_errors',0)}。只续跑未开始项，已开始的失败案例不重跑；账户拒绝、未知故障或健康检查未恢复仍会停止。")
  try:
   monitor=json.loads(s.open(str(Q/'monitoring/20261115/STATUS.json')).read());p=Q/'monitoring/20261115/STATUS.json';p.write_text(json.dumps(monitor,ensure_ascii=False,indent=2)+'\n')
   action=monitor.get('action');action_label={'observe':'巡检正常','observe_external_coordinator':'检测到其他调度进程，未干预','waiting_for_network_health':'等待网络恢复','restarted_verified_coordinator':'已按原冻结代码恢复','manual_unknown_error':'发现新错误，需排查','manual_partial_trial':'存在半途案例，需排查','manual_account_or_model_identity':'账户或模型身份异常','manual_monitor_error':'监测器异常，需处理','user_stopped':'用户要求停止','collection_complete':'采集完成','waiting_for_owned_ports_to_clear':'等待端口释放'}.get(action,action)
   lines.append(f"常驻巡检：{monitor.get('beijing')}；级别 {monitor.get('severity')}；处理状态 {action_label}（{action}）。")
   eta=monitor.get('eta',{})
   if eta.get('state')=='estimated':lines.append(f"预计采集完成（北京时间）：{eta['collection_finish_earliest']}～{eta['collection_finish_latest']}；预计最终结果：{eta['report_finish_earliest']}～{eta['report_finish_latest']}。按最近15/30分钟吞吐估算，未知故障会顺延。")
   elif eta.get('state')=='blocked_no_committed_finish_time':lines.append('当前评测已停止：不继续展示原预计完成时刻，待恢复后重新计算。')
   if monitor.get('severity')=='critical':lines.append(f"**需要处理：{monitor.get('diagnostic_bundle','查看 monitoring/20261115/ERROR.json')}。未知错误不会自动改写模型或评分。**")
  except(OSError,ValueError):pass
  try:
   guard=json.loads((Q/'monitoring/20261115/FINALIZER_STATUS.json').read_text());lines.append(f"后处理监护：{guard.get('action')}；只允许90条QA的首次固定模型判分。")
  except(OSError,ValueError):pass
  lines+=['', '|方法|任务|本阶段已结束/计划|交互通过|目标通过|物理完整通过|','|---|---|---:|---:|---:|---:|']
  for method,branches in v.get('by_method',{}).items():
   for branch,x in branches.items():
    if not x.get('planned'):continue
    lines.append('|'+method+'|'+branch+'|'+str(x['completed'])+'/'+str(x['planned'])+'|'+'|'.join(str(x[k]['success'])for k in ['interaction','target','instruction'])+'|')
  (Q/'PROGRESS.md').write_text('\n'.join(lines)+'\n')
  s.close();c.close()
 except Exception as e:print(type(e).__name__,str(e)[:120],flush=True)
 time.sleep(30)
