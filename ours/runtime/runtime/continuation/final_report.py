"""Evidence-only consolidation. Raw runs/verdicts are never overwritten."""
import csv,json,time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102')
MAIN=Path('/mnt/disk_2/geyi/voice_pi05_harness')
NAMES={'T1':'单轮执行','T2':'暂停、保持与恢复','T3':'即时修改任务','T4':'指代与历史位置','T5':'澄清、改口与确认','T6':'执行中问答','T7':'waiting等待交接','T8':'应和声、否定与语音打断'}
RUNS=[('恢复后的同24例',ROOT/'R5b/formal24_r5b_20261102'),('R6专项18例',ROOT/'R6/regression18b/regression18_r6b_20261102'),('R7问答修复3例',ROOT/'R7/qa3/qa3_r7_20261102'),('R8独立播报绑定3例',ROOT/'R8/qa3/qa3_r8_20261102'),('R8扩展96例',ROOT/'R8/expanded96/formal96_r8_20261102')]
def load(p):
 try:return json.loads(p.read_text())
 except(OSError,ValueError):return None
def score_paths(run):
 for name in ['reports_audited/v1.9_wait45','reports_audited/v1.8_wait45','reports_audited/v1.7_wait45','reports']:
  p=run/name
  if(p/'summary.json').exists():return p
 return run/'reports'
def value(s,k):
 m=s['micro'][k];return f"{m['passed']}/{m['denominator']}（{m['rate']*100:.2f}%）"if m['rate']is not None else'不适用'
