# Episode初始化 → 指令切换：物体记忆传递

更新：2026-10-26。用于当前“Agent规划＋Oracle阶段/状态判断＋YOLO点”的混合实验。π0.5权重、动作预算、成功标准和prompt格式不变。

## 这次解决什么

上轮奶酪和酒瓶案例并非从未识别到物体：初始帧分别有置信度0.9834、0.9863的K1，切换时物体几乎未移动。然而原代码只让固定设施点进入场景缓存；物体K1/K3留在episode_start历史字典中，current查询取不到。切换快照又没有5帧静止历史，所以冷启动阶段无法补建缓存。

这次让历史图像预测与“当前仍然可用的位置”接通。历史点不是GT像素，也不是把K2改名成K1。

## 三层记忆

| 层 | 内容 | 生命周期 |
|---|---|---|
| Episode历史 | 初始YOLO K1/K2/K3、采集帧、相机与私有有效性证据 | 仅新episode清空；初始归位K2不随任务变化 |
| 当前有效场景缓存 | 通过校验的历史/当前K1、K3；固定设施锚点 | 遮挡继续保留，移动/抓持/支撑丢失/相机变化使其失效 |
| 本次指令记忆 | instruction_takeover K2、指令版本 | 新用户指令接管时更新，不清空episode历史和场景缓存 |

当前数据每类可移动物体只有一个已知实例，因此实体名在同一episode内代表该实例；不能把这个假设直接推广到多只同类碗的场景。

## 初始化历史点进入current缓存的条件

仅尝试导入物体K1/K3，不导入抽屉把手，不使用不同K槽替代。

1. 同一episode、相同MAIN相机与图像变换。
2. 采集时刻不晚于当前时刻，坐标有限且在MAIN224范围内。
3. 检测与关键点置信度均>=0.5。
4. 初始与当前均有支撑、没有双指抓持。
5. 当前与初始物体位姿相容：平移<=5mm、旋转<=5°。这些是缓存有效性阈值，不是任务评分阈值。

这里校验的是“历史点现在是否仍适用”，不能仅凭物体类别静态就直接导入。初始化直接导入不伪造5帧观察：它依赖独立的初始/当前状态一致性证据。后续新缓存建立仍沿用5帧静止窗口。

导入后标记`cache_kind=episode_object`、`source_time_source=episode_start`。相同历史条目只尝试一次；失效后不能每次失检都重新灌入这个旧点。必须重新观测来建立新的静止阶段。

## 当前检测与缓存如何选择

- 正常当前检测按原双0.1门槛使用。
- 存在有效缓存时，超过10像素的跳变先拒绝，需另一帧在3像素范围内确认；这个保护也覆盖切换最初不足5帧的阶段。
- 当前失检/跳变尚未确认：返回有效缓存。
- 当前与历史均不可靠：明确缺失，不填(0,0)，不投影GT像素补点。

K1是可见参考，遮挡可能使“当前可见质心”偏移，因此历史K1与当前K1不必逐像素相同；实际抓取效果仍需闭环验证。高置信度也不保证定位一定正确。

## 实际连续episode中的调用方式

整个episode保留同一个Points/SceneMemory实例。不要因为新指令、子目标变化而重新创建它。

```python
points = Points(folder, episode_id=episode_id)
points.initialize_episode(initial_main_image, initial_facts, camera_id)

# 原任务执行期间也持续更新；不等到用户打断时才建立scene memory。
points.update_evidence(episode_frame, facts, camera_id)
points.observe(main_image, episode_frame)

# 新指令接管：只更新接管记忆和指令版本，不重建Points对象。
points.begin_instruction(main_image, episode_frame)
# 后续照常更新证据/当前图像，再让Agent规划并绑定prompt。
```

`begin_instruction()`不清空episode_start、场景缓存、固定设施锚点。调用方给Agent传入对应的instruction_version，并使用单调递增的episode时间。新episode创建新实例，避免跨episode串点。

本次已经接入当前hybrid_planner评测runner。VoiceHarness业务主循环还需在其实际切换入口复用此对象、调用同一接口；没有将主循环整套替换成新的规划器。

## 从冻结切换快照评测时如何补历史

快照评测从episode中途开始，没有完整实时运行过的记忆对象。新增`episode_history.py`适配器：

1. 独立、可丢弃的仿真环境恢复该episode真实初始状态；新增轨迹使用原HDF5 states[0]及原场景元数据。
2. 重渲染初始图像，验证与原初始图像一致（RGB平均绝对误差<=3）。
3. 仅提取初始相机与物体状态的私有有效性证据。
4. 当前已有初始图像照常送YOLO，预测点通过上述校验后进入current缓存。

该适配器不修改当前执行环境，不重置切换状态，不读取未来帧，不把仿真位姿投影为补点坐标。初始状态/图像无法验证时记录unavailable，不静默沿用错误记忆。

这是快照评测补历史的方式，不是让真实机器人每次切换时重新仿真。仍使用Oracle状态有效性证据，因此不应称为完全非Oracle；真机阶段需要以视觉跟踪、本体状态和接触判断替换facts接口。

## 日志与时间

日志记录history_import/history_reject、instruction_switch、cached/fresh、来源帧、置信度、失效原因。

初始图像在旧控制时钟中用frame=-1表示，但其真实source_episode_frame=0。已知fixed_switch_step时，日志用episode全局时间计算age_steps，并记录age_clock=episode；不能把切换后3步的初始记忆伪装为只有4步年龄。不知道全局偏移时明确标记控制时钟，不编造时间。

私有初始状态证据保存于每例episode_initial_validity_evidence.json，仅用于有效性核查，不进入Agent输入或π0.5 prompt。

可用`HYBRID_EPISODE_OBJECT_MEMORY=0`关闭本次新增的物体历史导入；固定设施及既有缓存仍独立工作。

## 验证与评测边界

- 72项单元测试通过，包括跨episode/相机、已移动物体、低置信度、未来帧、失效后重复导入、指令切换保留、全局时间。
- 两条旧失败轨迹在原0/3步暂停处成功取得初始K1。
- 另两条已持有/搬动物体的NEW_E/NEW_F轨迹拒绝其旧K1，验证没有乱补点。
- 四条验证中，独立补历史前后当前执行环境状态完全一致；初始重渲染平均误差约0.186–0.187。
- 闭环回归两案例×M1/M2共4次，无缺点暂停。奶酪M1/M2均135步完整成功，酒瓶M1为583步完整成功，M2为抓取未完成、1200步超时。完整成功3/4；不能回填之前Static24成绩。修复缺点不保证策略动作必然成功，也不代表全量静态位置100%可用。

实现：scene_memory.py、points.py、episode_history.py、run.py。
验证与闭环目录：`/mnt/disk_4/geyi/scene_memory_episode_transfer_20261026/`。
