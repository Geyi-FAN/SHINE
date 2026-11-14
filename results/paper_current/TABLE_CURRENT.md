# 论文填写用：现有结果，2026-11-14

**这是已有成绩存档，还不是新公共协议1770次重测后的最终公平对比表。** 新评测会另存版本，不覆盖以下数字。

|任务|指标|ELLSA（历史）|RoboOmni（历史）|ASR＋π0.5（旧版）|ASR＋Agent（旧版Oracle辅助）|Ours v8（已完成930）|
|---|---|---:|---:|---:|---:|---:|
|Spoken Execution|Inter. SR|35.00（旧物理口径）|4.17（旧物理口径）|0.00|94.17|100.00|
|Spoken Execution|Target SR|35.00|4.17|96.67|86.67|100.00|
|Pause & Resume|Inter. SR|34.38（旧物理口径）|0.00（旧物理口径）|0.00|55.83|92.50|
|Pause & Resume|Target SR|34.38|0.00|80.83|85.83|97.50|
|Pause & Resume|Instr. SR|21.88|0.00|58.33|60.00|85.00|
|Goal Revision|Inter. SR|0.00（旧物理口径）|0.83（旧物理口径）|0.00|7.50|95.00|
|Goal Revision|Target SR|0.00|0.83|75.00|74.17|88.33|
|Goal Revision|Instr. SR|0.00|0.00|51.67|60.83|88.33|
|Contextual Reference|Inter. SR|7.50（旧物理口径）|0.00（旧物理口径）|0.00|68.33|95.00|
|Contextual Reference|Target SR|7.50|0.00|88.33|66.67|85.83|
|Contextual Reference|Instr. SR|7.50|0.00|71.67|65.83|85.83|
|Clarify & Confirm|Inter. SR|0.00（旧物理口径）|0.00（旧物理口径）|0.00|68.33|98.33|
|Clarify & Confirm|Target SR|0.00|0.00|0.00|72.22|99.07|
|Clarify & Confirm|Instr. SR|0.00|0.00|0.00|70.37|99.07|
|Deferred Execution|Inter. SR|10.00（旧物理口径）|7.50（旧物理口径）|0.00|40.83|90.00|
|Deferred Execution|Target SR|10.00|7.50|50.00|50.83|90.83|
|Deferred Execution|Instr. SR|0.00|0.00|12.50|47.50|82.50|
|Non-command Handling|Inter. SR|10.00|6.67|0.00|88.33|100.00|
|Non-command Handling|Target SR|42.86|0.00|42.86|98.81|100.00|
|Non-command Handling|S-A Sep.|0.00|0.00|N/E|100.00|100.00|
|Concurrent QA|QA Success|0.00（0/9，旧条件分母）|0.00（0/19，旧条件分母）|N/S|Pending|96.67|

- 三种受控方法（ASR＋π0.5、ASR＋Agent、Ours）使用π0.5 E3 744/30000导出参数；不能擅自写成EMA。ELLSA、RoboOmni保留各自原架构和执行器。
- Ours共930注册首试，T1–T5/T7/T8各120，T6固定90；Target分母T5为108、T8为84；Instruction只报告适用任务。未知评分保留在分母。
- Ours数值来自 results/ours930_v8_original/FINAL_METRICS.csv；T6固定GLM-4.6V v4/r3首次判分87/90，未完成人工双评校准。
- 旧ASR＋Agent获得所选位置和阶段完成Oracle辅助；它的T6已采集90例，但旧评分因图像/事实时刻未对齐而阻塞，待核验不等于0。
- 纯ASR不新增规划、坐标、语义停止路由或TTS；不能把其交互0解释成所有语音均未识别。T6不支持且未运行。
- 旧版基线与Ours的T3准备、动作种子、T5音频回执绑定及承托测量存在差异。新版本将统一准备/种子/评分，保留方法本身的区别。
- 数据用于开发和多轮修复，不是独立封存测试；不要把同一脚本的三次重复称为三个独立任务。

当前结论：Ours现有成绩可以作为带版本说明的论文草表；新公平比较须等待新两条基线及Ours公共复核完成。

2026-11-14补充验证：Ours全部840条非QA经共同评分复核，异常0，三项主指标逐例变化0；T6原固定判分87/90及T8分离24/24保留。Ours列现已获得共同评分复核，新两条基线列仍待正式重测更新。

外部列说明：本次仅加入ELLSA和RoboOmni已有历史汇总，没有新评测或改分。标为“旧物理口径”的Inter单元格不能与统一交互成功率直接排名；T2、T5等分母亦有差异。T6分别为旧条件比例0/9、0/19，不是固定90例的统一QA成绩。所有42个外部单元格的原成功数、分母及口径见 [逐格说明](EXTERNAL_METRIC_NOTES.csv) 和 [来源计数](EXTERNAL_SOURCE_COUNTS.json)；详细边界见 [历史核查](../historical_comparison/ALIGNMENT_AUDIT.md)。本表数值单位为%。
