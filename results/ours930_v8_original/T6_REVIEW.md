# T6 90例结果检查与三例失败复盘

固定GLM-4.6V首轮：87/90（96.67%），3例失败、0例未知。首轮90个标签均保留，不由Codex覆盖。

- 提问音频送达90/90；45秒控制观察窗口无误控制90/90。
- 189段实际接收播报的PCM哈希与绑定证据一致，0错绑；这是字节/回执核查，不是独立听音转写。
- 78例实际问答图像＋12例当前任务/目的地问题；参考事实最大时间偏差80.05毫秒，冻结阈值100毫秒。
- 固定10例判分一致性复核：最终分数与语义判定均10/10一致；这10例由匿名包哈希预先选定，恰好全部是首轮通过例，不能据此宣称失败边界已验证。
- 一致性复核不替换首轮标签，尚无独立真人校准。

## T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00

用户原话：Is the cheese outside the bowl?

识别文字：Is the cheese outside the bowl?

实际播报：

1. 奶酪仍在夹爪中。 [音频](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00__R01/cases/T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00/client/output_1_1.wav)；开始延迟8.854秒，完整延迟10.866000175476074秒。

2. 机械臂已开始执行当前任务。 [音频](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00__R01/cases/T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00/client/output_1_2.wav)；开始延迟11.629秒，完整延迟14.360000133514404秒。

固定判分：**失败**；`no_answer`。

判分原文：The robot did not answer the yes/no question about whether the cheese is outside the bowl. The provided spoken outputs are progress notices and do not address the asked proposition.

原因检查：只回答了夹持状态，未明确回答内外关系。 实际图像与独立事实均显示奶酪被抓持；按冻结判分，回答仍未覆盖用户所问的奶酪与碗的关系。当前分数不改。

[实际发给问答模型的图像](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/frames/06_00.jpg)

[环境视频（语音另见上方WAV）](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/review_media/06_environment.mp4)

[原始问答调用记录](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00__R01/cases/T6Q_CHEESE_BOWL_P1_S1__MV90V2_V00_B00/qa_audit.jsonl) · [固定判分记录](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/judge90_live/c9efb695b1bc54859d2f6d80/SCORE.json)

## T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02

用户原话：Is the bowl empty?

识别文字：Is the bowl empty?

实际播报：

1. Snapshot analysis failed; no visual contents were confirmed. [音频](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02__R01/cases/T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02/client/output_1_1.wav)；开始延迟18.013秒，完整延迟22.58399987220764秒。

2. 机械臂已开始执行当前任务。 [音频](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02__R01/cases/T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02/client/output_1_2.wav)；开始延迟28.857秒，完整延迟31.58899998664856秒。

固定判分：**失败**；`no_answer`。

判分原文：The robot provided no answer to the question 'Is the bowl empty?'. The first output states 'Snapshot analysis failed; no visual contents were confirmed.' and the second output is a task progress notice, neither of which addresses the bowl's emptiness. The bowl is visible in the WRIST image and its contents can be observed, so the question is answerable.

原因检查：视觉复核14秒总时限触发AbortError，初始候选没有成为最终回答。 原始候选是“碗内没有可见物体，看起来是空的”，最终播报却是分析失败；按未回答保留，不能用未播出的候选代替实际回答。

[实际发给问答模型的图像](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/frames/30_00.jpg)

[环境视频（语音另见上方WAV）](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/review_media/30_environment.mp4)

[原始问答调用记录](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02__R01/cases/T6Q_BOWL_CONTENTS_P1_S2__MV90V2_V00_B02/qa_audit.jsonl) · [固定判分记录](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/judge90_live/c600524ef7ef74a0195d36c6/SCORE.json)

## T6Q_EXTRA_P2_S1__MV90V2_V03_B01

用户原话：How many wine bottles do you see?

识别文字：How many wine bottles do you see?

实际播报：

1. 当前画面可见2个酒瓶：一个黑色酒瓶在炉灶旁，另一个红褐色酒瓶在木质酒架顶部。 [音频](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_EXTRA_P2_S1__MV90V2_V03_B01__R01/cases/T6Q_EXTRA_P2_S1__MV90V2_V03_B01/client/output_1_1.wav)；开始延迟12.319秒，完整延迟20.73099994659424秒。

2. 机械臂已开始执行当前任务。 [音频](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_EXTRA_P2_S1__MV90V2_V03_B01__R01/cases/T6Q_EXTRA_P2_S1__MV90V2_V03_B01/client/output_1_2.wav)；开始延迟21.204秒，完整延迟23.93499994277954秒。

固定判分：**失败**；`wrong_count`。

判分原文：The robot claimed to see 2 wine bottles, but the reference facts and physical instance inventory show only 1 wine bottle exists in the scene. The claim about 2 wine bottles is contradicted by the evidence.

原因检查：将酒架顶部的红褐色木质结构认成额外酒瓶。 实际场景库存只有一个酒瓶；主视角的酒架端部被候选与复核两次认错。属于计数/身份判断错误，不能硬编码答案为1来修分。

[实际发给问答模型的图像](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/frames/40_00.jpg)

[环境视频（语音另见上方WAV）](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/review_media/40_environment.mp4)

[原始问答调用记录](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/runs/formal930_v1/T6__T6Q_EXTRA_P2_S1__MV90V2_V03_B01__R01/cases/T6Q_EXTRA_P2_S1__MV90V2_V03_B01/qa_audit.jsonl) · [固定判分记录](/mnt/disk_4/geyi/audio_switch_benchmark/deployments/ours_full930_readiness_20261114/finalization_formal930_v1/judge90_live/3e700e8be22a81fa180d93da/SCORE.json)

## 当前判断

T6的3例失败已经有可复盘的证据：一例回答不完整，一例复核超时降级，一例视觉计数错误。本轮未重跑机器人、未放宽评分阈值、未更新提示词。
后续若改问答策略，应另建运行版本，与本轮结果分开；人工校准完成前，保留“模型辅助判分”的结论边界。
