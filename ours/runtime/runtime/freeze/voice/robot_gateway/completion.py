"""External LIBERO stop supervisor. Scene truth never enters P1 observations.

The policy always receives the complete instruction. This module only stops or
holds execution; it never generates task actions or moves objects to a target.
"""

import re
from instructions import BY_KEY, key

OBJECTS = {
    1: "akita_black_bowl_1",
    2: "wine_bottle_1",
    3: "akita_black_bowl_1",
    4: "akita_black_bowl_1",
    5: "plate_1",
    6: "cream_cheese_1",
    8: "akita_black_bowl_1",
    9: "wine_bottle_1",
}


def contract_for(instruction):
    text = key(instruction)
    entry = BY_KEY.get(text)
    if text == "that is done. leave the result as it is":
        return {"mode": "user_stop", "stages": [], "persistent": []}
    if not entry or len(entry["target_tasks"]) != 1:
        # Explicit single close commands are useful even though not a training template.
        close = re.fullmatch(r"close the (middle|top) drawer(?: of the cabinet)?", text)
        if close:
            return {"mode": "verified", "stages": [[f"close:{close[1]}"]], "persistent": []}
        return {"mode": "manual", "stages": [], "persistent": []}
    target = entry["target_tasks"][0]
    stages = []
    persistent = []
    if text.startswith("return the bowl to its starting position"):
        stages.append(["restored:akita_black_bowl_1"])
    if text.startswith("leave the bowl inside the top drawer"):
        persistent.append("in_top")
    close = re.search(r"close the (middle|top) drawer", text)
    if close:
        condition = f"close:{close[1]}"
        stages.append([condition])
        persistent.append(condition)
    if text.startswith("take the bowl out of the top drawer"):
        stages.append(["outside_top"])
    if target == 3:
        stages.append(["open:top"])
    final = [f"goal:{target}"]
    if target in OBJECTS:
        final.append("released:" + OBJECTS[target])
    stages.append(final)
    return {"mode": "verified", "stages": stages, "persistent": persistent}


class CompletionMonitor:
    """Ordered predicates and stable final-goal debounce; pure, testable logic."""

    def __init__(self, instruction, stable_frames=10):
        self.contract = contract_for(instruction)
        self.stage = 0
        self.stage_streak = 0
        self.final_streak = 0
        self.stable_frames = stable_frames
        self.initial = None
        self.previous = None
        self.order_error = False

    def conditions(self):
        return set(self.contract["persistent"]).union(*map(set, self.contract["stages"]))

    def update(self, evidence):
        mode = self.contract["mode"]
        if mode != "verified":
            return mode
        stages = self.contract["stages"]
        values = [all(evidence.get(c, False) for c in stage) for stage in stages]
        if self.initial is None:
            self.initial = values.copy()
            self.previous = values.copy()
        # A later newly achieved stage cannot stand in for an earlier cleanup.
        for i in range(self.stage + 1, len(stages)):
            if (
                values[i]
                and not self.previous[i]
                and not self.initial[i]
                and not values[self.stage]
            ):
                self.order_error = True
        self.previous = values.copy()
        if self.order_error:
            return "order_violation"
        if self.stage < len(stages) - 1:
            self.stage_streak = self.stage_streak + 1 if values[self.stage] else 0
            if self.stage_streak >= 3:
                self.stage += 1
                self.stage_streak = 0
            return "progress"
        final = values[-1] and all(evidence.get(c, False) for c in self.contract["persistent"])
        self.final_streak = self.final_streak + 1 if final else 0
        if self.final_streak >= self.stable_frames:
            return "complete"
        return "candidate" if final else "progress"


class LiberoEvidence:
    """Read-only official predicates, contact/release and episode-start references."""

    def __init__(self, env, suite):
        from pathlib import Path
        import numpy as np
        from libero.libero import get_libero_path
        from libero.libero.envs.bddl_utils import robosuite_parse_problem
        from revision_eval.contact import ContactStateMonitor

        self.env = env
        self.np = np
        self.goals = {}
        for i in range(10):
            t = suite.get_task(i)
            self.goals[i] = robosuite_parse_problem(
                str(Path(get_libero_path("bddl_files")) / t.problem_folder / t.bddl_file)
            )["goal_state"]
        self.monitors = {name: ContactStateMonitor(env, name) for name in set(OBJECTS.values())}
        self.initial = {
            name: env.env.object_states_dict[name].get_geom_state()["pos"].copy()
            for name in self.monitors
        }
        self.initial_quat = {
            name: env.env.object_states_dict[name].get_geom_state()["quat"].copy()
            for name in self.monitors
        }

    def sample(self, conditions):
        env = self.env
        np = self.np
        measurements = {}
        result = {}

        def measured(name):
            if name not in measurements:
                measurements[name] = self.monitors[name].measure()
            return measurements[name]

        def released(name):
            m = measured(name)
            return (
                not m["target_contact"]
                and m["support_contact"]
                and m["object_speed"] < 0.03
                and m["object_angular_speed"] < 0.3
            )

        for condition in conditions:
            kind, _, value = condition.partition(":")
            if kind == "goal":
                result[condition] = all(env.env._eval_predicate(g) for g in self.goals[int(value)])
            elif kind in ("close", "open"):
                result[condition] = env.env._eval_predicate(
                    [kind, f"wooden_cabinet_1_{value}_region"]
                )
            elif kind == "released":
                result[condition] = released(value)
            elif kind == "restored":
                obj = env.env.object_states_dict[value].get_geom_state()
                angle = 2 * np.arccos(
                    np.clip(abs(np.dot(obj["quat"], self.initial_quat[value])), 0, 1)
                )
                result[condition] = (
                    released(value)
                    and np.linalg.norm(obj["pos"] - self.initial[value]) < 0.035
                    and angle < 0.35
                )
            elif condition in ("in_top", "outside_top"):
                inside = bool(
                    env.env._eval_predicate(
                        ["in", "akita_black_bowl_1", "wooden_cabinet_1_top_region"]
                    )
                )
                result[condition] = inside if condition == "in_top" else not inside
            else:
                raise ValueError("Unsupported completion condition: " + condition)
        return {k: bool(v) for k, v in result.items()}
