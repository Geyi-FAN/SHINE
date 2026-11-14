"""Summarize retained development trials. Never selects only successful trials."""
import argparse,collections,gzip,hashlib,json,sys
from datetime import datetime,timezone,timedelta
from pathlib import Path
B=Path(__file__).resolve().parents[1];DATA=Path('/mnt/disk_4/geyi/voice_f28d_G22_20261101');OUT=B/'reports/G22'
def load(path):return json.loads(Path(path).read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--audio',default='audio_smoke_v9');a=ap.parse_args();audio=DATA/a.audio;ar=load(audio/'AUDIO_RESULT.json')
 events=[json.loads(l)for l in(audio/'gateway.jsonl').read_text().splitlines()];client=[json.loads(l)for l in(audio/'client/events.jsonl').read_text().splitlines()]
 speech=[json.loads(l)for p in(audio/'voice/sessions').glob('*.jsonl')for l in p.read_text().splitlines()]
 transcripts=[dict(time=r['ts']/1000,text=r['payload']['text'])for r in speech if r['type']=='transcript.user']
 expected=load(audio/'spec.json')['turns'];receipts=[r for r in events if r['kind']=='voice_tool_receipt'and r['tool']in ['robot_start_task','robot_pause','robot_resume','robot_revise_task']];tools=['robot_start_task','robot_pause','robot_resume','robot_revise_task'];turns=[]
 for i,(spec,tool)in enumerate(zip(expected,tools)):
  got=transcripts[i]if i<len(transcripts)else{};receipt=next((r for r in receipts if r['tool']==tool),None)
  # Use actual stream-end time, never the pre-wait scripted start.
  frames=[r for r in client if r['type']=='client.input_frame'and r.get('clip_id')==spec['id']]
  end=max((r['time']for r in frames),default=0)+.020
  turns.append(dict(turn=spec['id'],expected=spec['text'],ASR=got.get('text'),transcript_exact=got.get('text')==spec['text'],tool=tool,accepted=bool(receipt and receipt['receipt'].get('status')=='accepted'),audio_end=end,receipt_at=None if receipt is None else receipt['time'],audio_end_to_receipt_s=None if receipt is None or not end else receipt['time']-end))
 pause=ar.get('pause',{});resumed=bool(ar.get('resume_motion')and ar['resume_motion']['control_step']>ar['resume']['control_step']);p_start=next((r['monotonic']for r in receipts if r['tool']=='robot_pause'),None);p_end=next((r['monotonic']for r in receipts if r['tool']=='robot_resume'),None)
 forbidden=[r for r in events if r['kind']in ['action_applied','native_source_action_applied']and p_start is not None and p_end is not None and p_start<r['monotonic']<p_end]
 taskresults=[]
 for p in(audio/'tasks').glob('*/result.json'):taskresults.append(dict(file=str(p),**load(p)))
 symbolic=next((r for r in taskresults if r['route']=='symbolic'),None);kernel_results=[load(p)for p in(audio/'kernels').glob('*/result.json')]
 kernel_calls=sum(k.get('agent_calls',0)for k in kernel_results);actions=sum(k.get('actions',0)for k in kernel_results)
 outputs=list((audio/'client').glob('output_*.wav'));rejected=[r for r in events if r['kind']=='voice_tool_rejected'];by_input=collections.Counter(r['args'].get('voice_input_id')for r in receipts)
 sys.path.insert(0,str(B/'integration'));from adapter import F28dExecutionAdapter
 role_count=0;role_errors=[]
 for p in(audio/'local_requests').glob('*/*/request_original.json'):
  try:F28dExecutionAdapter().role_body(p.parent.parent.name,load(p));role_count+=1
  except Exception as exc:role_errors.append(dict(file=str(p),error=str(exc)))
 frozen=load(B/'freeze/f28d/FROZEN.json');drift=[name for name,h in frozen.items()if hashlib.sha256((B/'freeze/f28d'/name).read_bytes()).hexdigest()!=h]
 terminal_notifications=[r['payload']for r in speech if r['type']=='realtime.protocol'and r['payload'].get('type')=='robot.terminal_notification']
 terminal_bound=any(ar.get('final',{}).get('task_id','missing')in n.get('key','') and n.get('key','').endswith(':'+ar['final']['mode'])for n in terminal_notifications)
 stats=dict(scope='one controlled four-turn TTS development episode; not formal Interaction SR/generalization',turns=turns,pause_passed=pause.get('passed',False),paused_action_count=len(forbidden),resumed_actual_source_actions=resumed,duplicate_mutations=sum(max(0,n-1)for n in by_input.values()),voice_tool_rejections=len(rejected),output_wav_files=len(outputs),terminal_audio=ar.get('terminal_audio'),terminal_notification_bound_to_current_task=terminal_bound,terminal_notifications=terminal_notifications,symbolic_planner_generations=kernel_calls,symbolic_kernel_actions=actions,terminal=ar.get('final'),symbolic_metrics=None if symbolic is None else symbolic['metrics'],role_requests_audited=role_count,role_input_errors=role_errors,frozen_files=len(frozen),frozen_drift=drift,audio_client_errors=ar['errors'],case_results=taskresults,model='SmolVLA E3 v4 raw30k',scoring='unchanged v2.5.0-candidate/current-contract-stop-v1',cache_validity_simulator_assisted=True,native_archive_caveat='Raw Native result mode field is captured after replacement, so use its independent metric and benchmark_terminal event, not that copied mode, to identify prior-task completion.')
 (OUT/'AUDIO_AUDIT.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
 close=load(OUT/'CLOSE_PAIR_AUDIT.json');release=load(OUT/'RELEASE_AUDIT.json');lines=['# G2.2关闭、释放恢复与真实语音预检','',f"生成时间：{datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')}。全部属于开发诊断，不是正式Benchmark成绩。",'',
 '相同关闭进入状态下，几何预检未通过成功保护，继续保留原调度。新增归位后期复查在支撑状态成功触发释放；真实语音结果如下，物理成绩与交互受理分列。','',
 '## 1. 共同条件与保护边界','',
 '- 动作权重、归一化、YOLO、8维本体状态、原训练提示词和v2.5数值阈值不变。模型为SmolVLA E3 v4 raw30000。','- 119份F28d冻结源码无漂移；修复通过独立适配模块加载。生产8787及共享模型服务没有重启。','- 仿真真值用于起点构造/对照评分及语音触发，M1缓存有效性沿用仿真辅助；不提供Oracle下一步或真值像素给规划Agent。不能称完全去仿真辅助。','- 暂停禁止所有env.step；异步模型等待继续推进物理，用独立时钟记账。','',
 '## 2. 相同关闭进入状态：4对、8次','',
 '两组完整物理状态、接触求解缓存、初始MAIN/WRIST图像、Task、原Agent所选close subgoal、种子和首个策略数组逐项相同。4个状态包含同一C4配置的两条轨迹，不能当4种独立任务。阶段固定，且两组均关闭主动恢复工具；每次400控制步，不是完整任务SR。','',
 '|进入状态|原调度确认成功|预检确认成功|原/预检视觉调用|原/预检控制步|','|---|---|---|---|---|']
 for name in ['middle','top_inside','top_after_return_A','top_after_return_B']:
  rows={r['arm']:r for r in close['rows']if r['state']==name};o,p=rows['original'],rows['preflight'];lines.append(f"|{name}|{o['observed']}|{p['observed']}|{o['visual_calls']} / {p['visual_calls']}|{o['controls']} / {p['controls']}|")
 lines+=['','原调度4/4、预检3/4，两组错误确认均0，工程审计8/8。预检失败的C4进入状态，最终抽屉开度约9.90cm，整个过程中未进入1cm关闭窗口：不只是复核漏判，也存在物理执行差异。异步等待时序会改变后续状态，减少复核并不保证改善执行，因此候选不推广。','',
 '[完整初始状态和时钟审计](CLOSE_PAIR_AUDIT.json) · [逐对明细及视频路径](CLOSE_PAIR.csv)','',
 '## 3. 到位未松手恢复','',
 '未保存历史卡住时刻的完整控制器快照。本次从历史末尾机器人/物体姿态重建，速度清零并稳定12步，再保存两组完全相同的完整起点。核查有支撑、仍夹爪接触，距原位2.34cm。不能称原失败轨迹精确续接。','',
 '从新任务重新规划时，原版和恢复版都能完成全部任务；不能把该状态当作只有新模块才能解决的失败。于是另设固定归位阶段诊断：保留原阶段1196步年龄，两组先获取12步新观测，预算300控制步。','',
 '|固定阶段组|观测确认归位|独立检查有支撑、松手、距原位≤3.5cm|控制步|墙钟秒|','|---|---|---|---:|---:|']
 for r in release['stage_tests']:
  if r['experiment']=='release_stage_v2':lines.append(f"|{r['arm']}|{r['accepted']}|{r['physically_supported_released_in_3p5cm']}|{r['controls']}|{r['seconds']:.2f}|")
 lines+=['','恢复组：12、20步两次新观测均由Agent请求原地释放；20步开启夹爪，36步由Agent请求撤离，72步归位阶段通过。脚本没有直接写入完成事件。少40个控制步，但因模型复核更多，墙钟更慢；不能称整体提速或成功率提升。','',
 '历史真实悬空、后期遮挡两组新Agent复核均返回observe_only，没有请求盲目释放。对当前真实支撑图像和位置对齐证据才请求释放。10项新增归位保护测试覆盖错对象、错阶段、远离目标、缺点、低置信度、手运动、已开手和非独立新帧。','',
 '[释放诊断及实际Agent输入输出索引](RELEASE_AUDIT.json)；视频见其中video字段。','',
 '## 4. 真实语音开发闭环','',
 f"实际输入：{a.audio}。独立PCM客户端以16kHz、20ms帧发送真实合成音频；没有把文字注入受测语音入口。输出24kHz音频保存为WAV，以时钟接收回执，不是物理扬声器测试。",'',
 '|轮次|真实转写|预期工具|受理|音频末端→工具回执秒|','|---|---|---|---|---:|']
 for t in turns:lines.append(f"|{t['turn']}|{t['ASR']}|{t['tool']}|{t['accepted']}|{t['audio_end_to_receipt_s']:.3f}|"if t['audio_end_to_receipt_s']is not None else f"|{t['turn']}|{t['ASR']}|{t['tool']}|{t['accepted']}|未返回|")
 lines+=['',f"- 转写逐字匹配：{sum(t['transcript_exact']for t in turns)}/4；工具正确受理：{sum(t['accepted']for t in turns)}/4。",f"- 暂停物理核查：{stats['pause_passed']}；暂停期动作数{len(forbidden)}；恢复后确有新原任务动作：{resumed}。",f"- 重复任务变更{stats['duplicate_mutations']}次，工具拒绝{len(rejected)}次；接收保存输出WAV {len(outputs)}个。",f"- 实际新Symbolic规划{kernel_calls}次，内核执行动作{actions}步；最终状态：{ar.get('final',{}).get('mode')}。",f"- 新本地角色请求边界审计{role_count}次，错误{len(role_errors)}；119份冻结源码漂移{len(drift)}。",'',
 '物理结果：`AUDIO_AUDIT.json`的symbolic_metrics为切换后任务的独立v2.5评分；如果没有完成，不将正确受理误写成完整任务成功。该预检有源任务持物后的受控观察窗口，不是自然打断成绩；没有覆盖QA、waiting、噪声、真人或全部T1–T8。','',
 '### 开发失败与本轮修复（全部保留）','',
 '|迭代|实际问题|处置|','|---|---|---|','|关闭v1|控制器初始化覆盖qacc_warmstart，严格状态校验失败，零动作|最后补回求解器缓存，重新做完整对照|','|释放完整流程v1恢复组|生成内核给两个停滞分支重复注入，启动校验失败，零动作|仅插入一次，新增测试|','|音频v1|缺少原外观图集，未发送音频|补齐原有7类参考图并核对哈希|','|音频v2|环境初始化与网页不同，初始图不一致，未发送音频|改用网页同一初始化/seed；之后初始图逐像素差0|','|音频v3|Native等待守在episode初始手位，抵消动作|每个新请求绑定当前手位，旧失败中止留存|','|音频v4|日志重复传simulation_time，网关退出|移除重复字段并补测试|','|音频v5|原任务刚完成导致版本竞态，切换请求被拒|只允许同录音、同任务、同语义版本的自动完成竞态重新核验；其他陈旧请求仍拒绝|','|音频v6|四条语音正确受理，切换后仍读取旧私有评分清单，零动作退出|将生成内核和每个新任务绑定本地独立评分清单，不给Agent评分内容|','|音频v7|规划正确进入bowl_plate，但动作回执缺少原内核要求的3个审计字段，零动作退出|沿用G2动作响应适配，补哈希和非缓存标记，动作数组不变|','',
 '完成收尾也改为当前完整任务验收统一产生回执，且完成后保持实际完成手位；不再用为受控触发屏蔽的原生成功读数覆盖当前完成状态。','',
 '[音频逐项审计](AUDIO_AUDIT.json) · [46项本地检查日志](LOCAL_CHECKS_FINAL.log) · [实现入口与边界](../../g22/README.md)','',
 '## 5. 当前判断','',
 '关闭预检候选不采用；归位后期观察恢复可用作受限开发候选，但小样本且两组均成功，没有证明总体SR提升。真实音频仅构成开发预检；完整自然生命周期、困难状态和扩大音频回归仍需分开验证。没有将本工作树切换到生产8787。']
 lines.insert(lines.index('## 5. 当前判断'),f"终态提示已绑定本次任务及{ar.get('final',{}).get('mode')}状态：{terminal_bound}；完整新终态PCM接收：{bool(ar.get('terminal_audio',{}).get('complete'))}。完整接收不等于真人试听通过。前一轮v8只有5秒尾部等待，未完成终态音频验收；该原始结果仍保留。\n")
 if(OUT/'NATURAL_RETURN_AUDIT.json').exists():
  n=load(OUT/'NATURAL_RETURN_AUDIT.json');index=lines.index('## 5. 当前判断')
  lines[index:index]=['## 4.1 原酒瓶卡住案例：真实自然源任务单例回归','',
   '本次真实执行原酒瓶任务到持物触发，然后直接切换，无reset、无预暂停。原同ID的G2.1为目标/完整失败；新增后期复查版本本次目标和完整任务均成功，切换后366控制步、约215.68秒全流程。225步观察到历史/当前K2误差≤2.44像素且手停滞，233步由Agent两次请求后松手，245步归位确认，后续抓碗与放盘子完成；没有重新抓酒瓶。',
   '源任务实际控制步原44、本次45，异步切换快照不同。此结果证明确有一条真实成功恢复路径，不足以把1例变化当总体成功率提升或严格单变量因果效果。9项物理/生命周期核查通过，完整v2.5评分重算一致，12次角色输入边界审计无错误。','',
   f"[独立审计](NATURAL_RETURN_AUDIT.json) · [完整环境视频]({n['new']['video']}) · [原始结果]({n['new']['file']})",'',
   '![本次酒瓶位置误差与夹爪开度](natural_return_trace.png)','']
 (OUT/'FINAL_REPORT.md').write_text('\n'.join(lines)+'\n');print(json.dumps(dict(turns=len(turns),accepted=sum(t['accepted']for t in turns),pause=stats['pause_passed'],symbolic_actions=actions,final=ar.get('final',{}).get('mode'))))
if __name__=='__main__':main()
