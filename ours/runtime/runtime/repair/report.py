"""Development evidence index. Never turn text tests into an audio SR."""
import collections,json,sqlite3,time
from pathlib import Path
ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
def load(p):return json.loads(p.read_text())if p.exists()else None
def events(d):
 p=d/'gateway/episodes.sqlite'
 if not p.exists():return[]
 with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)as db:
  return [{**json.loads(payload),'time':t,'kind':k}for t,k,payload in db.execute('SELECT time,kind,payload FROM events ORDER BY rowid')]
def main():
 report=ROOT/'reports';report.mkdir(exist_ok=True)
 cases=[]
 for label in ['text_integration_r1','text_integration_r2','text_integration_r3']:
  for d in sorted((ROOT/label).glob('*')):
   if not d.is_dir():continue
   result=load(d/'TEXT_RESULT.json');validity=load(d/'VALIDITY.json');es=events(d)
   tasks=[e for e in es if e['kind']=='task_instruction'];starts=[e for e in es if e['kind']=='deferred_started'];completed=[e for e in es if e['kind']=='task_completed']
   typed=dict(label=label,kind=d.name,finished=result is not None,raw_passed=(result or{}).get('passed'),valid=not validity or validity.get('valid_for_closed_loop_success'),invalid_reason=(validity or{}).get('reason'),error=(result or{}).get('error'),task_instructions=[e.get('instruction')for e in tasks],deferred_starts=len(starts),completed_events=len(completed),directory=str(d),video=str(d/'gateway_environment.mp4'))
   typed['method']='typed public tools + actual fixed policy; no speech/ASR or realtime intent selection evaluated'
   f=d/'physical.jsonl'
   if f.exists():
    for line in f.open():last=json.loads(line)
    typed['final_observed']=dict(mode=last['mode'],controls=last['policy_actions'],physics=last['step'],task_id=last['task_id'],relations=last['physical']['native_goal_relations'])
   gateway=d/'gateway.jsonl'
   if gateway.exists():
    trace=[json.loads(line)for line in gateway.open()]
    starts=[x for x in trace if x['kind']=='g3_task_activated']
    typed['tasks']=[dict(task_id=x['task_id'],instruction=x['instruction'],start_control=x['control_step'],activated_at=x['time'])for x in starts]
    if starts and typed.get('final_observed'):
     typed['final_task_control_actions']=typed['final_observed']['controls']-starts[-1]['control_step']
    if d.name=='waiting'and len(starts)>=2:
     first=next((x for x in trace if x['kind']=='action_applied'and x['time']>=starts[-1]['time']),None)
     typed['successor_activation_to_first_authorized_control_s']=None if first is None else first['time']-starts[-1]['time']
   cases.append(typed)
 pacing=load(ROOT/'PACING_ALL49.json');priority=load(ROOT/'text_priority_r3/RESULT.json');expanded=load(ROOT/'expanded96/dataset/READINESS.json')
 summary=dict(updated_at=time.time(),new_valid_audio_cases=0,cloud_status='1007 Access denied before waveform; waiting for account restoration',production_8787='not switched to experimental backend',model_weights_changed=False,text_cases=cases,pacing=dict(clips=len(pacing['clips']),passed=pacing['passed'],max_gap_ms=max(x['max_gap_ms']for x in pacing['clips']),max_ratio=max(x['ratio']for x in pacing['clips']))if pacing else None,priority={k:priority.get(k)for k in ['passed','public_tool_pause_latency_s','pause_zero_world_change','actual_resume_events','duplicate_resume_task_id_unchanged']}if priority else None,expanded96=expanded)
 (report/'CURRENT_PROGRESS.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 rows=['# 音频统一接入修复：开发证据报告','', '当前已完成本地修复与真实物理诊断；新的24例/96例语音回归尚未完成，不能声明音频交互已经通过。', '', '## 云端阻断','', '`2026-11-02 02:58`左右，Qwen实时语音在播放任何测试音频前返回`1007 Access denied, please make sure your account is in good standing`。已核对使用的是生产服务同一个私有凭据文件，不是旧副本。暂停后续云端调用；保留工程原记录，未记为模型失败、未拼入旧24成绩。已向用户请求账户状态核查。', '', '## 修复与验证','', '|问题|候选改动|目前证据|','|---|---|---|','|20ms音频发送受同步I/O阻塞|独立工作线程持有WebSocket/音频时钟，编排与写盘分离，独立接收端审计|49段审核音频全部压力测试通过；真实云端收发仍待复测|','|开放对象问答被参数校验误拒绝|允许绑定当前用户明确说出的同一对象；不允许猜对象、无依据ball→bowl或添加目的地|针对性单元检查及真实文字工具闭环通过；未替代ASR/Agent选工具评测|','|碰到目标就报完成并中断松爪|Native与符号路径共用当前任务释放/稳定/40真实物理步终验|基础放置、连续澄清后执行、单独归位均有真实动作诊断；属于开发检查|','|单独归位被附加炉灶目标|归位本身是终态目标，不虚构后续任务|真实文字归位能正常收尾；不证明未见位置记忆泛化|','|Native完成后waiting不交接|同一已验收任务才交接，Native和符号共用出口|R1确实交接1次，但后续物理预算耗尽；不能说整任务成功|','|把观察误添进Task|拒绝无用户依据的“碗当前在桌上”等描述，要求Agent重新生成|单元通过；R3实际规划已有纯用户目标表达，最终物理结果如下|','|暂停配置与网页不一致|统一快速暂停/音频复核开关，物理线程排空优先暂停请求|真实文字工具暂停零物理变化、实际恢复1次；不是语音端到端延迟|','|监控拼接旧快照和新任务编号|任务编号、状态、计数来自同一不可变快照；客户端再与公开状态核对|保留并作废R2提前通过记录；专门回归保护通过|', '', '## 真实文字诊断逐例','', '**这部分无ASR、没有验证听音或实时Agent选工具，不计算音频Interaction/Target/Instruction成功率。工程轮未冻结，不能作为版本间提升的统计证据。**','', '|轮次|项目|终止/结果|waiting交接|证据|','|---|---|---|---:|---|']
 for c in cases:
  state='无效：监控混读，原结果保留'if not c['valid']else('通过开发诊断'if c['raw_passed']else c['error']or'运行中')
  rows.append(f"|{c['label']}|{c['kind']}|{state}|{c['deferred_starts']}|[原记录]({c['directory']}/TEXT_RESULT.json) · [视频]({c['video']})|")
 rows+=['', '## 测试边界','', '- 使用SmolVLA E3 v4 raw30k、原YOLO和已批准8787场景，未训练/更换动作权重。115份Git跟踪F28d源码保持字节不变；扩展以显式适配器安装。M1缓存有效性仍有仿真辅助，语音仍需云端，不宣称整套全本地、全非Oracle。','- 49段压力测试是本地网络回放质量检查，不是49例机器人任务，也不是新的语音识别成绩。接收端与发送端处于不同线程；主编排线程每150ms人为阻塞80ms。','- R2把正确拒绝重复恢复误记为诊断失败，原记录保留；R3明确要求拒绝、任务版本不变、恢复事件只有一次，并通过。','- waiting R2因监控快照混读被判无效，不能把其raw_passed=true当作成功；R3另开目录重测。','- 原24轮保持原样，包括其实时回放不合格标记；不将其低分与本轮开发检查混成提升。','- waiting R3已完成重测：前任务成功、交接一次、Task不再误加桌面位置；后续进入grasp_cheese和cheese_bowl阶段，但1200步未完成放置。新任务激活到首个授权控制约10.32秒，不能据此宣称waiting时延已满足原10秒全链要求。它是无音频开发诊断，不能直接归因SmolVLA或当音频交互通过。','- 新增归位测试只有一个批准初始状态，切换点距原位可能已在容差内；不把它解释成大位移/独立位置泛化。','', '## 扩展96例','', f"已准备32脚本×3批准初始状态={expanded['cases']}例；{expanded['physical_eligible']}例纳入物理指标，另外15例仅检验交互禁止动作等规则。复用{expanded['audios']}段审核音频，缺失{len(expanded['missing_reviewed_audio'])}。正式新音频运行0例。"if expanded else'尚未准备。','', '- 96例的前置场景用同动作模型接受未评分的文字授权建立，所有正式交互才用原音频。没有直接摆物体/读取答案替代前置执行，前置失败保留；因此与24例的语音源任务前置方式分开报告。','- T4_04“奶酪放炉灶”不是十个已训练完整任务之一，保留在原开发集并标记覆盖边界，不悄悄删掉或把低物理成功都归音频。','- 独立评分继续保留原v2.5数值阈值。新候选评分明确区分正常运行中的因果异步物理帧与终态评测hold，额外保留旧action-only Target字段。此为新证据实现版本，不能直接与旧结果混算；容器侧面支撑/QA语义仍列为核对项，不通过事后调阈值刷成功。','', '## 恢复步骤','', '1. 账户恢复后先运行真实音频smoke，验证发送和接收端时序、工具回执、播报与任务身份。','2. 修复已知问题后冻结同24例；保留首次结果、视频、音频、ASR、工具、四Agent输入输出、实际策略提示词及物理轨迹。','3. 再跑32×3的96例，明确区分交互失败、基础设施故障和物理执行失败。','4. 核对通过后再切换主网页执行后端，并验证reset/重连/记忆生命周期。主8787当前未因此上线候选。','', '代码与启动说明：[候选运行说明](/mnt/disk_2/geyi/voice_f28d_audio_repair_20261102/repair/RUNBOOK.md)。机器可读进度：[CURRENT_PROGRESS.json]('+str(report/'CURRENT_PROGRESS.json')+')。','']
 (report/'REPORT.md').write_text('\n'.join(rows));print(json.dumps(dict(report=str(report/'REPORT.md'),text_cases=len(cases),cloud='blocked')))
if __name__=='__main__':main()
