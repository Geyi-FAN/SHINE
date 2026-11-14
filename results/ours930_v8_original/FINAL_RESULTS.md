# Ours冻结v8：930次评测结果核查

核查时间：2026-11-14T16:52:41.715707+08:00。全部930次登记已结束；原458次首试和接口故障保留。

|分支|交互成功|目标成功|完整指令成功|问答成功|
|---|---:|---:|---:|---:|
|T1 单轮执行|120/120（100.00%）|120/120（100.00%）|—|—|
|T2 暂停与恢复|111/120（92.50%）|117/120（97.50%）|102/120（85.00%）|—|
|T3 执行中改任务|114/120（95.00%）|106/120（88.33%）|106/120（88.33%）|—|
|T4 指代与上下文|114/120（95.00%）|103/120（85.83%）|103/120（85.83%）|—|
|T5 澄清与确认|118/120（98.33%）|107/108（99.07%）|107/108（99.07%）|—|
|T6 执行中问答|—|—|—|87/90（96.67%）|
|T7 延后执行|108/120（90.00%）|109/120（90.83%）|99/120（82.50%）|—|
|T8 非指令处理|120/120（100.00%）|84/84（100.00%）|—|—|

非问答任务汇总：交互805/840（95.83%）；目标746/792（94.19%）；完整指令517/588（87.93%）。
T8语音—动作分离：24/24（100.00%）。

T5物理指标固定108例、T8物理指标固定84例；T7交接采用已登记45秒标准。T4保留1次接口中断；T4/T5的目标评分未知共4次，保留登记分母。
汇总字段核查：T7登记字段为interaction45，原通用汇总只查interaction会漏掉该行。本表按冻结的interaction45逐例汇总，不修改注册清单或原评分。

## T6检查

固定GLM-4.6V首次判分：87/90通过，3失败，0未知；不由Codex替换语义标签。
提问音频送达90/90；独立控制检查90/90无误控制；绑定错误0；实际图像78张、接收音频189段哈希复核通过。
78例使用实际问答图像；12例为当前任务/目的地问题，依据任务记录回答。参考帧与事实最大偏差80.05毫秒，阈值100毫秒。
播报需在问题结束后20秒内开始正确回答、40秒内完整播完，并在45秒观察窗口无误控制。有效语义失败不重试，格式错误至多一次修复。
在线视觉回答来自Qwen3.8-max；其中1例复核在14秒总时限被AbortError中止，正确候选未形成最终播报，该首试仍按未回答保留。该时限为现有运行规则，未在本轮检查中放宽。
内容证据来自生成文本与实际接收PCM的绑定，尚未完成独立输出音频转写；尚无独立真人校准。

|问题类别|成功/总数|成功率|
|---|---:|---:|
|T6Q_ABSENT_TENNIS|9/9|100.00%|
|T6Q_BOWL_CONTENTS|8/9|88.89%|
|T6Q_BOWL_PLATE|9/9|100.00%|
|T6Q_CHEESE_BOWL|8/9|88.89%|
|T6Q_CURRENT_ACTION|9/9|100.00%|
|T6Q_DRAWER_CONTENTS|9/9|100.00%|
|T6Q_DRAWER_STATE|9/9|100.00%|
|T6Q_EXTRA|8/9|88.89%|
|T6Q_STOVE|9/9|100.00%|
|T6Q_WINE_LOCATION|9/9|100.00%|

### 未通过案例

- `T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00`：Is the cheese outside the bowl?
  实际播报：奶酪仍在夹爪中。 | 机械臂已开始执行当前任务。
  固定模型原因：no_answer；The robot did not answer the yes/no question about whether the cheese is outside the bowl. The provided spoken outputs are progress notices and do not address the asked proposition.
  判分目录：`/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/judge90_live/c9efb695b1bc54859d2f6d80`。
- `T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02`：Is the bowl empty?
  实际播报：Snapshot analysis failed; no visual contents were confirmed. | 机械臂已开始执行当前任务。
  固定模型原因：no_answer；The robot provided no answer to the question 'Is the bowl empty?'. The first output states 'Snapshot analysis failed; no visual contents were confirmed.' and the second output is a task progress notice, neither of which addresses the bowl's emptiness. The bowl is visible in the WRIST image and its contents can be observed, so the question is answerable.
  判分目录：`/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/judge90_live/c600524ef7ef74a0195d36c6`。
- `T6Q_EXTRA_P2_S1__MV90V2_V03_B01`：How many wine bottles do you see?
  实际播报：当前画面可见2个酒瓶：一个黑色酒瓶在炉灶旁，另一个红褐色酒瓶在木质酒架顶部。 | 机械臂已开始执行当前任务。
  固定模型原因：wrong_count；The robot claimed to see 2 wine bottles, but the reference facts and physical instance inventory show only 1 wine bottle exists in the scene. The claim about 2 wine bottles is contradicted by the evidence.
  判分目录：`/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/judge90_live/3e700e8be22a81fa180d93da`。

## 结论边界

同一C3r运行版本、π0.5 E3 744/30000、云04四角色；未修改模型、提示词和冻结判分规则。
此次只修复收尾监控的跨文件读取时间差，原错误已归档；无新增机器人rollout、无按结果挑选重试。
本轮采用已披露的承托力测量修订与T5客户端修复，旧表并非全部同条件；这些数据已用于开发，不是独立封存测试。

[完整指标CSV](result_check_20261114/METRICS.csv) · [T6逐例问答](result_check_20261114/T6_CASES90.csv) · [T6失败列表](result_check_20261114/T6_FAILURES.csv) · [T6核查JSON](result_check_20261114/T6_AUDIT.json)


## T6固定判分一致性复核

按匿名包哈希选取10例，最终判分与语义判断均10/10一致；首轮90例未覆盖。该预选子集恰好均为通过例，不代表失败边界已验证，不能替代真人校准。

[三例失败的原话、实际播报、图像与环境视频](result_check_20261114/T6_REVIEW.md) · [一致性复核记录](T6_judge_reliability_20261114/RESULTS.json)
