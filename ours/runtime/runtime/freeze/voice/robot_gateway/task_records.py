"""Observable task structure; never substitute a stage instruction for P1 input."""

from instructions import CATALOG

GOALS = {}
for entry in CATALOG["entries"]:
    if "normal" in entry["kinds"] and len(entry["target_tasks"]) == 1:
        GOALS[entry["target_tasks"][0]] = entry["instruction"]

LABELS = {
    "goal:0": "打开中间抽屉",
    "goal:1": "将碗放到炉子上",
    "goal:2": "将酒瓶放到柜顶",
    "goal:3": "打开上层抽屉并将碗放入",
    "goal:4": "将碗放到柜顶",
    "goal:5": "将盘子推到炉子前方",
    "goal:6": "将奶油奶酪放进碗",
    "goal:7": "打开炉子",
    "goal:8": "将碗放到盘子上",
    "goal:9": "将酒瓶放到酒架上",
    "close:middle": "关闭中间抽屉",
    "close:top": "关闭上层抽屉",
    "open:top": "打开上层抽屉",
    "restored:akita_black_bowl_1": "将碗归位到本轮开始时的位置并松手",
    "in_top": "保持碗在上层抽屉内",
    "outside_top": "将碗从上层抽屉取出",
}


def condition_label(condition):
    return LABELS.get(
        condition, "松手后保持物体稳定、有支撑" if condition.startswith("released:") else condition
    )


def build_task_record(
    task_id, episode, operation, instruction, requested, args, monitor, observed_at
):
    contract = monitor.contract
    stages = [
        {
            "index": i,
            "label": "；".join(condition_label(c) for c in stage),
            "conditions": stage,
            "status": "pending",
        }
        for i, stage in enumerate(contract["stages"])
    ]
    goal = next(
        (
            GOALS.get(int(c.split(":")[1]))
            for stage in contract["stages"]
            for c in stage
            if c.startswith("goal:")
        ),
        None,
    )
    return {
        "schema": "robot_task.v1",
        "task_id": task_id,
        "episode_id": episode,
        "operation": operation,
        "complete_instruction": instruction,
        "requested_instruction": requested,
        "user_utterance": str(args.get("user_utterance", ""))[:1000],
        "clarification_evidence": args.get('_clarification_evidence'),
        "goal": goal or instruction,
        "preconditions": [s["label"] for s in stages[:-1]],
        "persistent_constraints": [condition_label(c) for c in contract["persistent"]],
        "constraint_scope": "configured_template_checks" if stages else "unparsed_full_instruction",
        "reference_memory_ids": list(
            dict.fromkeys(
                args.get("memory_ids", []) + ([args["memory_id"]] if args.get("memory_id") else [])
            )
        ),
        "source": args.get("source", "operator_text"),
        "request_id": args.get("_request_id"),
        "voice_input_id": args.get("voice_input_id"),
        "observation_time": observed_at,
        "structure_source": "training_template_contract"
        if stages
        else "full_instruction_preserved",
        "completion_basis": "libero_supervisor" if stages else contract["mode"],
        "stages": stages,
        "evidence_note": "阶段检查不生成动作；未覆盖的约束仍保留在完整指令中。",
    }


def task_view(record, monitor, mode, completion, version, reason, evidence):
    import copy

    result = copy.deepcopy(record)
    result.update(state=mode, completion=completion, task_version=version, hold_reason=reason)
    for stage in result["stages"]:
        i = stage["index"]
        if completion == "verified" or i < monitor.stage:
            status = "verified"
        elif completion == "user_confirmed":
            status = "user_confirmed"  # Explicitly NOT observed verification.
        elif i == monitor.stage:
            status = {
                "running": "active",
                "verifying": "verifying",
                "needs_review": "needs_review",
                "cancelled": "cancelled",
                "error": "needs_review",
            }.get(mode, "paused")
        else:
            status = "pending"
        stage["status"] = status
        stage["current_conditions"] = {c: evidence.get(c) for c in stage["conditions"]}
    result["current_persistent_conditions"] = {
        c: evidence.get(c) for c in monitor.contract["persistent"]
    }
    return result
