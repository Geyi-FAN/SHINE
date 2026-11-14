# 独立运行和复核

代码根目录：`/mnt/disk_4/geyi/audio_switch_benchmark/runtimes/c3r_pi05_744_30k_20261108`。

以下命令仅为启动方法，本轮没有执行这些启动命令。GPU、端口必须先确认空闲并为本轮独占。不要复用8787/8801、其他分支的私有目录或语音账户。

1. 验证冻结与模型身份（不会加载模型）：

```bash
cd /mnt/disk_4/geyi/audio_switch_benchmark/runtimes/c3r_pi05_744_30k_20261108
./scripts/check.sh
```

2. 在自己的 tmux 会话启动 π0.5。下面GPU/端口为示例，输出目录必须尚不存在。不要在GPU被占用时直接照抄。

```bash
./scripts/start_policy.sh --gpu 0 --port 49320 --out "$PWD/runs/preflight01_policy"
```

服务完成模型加载及独立预热后才提供 `/metadata`。它使用本地复制的 openpi 源码及明确 checkpoint，参数形状、归一化、prompt长度都会检查。模型加载有真实显存开销。

3. 在另一终端启动单所有者的仿真服务。SPEC是批准场景的fixture描述，包含源HDF、BDDL、参考图及各自SHA、case_id和预算；与对应分支适配器一起生成，不能用其他场景替代。令牌文件放服务器私有目录。

```bash
export HARNESS_ROBOT_TOKEN_FILE=/绝对路径/私有/robot.token
# 若不用 roles.json 中现存的私有凭据文件，可覆盖：
export HARNESS_AGENT_ENV_FILE=/绝对路径/私有/local_agent.env
./scripts/start_robot.sh --gpu 1 --port 49321 --child-port 59321 \
  --policy-port 49320 --spec /绝对路径/fixture_spec.json \
  --out "$PWD/runs/preflight01_robot"
```

本地Agent服务需预先就绪；本启动器不替用户重启共享推理池。`config/roles.json` 固定模型/端口，`HARNESS_AGENT_ENV_FILE` 仅覆盖凭据位置，不能偷换模型。只有操作者明确 reset 才新建episode；语音重连、问答、任务切换不清空episode memory。

4. 网关ready后启动独立音频daemon。私有配置可参考已有语音配置结构，须包含自己的有效 realtimeApiKey 或通过环境注入；从不把凭据提交到仓库。输出中的 private/config.json 权限600。

```bash
./scripts/start_voice.sh --port 49322 --robot-port 49321 \
  --private-config /绝对路径/私有/voice.json \
  --out "$PWD/runs/preflight01_voice"
```

音频评测客户端直接连接新的语音daemon，以正常速度回放已冻结WAV，不需要绕行8787网页。客户端必须记录识别文本、原始音频SHA、事件时刻、工具回执、task_id/task_version、实际动作和独立评分；不能把工具accepted等同物理成功。

离线回归可执行：

```bash
/mnt/disk_2/geyi/pi0.5_test_1001/evaluation_portable/.venv/bin/python tools/run_checks.py
```

这只重写被Git忽略的 reports 日志，不改冻结代码；不调用云端或真实模型。冻结时的结果另存于 `validation/`，不被重跑覆盖。日志中出现robosuite旧版提示不等于测试失败，以结构化JSON和退出码为准。

## 恢复与版本追踪

`FREEZE.json` 记录本地commit和标签，`provenance/FROZEN_FILES.json`逐文件记录SHA。`tools/verify_freeze.py`同时检查SHA、Git HEAD、未提交修改和未跟踪源码。运行产物与凭据在忽略目录，不作为源码变动。

本轮没有修改主服务启动入口；回退不需要恢复主8787。若预检需要修复，保留本目录，创建新版本/工作树，记录新commit、修改原因及同条件回归，不在本目录执行覆盖式重新构建。

模型和数据保留原处，模型参数不复制进Git。Python/Node环境未修改；依赖快照见 `provenance/ENVIRONMENTS.json`，外部导入边界见 `validation/IMPORT_BOUNDARY.json`。跨服务器部署需要转移这些外部资源并新建机器路径配置，此站点冻结配置不能盲目跨机器复用。
