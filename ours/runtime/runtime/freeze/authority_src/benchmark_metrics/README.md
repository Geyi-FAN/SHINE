# Small722 benchmark metrics — 2.5.0-candidate

这是当前候选评测标准的唯一实现入口。此次固化的是**配置、代码和语义可复现的候选版本**，不是宣布所有数值已经通过独立验证。旧报告、人工备注、冻结的模型 rollout 和旧 SGS/strict 分数不改写。

## 结构与原生 LIBERO 的关系

本地 LIBERO 的 `envs/problems/libero_tabletop_manipulation.py::_check_success` 对 BDDL 目标谓词做合取；`object_states/base_object_states.py::check_ontop` 使用 body origin、目标 site 和父物体接触；`objects/site_object.py::under` 使用严格局部边界。这里保留这些原生语义，将 Switch 特有的时序与指令约束放在上层，不向原生目标函数塞入额外稳定门槛。

| 文件 | 职责 |
|---|---|
| `configs/v2.5.0-candidate.json` | 唯一数值阈值、窗口、单位、候选状态 |
| `config.py` | 配置检查与确定性 SHA256 |
| `predicates.py` | 无状态物理谓词：距离、间隙、局部区域、稳定性 |
| `events.py` | 连续帧确认、归位完成、高处释放、保持违规 |
| `contracts.py` | 原始 case 指令编译出的显式契约检查 |
| `adapters.py` | 冻结轨迹输入适配；缺少证据保持未知 |
| `evaluator.py` | 事件顺序、显式约束和每回合指标 |
| `reasons.py` | 稳定原因码及中文解释 |
| `cli.py` | 离线批处理、汇总与不可覆盖输出 |
| `controller.py` | 独立的抓持交接候选逻辑，不参与 benchmark 分数 |
| `tests/` | 边界、时序、缺证据、已审核样本回归 |

依赖 Python 标准库，Python 3.8+；不导入模型、MuJoCo、视频服务或历史分析脚本。函数入口：`evaluate_episode(trace, case, canonical_contract, rules)`。

## 固化的判据

所有距离与关节量在配置内使用 **m**，窗口使用**控制步**；时间只在显示时按20Hz换算。以下数值只作说明，以 JSON 为权威来源。

| 判据 | 候选定义 |
|---|---|
| Native Target SR | 策略阶段任意一步原生目标成立；不计 hold 阶段独有成功；随后丢失另记诊断 |
| Adjusted Target SR | Switch 酒瓶上架局部 Y 每侧+5mm；盘子炉灶前区域局部 X/Y 每侧+5mm；原 body origin、Z边界、接触要求保留。Normal LIBERO不扩展 |
| 通用归位 | 本回合初始参考点三维距离≤35mm，连续5步 |
| 特殊归位 | source task=3、原任务为上层抽屉放碗、归位对象为碗时≤70mm；匹配任务语义，不按案例ID |
| 归位支撑／松手 | 最近5步至少4步支撑且当前支撑，最近3步无机器人接触 |
| 明确稳定／撤离 | 原指令要求稳定时5步最大两两位置距离≤5mm；要求撤离时3步夹爪距离≥80mm且无接触 |
| 高处无支撑释放 | 接触→连续3步无接触，脱离前一步与首个无接触步均无支撑；脱离前参考点高于初始高度>30mm。归位完成前出现则失败，落地稳定不清除 |
| 抽屉关闭 | max(0,-q)≤10mm，连续5步。符号仅适用于本冻结木柜资产 |
| 重开诊断 | 已关闭后间隙>10mm连续3步，或>30mm一步；未明示保持关闭时不改变 Instruction SR |
| 明确保持物体 | 相对切换位置>25mm连续3步，或>50mm一步；不得重置参考点 |
| 明确保持关节 | 相对切换关节坐标>10mm连续3步，或>30mm一步；待确认越界期间不能判整任务成功 |
| 容器内保持 | 需要每步原生 containment 证据，不能用世界坐标不动或含关闭条件的复合goal代替 |
| 完成顺序 | 前置首次完成早于后续首次完成；不是“开始移动”的先后。首次目标太早不能靠再次达到自动洗掉 |
| Instruction SR | 目标与显式契约在同一策略步满足；不要求 SGS；成功后动作只作诊断 |

