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
  lines+=['', '|方法|任务|本阶段已结束/计划|交互通过|目标通过|物理完整通过|','|---|---|---:|---:|---:|---:|']
  for method,branches in v.get('by_method',{}).items():
   for branch,x in branches.items():
    if not x.get('planned'):continue
    lines.append('|'+method+'|'+branch+'|'+str(x['completed'])+'/'+str(x['planned'])+'|'+'|'.join(str(x[k]['success'])for k in ['interaction','target','instruction'])+'|')
  (Q/'PROGRESS.md').write_text('\n'.join(lines)+'\n')
  s.close();c.close()
 except Exception as e:print(type(e).__name__,str(e)[:120],flush=True)
 time.sleep(30)
