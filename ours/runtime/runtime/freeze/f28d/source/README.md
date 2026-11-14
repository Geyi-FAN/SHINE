# Agent 规划＋Oracle 阶段完成判断＋YOLO 位置

本模块是 VoiceHarness 代码库中的独立在线验证入口。Agent 依据用户原话和截至当前的仿真物理状态生成计划及 subgoal；脚本校验并绑定 YOLO 点，交给冻结 V3-R 执行。它不是全非 Oracle 系统，尚未替换 VoiceHarness 的音频任务主循环。

## 权威判据

使用 `/mnt/disk_4/geyi/smolvla_eval/benchmark_metrics`，配置为
`configs/v2.5.0-candidate.json`，版本 `2.5.0-candidate`。
不再使用 physical v2.1 的归位/关闭阈值。

- 通用归位：35 mm、连续 5 步；特定“原任务打开顶层抽屉并放碗”场景按 v2.5 语义采用 70 mm。
- 支撑最近 5 步至少 4 步且当前支撑；释放最近 3 步无接触。
- 当前 Agent subgoal 承诺稳定释放时，完成监控采用 5 步位置直径不超过 5 mm；显式 `_clear` 操作再检查 3 步 80 mm 撤离。
- 关闭：间隙不超过 10 mm、连续 5 步。
- 高处无支撑释放通过 v2.5 `high_releases` 检测，报告失败事件，不能写成完成。
- 抓持是控制辅助：连续 5 步双侧接触、机器人接触且无支撑，不是新增 benchmark 得分条件。
- 原生目标、Instruction 得分与执行阶段事件分离。评分使用冻结的原始 benchmark 契约，不使用 Agent 自己生成的计划给自己评分。
- 当前短 rollout 沿用现行 v2.5 baseline 的首次原生最终目标停止方式，没有阶段超时跳过；总控制步预算单独记录。不能把 `native_target_reached` 等同于完整指令成功。

## 数据边界

Agent 输入只有：`user_message`、`physical_state`、`completed_events`、`reference_availability`、episode/task/frame 标识和混合实验说明。

`physical_state` 提供持物、接触/支撑、归位状态、抽屉开闭和当前原生关系。它不提供三维坐标或像素 GT，不提供 Oracle 的 stage index、标准 subgoal、未来历史、案例契约或隐藏保持约束。归位确认所需初始三维位置仅留在仿真监控器内部。

完整 user_message 使用 case 的 `instruction_original`，没有这一字段才用 `instruction`。例如“把奶酪放入碗”不会补入数据集后来追加的“保持碗不动”。评测侧如果仍包含该追加要求，结果明确记录 `scoring_instruction_differs_from_raw`，不能把这类差异都归咎于 Agent 理解错误。

通用 `operators.json` 是所有场景共享的训练表达词汇；Agent 选择 operation 并亲自输出当前 subgoal、位置引用和最终 prompt 模板。校验脚本只拒绝错误并反馈，不替换或拼造 subgoal。坐标绑定仅替换 Agent 选定的占位符。

## 位置与执行

- YOLO26s-pose 的输入仅为 MAIN256 RGB；每次策略请求同步推理一次，不由 Agent 发起定位工具调用。
- K1/K3 当前点与当前策略图像同帧；episode-start K2 由初始化图像预测后冻结；接管 K2 由接管图像预测后冻结。
- 转换：`((xy256 + 0.5) * 0.875 - 0.5)[::-1]`，保存浮点值，最终文本/箭头共同四舍六入五成双取整。
- 检测及关键点置信度门限现各为 0.1（2026-10-25 用户指定；初轮联调为 0.25，可用 HYBRID_DET_CONF / HYBRID_KPT_CONF 配置）。缺点不替换 K 类型、不读取 GT、不用零点占位。
- V3-R 仅归位阶段绘制与原训练一致的红箭头。当前图、Wrist、8 维 state 和动作接口保持原实现。
- Agent 只在开始或监控器报告当前操作结束后调用。监控器不会选择下一步；阶段改变时清除剩余动作队列。
- 动态失检会停止下发并报告 `need_observation`。主动补观测/恢复动作和“全开抽屉 K3 缓存”尚未接入，本轮不能宣称已经解决失检恢复。
- 仿真等待 API 时暂停推进。日志中的端到端耗时包含 Agent/IPC/模型，不等于真机实时闭环延迟。

## 文件