支持分别输出 `instruction_native` 与 `instruction_adjusted`，不要混淆原生目标和自定义扩展。没有明确保持条款时不加入计划文本追加的“保持关闭”“持续保持已归位物体”。Cheese目标不追加“向上支撑力达到重力70%”的旧门槛；指令/记录缺少的精确支撑力不伪造。

“位置合格”和“放置过程合格”分别形成证据。瞬时接触不等于抓稳；支撑布尔值不等于精确净支撑力。抓持掉落后回退控制是 `controller.py` 的提案，**尚未接入在线 Oracle**，不改变离线分数。

## 输入与缺失证据

- `trace.measurements` 使用既有 `step/phase/source/goal_frame`。只评价连续的 policy 步，拒绝跳步；原生目标必须为布尔值。
- `case` 来自冻结 `cases.jsonl`，`contract` 来自规范化原始指令契约。case ID 必须一致。
- 归位使用 source 物体测量，额外核对 `all_object_poses[restore_object]`，不能拿新目标的接触状态替代。
- 可选 `trace.metric_initial.articulation` 提供切换瞬间关节证据，允许前置关闭在第0步已满足。没有该证据时，首帧已关闭造成的顺序歧义输出 unknown，不把首帧冒充初态。
- 扩展区域需要 `measurement.metric_evidence.regions[site]`，含 `local_position/lower/upper/parent_contact_required/parent_contact`，数值由冻结仿真 site 几何产生。局部变换忠实于原生 `M @ (body_origin-site_center)`。
- 容器保持需要 `measurement.metric_evidence.containment[clause_id]` 布尔值。旧 trace 不具备时返回 unknown。
- 调整区域的原生成功点一定仍成功；原生失败不能直接推出扩展区域失败，没有几何证据应返回 unknown。

结果使用 `true/false/null` 对应通过／失败／无法判定。汇总同时报告 total/pass/fail/unknown；存在 unknown 时不输出伪精确 SR，而报告上下界，**不静默剔除未知案例改变分母**。

`components` 中的 `success` 表示该组件曾满足，`last_state` 表示策略末状态；持续约束是否影响任务以整任务首次合格时刻为准，不能只读取组件曾通过。高处释放检测只覆盖记录内的接触转变；切换至第一测量之间的掉落不能宣称已排除。

## 使用

从 `/mnt/disk_4/geyi/smolvla_eval` 执行：

```bash
python3 -m benchmark_metrics validate --contracts analysis/task_contract_v2_20261021/contracts.json
python3 -m unittest discover -s benchmark_metrics/tests -v
python3 -m benchmark_metrics.tests.regression_reviewed
```

离线任务清单 JSON 格式：

```json
[{"case_id":"CASE_ID","trace":"relative/or/absolute.trace.json.gz"}]
```

```bash
python3 -m benchmark_metrics evaluate \
  --contracts analysis/task_contract_v2_20261021/contracts.json \
  --cases modelscope_datasets/OutlierFaye/pi05-hard880-v1-local/small722/pi05_small722_20261016/work/pi05_small722_data_v1/mini/cases.jsonl \
  --manifest /path/to/jobs.json \
  --output /path/to/new_report.json
```

也可用既有评测目录的 `src/score.py` 作为入口，参数一致。默认禁止覆盖已有报告。输出包含规则配置、规则哈希、契约哈希、输入轨迹文件哈希、事件时刻、中文原因及诊断。修改实验阈值时复制配置并更改版本，使用顶层 `--rules path.json` 参数，不修改已发布候选文件。

## 验证范围与迁移

已审核的15例归位和5例区域争议作为组件回归样本；722条契约结构单独验证。数值候选仍有空白：30mm释放高度在20–50mm缺少标注；10mm关闭间隙缺少附近负例；容器保持、初态、扩展目标区域需要补采证据。**本轮不宣称已完成722例完整新版 Instruction SR，更不宣称已验证在线修复效果。**

旧 `analysis/metric_revision_v2_rc1`、`review_refinement_round2_20261021`、`metric_threshold_ab_20261021`、`restore_release_revision_20261021`、`review_refinement_round3_20261021` 中的脚本是历史校准快照，继续保留以复现原报告，但不再作为新评测入口。它们的35/70mm、10mm、30mm等最终候选逻辑在本包集中实现；旧5mm关闭等历史参数不能混入新配置。
