"""Read-only evidence index. Does not mutate verdicts or include secrets."""
import collections,json,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path('/mnt/disk_4/geyi/voice_audio_unified_repair_20261102');B=Path(__file__).resolve().parents[1]
def load(p):
 try:return json.loads(p.read_text())
 except(OSError,ValueError):return None
def main():
 run=ROOT/'R5b/formal24_r5b_20261102';regression=ROOT/'R6/regression18b/regression18_r6b_20261102';expanded=ROOT/'R6/expanded96/formal96_r6b_20261102'
 rows=['# 音频24→96回归与主页面统一接入','', '更新时间：'+datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),'','本报告读取实际文件，不把工程文字测试、历史中止轮或无音频尝试合并成有效音频成绩。','', '## 固定条件与本轮修复','', '- 动作模型：SmolVLA E3 v4 raw30000；动作权重、YOLO权重及本地四角色提示词未重训或替换。MAIN/WRIST256、原8维state、4步动作执行。','- 新统一服务：评测和计划上线的网页共用 `continuation/service_r5.py` + `continuation/live_gateway.py`。Agent生成计划与子任务；脚本终验读取当前实际授权任务，不读取私有case标签来决定用户目标。','- 保留仿真辅助的M1有效性与最终物理验收，不能称完全无Oracle。中间规划仍为F28d观测流程。','- 释放/稳定终验修复：奶酪分支不再覆盖释放门槛；关闭/打开脱离检查不引用不存在的奶酪局部变量。','- 原话澄清：开放对象回答绑定实际用户字面对象，保留原完整请求。恢复播报依据真实工具回执并复核后续实际物理状态，不由最后一条旧快照单独判错。','- 保持观测必须出现实际新增40个物理步；被明确暂停时禁止推进世界。','- 语音收发由独立工作线程按20ms节奏运行，逐片段核对接收PCM和真实时钟。','', '## 正式音频轮次','', '|轮次|完成情况|交互|目标|完整指令|输入质量|','|---|---|---|---|---|---|']
 for label,p in [('同24例原冻结评分',run),('修复后18例',regression),('扩展96例',expanded)]:
  s=load(p/'reports/summary.json');done=(p/'COMPLETED.json').exists();verdicts=load(p/'reports/verdicts.json')or[]
  if s:
   metric=lambda k:f"{s['micro'][k]['passed']}/{s['micro'][k]['denominator']}"
   rows.append('|'+label+'|'+('完成'if done else'进行中；仅部分证据')+'|'+ '|'.join(metric(k)for k in ['interaction','target','instruction'])+'|'+str(s.get('valid_for_audio_benchmark'))+'|')
  else:rows.append('|'+label+'|尚无完整结果|—|—|—|—|')
 rows+=['','同24例收发质量：24例、52段PCM全部通过。原冻结评分不覆盖。独立修正：真实容器接触可证明支撑；暂停检查只用于确实要求暂停的脚本；已绑定同一输入和成功工具回执的尾部播报可计入，必须真实播放完成。修正后的原24例为Interaction15/24、Target19/24、Instruction19/24，这属于评分修正，不是系统重新运行带来的提升。','','|轮次/独立评分|交互|目标|完整指令|','|---|---|---|---|']
 for label,p in [('24',run),('18',regression),('96',expanded)]:
  for seconds in [10,45]:
   s=load(p/f'reports_audited/v1.7_wait{seconds}/summary.json')
   if s:rows.append('|'+label+f' / waiting{seconds}秒|'+ '|'.join(str(s['micro'][k]['passed'])+'/'+str(s['micro'][k]['denominator'])for k in ['interaction','target','instruction'])+'|')
 rows+=['','只有完成轮次才解释其总体成功率。96例的物理指标按81个适用实例计；前置失败和云端故障不通过删除案例提高成功率。使用单一审核合成音色，不是真人、噪声或独立泛化测试。关键词时间未人工标注，延迟使用音频末端代理。','','## 逐例未通过项','']
 for label,p in [('24',run),('18',regression),('96',expanded)]:
  for v in load(p/'reports/verdicts.json')or[]:
   if v['interaction']=='pass'and v.get('instruction')in('pass','not_applicable'):continue
   d=p/'cases'/v['case_id'];rows+=[f"### {label} / {v['case_id']}",'',f"交互={v['interaction']}，目标={v.get('target')}，完整指令={v.get('instruction')}。未通过项：{', '.join(v.get('failures',[]))or'见逐项评分'}。",'',f"[逐项判定]({d/'verdict.json'}) · [实际输入/输出]({d/'result.json'}) · [视频]({d/'gateway_environment.mp4'}) · [收发质量]({d/'AUDIO_QUALITY.json'})",'']
 rows+=['## 本地与网页验证（独立于音频成功率）','','|验证|实际状态|','|---|---|']
 for label,p in [('真实文字生命周期',ROOT/'R4/service_lifecycle_smoke_105515/RESULT.json'),('真实HTTP/40步保持预检',next(iter(sorted((ROOT/'R5').glob('transport_preflight_*/RESULT.json'),reverse=True)),ROOT/'missing')),('主页面只读联调',ROOT/'ui_readonly/RESULT.json'),('主页面真实浏览器音频',ROOT/'ui_main_audio/RESULT.json')]:
  r=load(p);rows.append('|'+label+'|'+('通过'if r and r.get('passed')else'未完成或未通过')+'；[证据]('+str(p)+')|')
 deployment=load(ROOT/'deployment/DEPLOYMENT.json');rows+=['','主8787部署状态：'+(str(deployment['state'])if deployment else'现用后端未切换；仅完成候选接入及隔离联调。'),'','## 文件与复盘入口','',f'- [实时进度]({ROOT/"reports/LIVE_AUDIO_PROGRESS.json"})',f'- [同24例完整输出]({run/"reports/RESULTS.md"})',f'- [96例完整输出]({expanded/"reports/RESULTS.md"})',f'- [部署记录]({ROOT/"deployment/DEPLOYMENT.json"})',f'- [主框架进展](/mnt/disk_2/geyi/voice_pi05_harness/docs/integrations/branch_updates/CORE.md)','', '## 历史轮的处理','', 'R3中止：发现真实终验代码问题；R4中止：外层拒绝评测收尾空POST；R5第一尝试在发音频前因迁移导入路径中止。各目录的ABORTED_IMPLEMENTATION与原始结果保留。R5b为修复后从第一例开始的整轮，不拼接前缀成功案例。旧24例还存在实时发送节奏不合格，不能当有效主表基线。','']
 (ROOT/'reports/CONTINUATION_REPORT.md').write_text('\n'.join(rows))
if __name__=='__main__':main()