def main():
 out=ROOT/'reports';out.mkdir(exist_ok=True)
 rows=['# 音频回归、修复和主网页统一接入记录','', '更新时间：'+datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),'','各轮首次结果单独保留；工程文字测试、离线图片对照和正式合成语音结果不混合。正在运行时仅显示累计证据，不能将部分成功数解释成最终成功率。','', '## 当前状态','',f"顺序编排：[R8_FULL_CHAIN.json]({ROOT/'R8_FULL_CHAIN.json'})。"]
 deployment=load(ROOT/'deployment/DEPLOYMENT.json');ui=load(ROOT/'ui_main_audio/RESULT.json')
 rows += [f"主网页部署：{deployment.get('state')if deployment else'未部署'}；浏览器音频自动验收：{'通过'if ui and ui.get('passed')else'未通过或未完成'}。",'', '## 固定设置与解释边界','', '- 动作执行器仍为SmolVLA E3 v4 raw30000，权重、归一化、YOLO和四个执行Agent的提示词未重训/替换。语音理解仍使用云端Qwen；不能称整套系统全本地。','- Agent负责计划和subgoal；脚本校验并绑定YOLO/M1坐标；相同服务内核拥有唯一env.step。episode初始化建记忆，改任务不reset，语音重连不重建环境，显式reset才建立新episode。M1仍有仿真辅助有效性管理，终态验收仍读取Benchmark物理事实。','- 评分使用v2.5物理规则；Interaction为交互协议成功，Target为目标达成，Instruction还要求顺序、释放、保持等。阴性/只要求追问的案例不进入物理分母，始终进入交互分母。','- 暂停5秒、下发20秒、首个新动作45秒、问答20/40秒、每目标1200动作步/600秒、真实40步保持等不因单例失败而放宽。waiting补报原10秒与45秒；正确交接但超过门槛仍计为失败。','- 主网页“功能接入验收”和Benchmark时限达标分开；FUNCTIONAL_GATE不改动任何失败判分。','- 音频来自已人工试听的Tina合成音色，按20ms实时输入，逐段核对接收PCM/时钟；关键词时刻未人工标注，延迟使用音频末端代理。不是真人、噪声或独立泛化成绩。','', '## 各轮实际结果','', '|轮次|状态|评分|Interaction|Target|Instruction|音频质量|','|---|---|---|---|---|---|---|']
 for label,run in RUNS:
  report=score_paths(run);s=load(report/'summary.json');done=(run/'COMPLETED.json').exists();quality=[load(f)for f in(run/'cases').glob('*/AUDIO_QUALITY.json')];quality=[q for q in quality if q]
  if not s:rows.append(f'|{label}|尚无结果|—|—|—|—|—|');continue
  status='完成'if done else f'进行中：{s["received"]}/{s["planned"]}'
  q=f'{sum(bool(q.get("passed"))for q in quality)}/{len(quality)}例；{sum(len(q.get("clips",[]))for q in quality)}段'
  rows.append('|'+label+'|'+status+'|'+report.name+'|'+'|'.join(value(s,k)for k in ['interaction','target','instruction'])+'|'+q+'|')
 rows += ['','原24例的冻结v1.4原判分为14/24、19/24、17/24。独立修正容器接触证据、暂停反例适用性及真实回执播报归属后，旧证据重评分曾为15/24、19/24、19/24；这是评分修正，不能宣称是系统重新运行提升。全部原判分保留。v1.8进一步把位置问答对齐到实际采图时刻，而不是把整个运动过程当作同一状态。','', '## 修复内容与实际验证','', '|问题|修改|证据边界|','|---|---|---|','|复合停止被漏识别|明确Stop＋保持持物走快速暂停；保护否定/问句|R6三状态暂停/恢复通过；世界步数、时间、哈希不变|','|仅说对象就执行不完整任务|缺少目的地时拒绝下发；保留回答并继续追问|真实语音三状态澄清通过；独立工具负例拒绝后可继续绑定|','|waiting参数被拒绝后没有纠正|只对明确executed=false的已知参数拒绝开放有界重试|未知/超时不重放；实际首次结果和工具回执保留|','|把目的地当当前位置|去除高优先级禁止判断持物的冲突；图像＋本体状态；限定快照|同图三例旧提示均错、新提示均正确；真实QA3另列|','|问答跨自然完成被误作失效|以episode、task及语义版本绑定快照；新语音仍取消旧问答|4项身份检查；最终以实际音频与主网页结果为准|','|预算恢复马上再次耗尽|预算检查和恢复共用状态锁；显式恢复才追加预算|独立真实Native/Symbolic均4→8步，同任务/记忆；重复请求不追加|','|恢复后模型请求序号失步|成功发出并收到模型响应才推进序号|真实符号恢复通过；未取消/重启共享模型服务|','|waiting交接耗时长|只读预取同一措辞Agent结果，实际消费槽位才绑定|保留45秒失败：前两例约58/51秒；物理任务也有失败，不冒称解决|','|排队第二段音频没有开始回执|每段独立outputId开始回执，保留原整批回调；播报文本绑定生成与接收PCM哈希|R8新三例真实问答全部通过；不将旧R7轮人工改分|','|主网页启动没有仿真依赖|保留虚拟环境Python可执行文件软链，不解析成系统Python|配置及启动8项通过；在任何网页测试音频前修复|','', '## 96例分组','', '原24案例在96中保留相同源任务音频，其余前置采用公开文字授权同模型实际执行。原24子集独立配对；不是拼接不同修复轮的成功案例。T4_04三例“奶酪到炉灶”不属于十个普通训练指令，保留原分母并单独标注，不能把这组物理失败全部归因于语音。']
 expanded=RUNS[-1][1];report=score_paths(expanded);s=load(report/'summary.json');vs=load(report/'verdicts.json')or[]
 if s:
  rows+=['','|类别|Interaction|Target|Instruction|','|---|---|---|---|']
  for k,g in s['groups'].items():rows.append('|'+k+' '+NAMES[k]+'|'+'|'.join(f"{g[m]['passed']}/{g[m]['denominator']}"for m in ['interaction','target','instruction'])+'|')
  for seconds in [10,45]:
   ds=load(expanded/f'reports_audited/v1.9_wait{seconds}/summary.json')
   if ds:rows+=['',f'waiting门槛{seconds}秒时，整体Interaction：{value(ds,"interaction")}。']
  completed=[load(expanded/'cases'/v['case_id']/'result.json')or{}for v in vs];actual=sum(bool(r.get('precondition_validated'))and any(not t.get('prelude')for t in r.get('turns',[]))for r in completed)
  rows+=['',f'计划96例；当前有实际评分音频机会的已结束案例{actual}例。前置失败/未发音频的案例保留在计划分母中，不能把条件成功率当96例主结果。']
 rows+=['','## 主网页验收','',f'- [部署和模型身份]({ROOT/"deployment/DEPLOYMENT.json"})',f'- [功能放行与仍然超时的案例]({ROOT/"deployment/FUNCTIONAL_GATE.json"})',f'- [真实Chromium音频路径、暂停冻结、重连、reset]({ROOT/"ui_main_audio/RESULT.json"})',f'- [网页截图]({ROOT/"ui_main_audio/audio-session.png"})','', '浏览器测试使用公开标注的合成麦克风，走真实AudioWorklet/云端语音/工具/动作路径；不能视为真人麦克风硬件验收。主页面启用的动作执行器与独立评测相同，Codex不参与动作下发。','', '## 逐例复盘入口','']
 for label,run in RUNS:
  report=score_paths(run);rows +=[f'- {label}：[逐例输入/播报/视频/评分]({report/"RESULTS.md"}) · [CSV]({report/"cases.csv"}) · [原始判分]({run/"reports/summary.json"})']
 rows +=['',f'- [实时JSON]({ROOT/"reports/LIVE_AUDIO_PROGRESS.json"})',f'- [主框架进展]({MAIN/"docs/integrations/branch_updates/CORE.md"})','', '## 条件差异与限制','', '不同轮次集合不同，不能直接按总体百分比排名；R6为专项开发集、QA3为修复验证。动作权重不变不代表物理轨迹逐步相同，角色服务负载、源任务结果和异步时序会影响实际切换状态。96中的同24子集保留音频和场景，但使用了修复后的服务；GPU/运行时间不同，不宣称严格单变量因果增益。开发集被用于定位修复，不能替代冻结后的独立盲测。','']
 (out/'FINAL_REPORT.md').write_text('\n'.join(rows))
 print(json.dumps(dict(report=str(out/'FINAL_REPORT.md'),deployment=None if not deployment else deployment.get('state'),browser_passed=bool(ui and ui.get('passed')))))
if __name__=='__main__':main()
