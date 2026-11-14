# 候选修复运行说明

本目录是隔离开发候选，主8787尚未切换。当前云端1007 Access denied，未完成新音频回归。勿把本地文字/音频时钟测试当成音频SR。

固定执行器：SmolVLA E3 v4 raw30000；原YOLO和M1；原v2.5数值阈值。语音Omni仍为云端，四个执行角色为本地Qwen3.8-27B-FP8。不要启动旧Max/Codex动作出口，不改119份原冻结包或停止共享模型。

## 先验证

```bash
cd /mnt/disk_2/geyi/voice_f28d_audio_repair_20261102
PY=/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python
$PY -m unittest repair.test_repairs -v
$PY -m unittest discover -s freeze/voice/tests -p 'test_clarification*.py' -v
```

`repair/audio-client.mjs`通过独立工作线程维持20ms输入时钟，JSON/状态编排在父线程。收端`audio_received.jsonl`记录帧哈希和单调时间。`audit_audio.mjs CASE_DIR`核对全部原PCM帧、时长比0.95–1.05和最大帧间隔<100ms；门槛开跑前声明，不事后剔除案例。

`completion.py`只负责当前授权任务终验与收尾，不生成计划或提供位置。F28d Agent仍生成计划/subgoal，YOLO/M1绑定引用，唯一物理线程执行；明确暂停不调用env.step。

`wording_guard.py`要求Agent保持完整用户目标，不把可能错误/过期的“碗在桌上”等观察塞进Task。当前点仍由YOLO/M1提供。`telemetry.py`使同一个发布快照同时绑定任务编号、模式、物理步和计数，防止把上一个任务完成记给下一个任务。

## 云端恢复后

仅在账户恢复后启动。沿用现有共享18084/19867服务；私有端口19281/19287/19289，默认单语音会话、30秒例间冷却。端口占用会拒绝启动，不杀其他分支。任一1007或输入时序不合格会停止整轮并保留证据。

```bash
cd /mnt/disk_2/geyi/voice_f28d_audio_repair_20261102
# 先smoke，阅读逐例证据，修复/重新冻结后再正式24。
tmux new-session -d -s audio_repair_smoke 'bash repair/launch.sh smoke > /mnt/disk_4/geyi/voice_audio_unified_repair_20261102/smoke.console.log 2>&1'
# smoke通过并核对后：
tmux new-session -d -s audio_repair_24 'bash repair/launch.sh formal24 > /mnt/disk_4/geyi/voice_audio_unified_repair_20261102/formal24.console.log 2>&1'
# 同24问题解决后扩到已有96，不能把不同轮/条件拼接。
tmux new-session -d -s audio_repair_96 'bash repair/launch.sh expanded96 > /mnt/disk_4/geyi/voice_audio_unified_repair_20261102/expanded96.console.log 2>&1'
```

三个命令顺序执行，勿并行。启动脚本不自动安排之后两轮，更不会直接切换生产服务。每轮自动新建带时间的结果目录并冻结代码/协议/资产引用；不覆盖已有失败。工程诊断历史和正式冻结结果分开。

96例前置通过未评分的公开文字工具授权同模型执行，不注入物体位置。所有评分交互使用49段原审核音频。它与24例语音源任务前置不同，不能直接把总分变化归因于修复。

## 证据入口

- `/mnt/disk_4/geyi/voice_audio_unified_repair_20261102/reports/REPORT.md`
- 同目录`CURRENT_PROGRESS.json`，运行`$PY repair/report.py`更新开发进度。
- `PACING_ALL49.json`：49音频独立收发压力测试。
- `text_integration_r1/`：基础、澄清、归位通过；waiting后续物理预算耗尽。
- `text_integration_r2/waiting/VALIDITY.json`：监控拼接错误，原提前通过记录已作废，不算成功。
- `text_integration_r3/`：修复监控后重测waiting，最终以TEXT_RESULT及视频为准。
- `text_priority_r3/RESULT.json`：真实硬暂停、真实恢复和重复恢复保护；时延为公开工具调用，不是音频末端时延。

未解决的正式证据：云端ASR、意图选工具、TTS播报、QA语义/时延、waiting语音登记/取消/替换、真实音频24/96及上线后reset/重连回归。恢复账户之后继续同一授权任务，不需要重新批准训练；本轮无训练。