| 文件 | 职责 |
|---|---|
| `prompt.txt`、`operators.json` | Agent 通用提示与训练兼容词汇 |
| `planner.py` | Agent 调用、输入白名单、输出校验和最多两次纠错 |
| `completion.py` | 无 Oracle 计划输入的 v2.5 物理事实/完成事件监控 |
| `yolo_worker.py`、`points.py` | 常驻 YOLO、三个时间源记忆、同帧绑定 |
| `run.py` | 独立仿真闭环、视频、原始调用与独立 v2.5 评分 |
| `serve_policy.py` | 原 π0.5 服务接口，元数据注明混合实验来源 |
| `live_smoke.sh` | 启动冻结策略服务和三个代表性短 rollout |

## 本机复现

```bash
source /mnt/disk_2/geyi/voice_pi05_harness/hybrid_planner/env.sh

# 仅场景恢复、YOLO、真实 Agent、prompt 绑定；不执行动作。
"$SIM_PYTHON" /mnt/disk_2/geyi/voice_pi05_harness/hybrid_planner/run.py \
  --snapshot-only --out /mnt/disk_4/geyi/hybrid_snapshot_NEW

# 先确认 GPU 空闲；GPU0 为 π0.5，GPU3 为 YOLO。
tmux new-session -d -s hybrid_v25_NEW \
 'bash /mnt/disk_2/geyi/voice_pi05_harness/hybrid_planner/live_smoke.sh /mnt/disk_4/geyi/hybrid_live_NEW 0 19865 240'
```

输出目录必须是新的，保留失败尝试。默认策略为本机 Hard880 V3-R full-LIBERO 30000 权重导出；归档本身没有完整训练身份，EMA 身份不能仅凭服务元数据独立确认。它是冻结策略的接口验证，不是新一轮训练或与旧实验公平配对的成绩。YOLO 使用本机已训练的 `yolo26s_pose_50ep/weights/best.pt`，Agent 使用 `qwen3.8-max` 非 thinking JSON 输出，凭证只从现有 Harness 私有配置读取。

每例保存 Agent 完整输入/输出与纠错、YOLO 原始预测、point 图、策略输入视频、动作及逐步状态 trace、v2.5 评分。源码与规则哈希见实验目录报告。

## M1 静态场景缓存（2026-10-25）

默认启用；`HYBRID_STATIC_CACHE=0` 可禁用复用，用于对照。权重、Agent prompt、π0.5 文本格式、V3-R 仅归位画点、YOLO 0.1 双门限均未修改。

`scene_memory.py` 管理当前检测和静态缓存，`Points.available/bind` 共用解析接口。对象/K 类型错误、越界、非有限坐标、置信度不足不会进入记忆。可信本帧点优先；本帧缺失时使用仍有效的静态缓存。固定 MAIN 相机与256→224变换签名必须一致。

当前支持 bowl/plate/cheese/wine_bottle 的 K1、K3；初始化/接管 K2 保持原有冻结存储。支持能解析到仿真设施 body 的 stove/cabinet_top/wine_rack/table_front placement K3。无法解析设施 body 时只使用本帧检测，不缓存。抽屉把手、炉灶按钮、抽屉内部暂不缓存，不追踪动态点。

可移动物体需要最近5个控制观测均有支撑、无机器人接触，位置及四元数各分量变化≤1e-5；每个控制步复核，缓存相对来源位姿变化超过此容差立即失效。该容差是保守的缓存有效性参数，不是任务完成阈值。相机变化、证据缺失同样失效。没有固定超时：只有持续物理证据证明静止才可继续复用，不是无限无条件缓存。首次证据不足时仍允许使用可信当前检测，但不建立缓存。

静态点相对缓存跳变>10个MAIN224像素时，先拒绝该候选并保留有效旧点；两个不同帧的新候选相差≤3像素才接受新位置。这只是异常抑制，不能保证识别身份永远正确。当前数据场景每种物体只有一个实例，尚未实现多同类物体跟踪。

仿真位姿只用于缓存有效性；不投影真值、不回填坐标、不传给Agent或π0.5。新实验应标注：Agent规划 + YOLO位置 + Oracle阶段及缓存有效性判断。

日志：每例 `points/memory_events.jsonl` 记录 update/reject/invalidate/resolve；动作chunk的marker增加 resolution(fresh/cached/historical)、source_frame、age_steps、camera_transform_id。`result.json` 增加 scene_memory_counts。cached 的来源帧保持原检测帧，文本及绘图仍统一最终取整。

验证资料：`/mnt/disk_4/geyi/scene_memory_M1_20261025/`。原始动作与检测回放中，第86步成功解析83步的碗K3缓存；这不是新策略完成任务的成功率评测。
