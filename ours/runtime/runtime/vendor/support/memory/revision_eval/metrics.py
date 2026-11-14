import json
from pathlib import Path
import numpy as np
PUSH_TASKS={5}
POSE_RULES=json.loads(Path(__file__).with_name("pose_rules.json").read_text())["rules"]

def supported(mon, m, task):
    """Cheese can rest against inclined bowl walls, not just horizontal surfaces."""
    if task != 6:
        return bool(m['support_contact'])
    upward, contacts = 0., 0
    for i, co in enumerate(mon.live.contact[:mon.live.ncon]):
        a, b = int(co.geom1), int(co.geom2)
        if a not in mon.target_geoms and b not in mon.target_geoms:
            continue
        other = a if b in mon.target_geoms else b
        if mon.object_geom_owner.get(other) != 'akita_black_bowl_1' or co.efc_address < 0:
            continue
        force = np.zeros(6)
        mon.mj.mj_contactForce(mon.model, mon.live, i, force)
        world = co.frame.reshape(3, 3).T @ force[:3]
        upward += float(world[2])*(1 if b in mon.target_geoms else -1)
        contacts += 1
    weight = float(mon.model.body_mass[mon.target_body]*abs(mon.model.opt.gravity[2]))
    return bool(contacts and upward >= .7*weight)

def pose_measure(mon, task_id):
    rule = POSE_RULES.get(str(task_id))
    if rule is None:
        return {"valid": True, "angle_deg": None, "limit_deg": None}
    axis = mon.live.xmat[mon.target_body].reshape(3, 3)[:, 2]
    reference = np.asarray(rule["reference_axis"], dtype=float)
    reference /= np.linalg.norm(reference)
    angle = float(np.degrees(np.arccos(np.clip(np.dot(axis, reference), -1., 1.))))
    return {"valid": angle <= rule["max_angle_deg"], "angle_deg": angle,
            "limit_deg": float(rule["max_angle_deg"])}

def frame_measure(rt, mon, task_id):
    goal = bool(rt.goals(mon.env, task_id)) if mon is not None else None
    if task_id in (0, 7):
        return {"goal": goal, "stable": goal, "released": True, "supported": True,
                "no_robot_contact": True, "gripper_open": True,
                "linear_speed": None, "angular_speed": None,
                "pose": {"valid": True, "angle_deg": None, "limit_deg": None}}
    m = mon.measure()
    pose = pose_measure(mon, task_id)
    no_contact = not m["target_contact"]
    support = supported(mon, m, task_id)
    gripper = True if task_id in PUSH_TASKS else m["gripper_gap"] >= .065
    low_speed = (m["object_speed"] <= .012 and m["object_angular_speed"] <= .20)
    stable = bool(goal and no_contact and support and gripper and low_speed and pose["valid"])
    return {"goal": goal, "stable": stable, "released": no_contact,
            "supported": bool(support), "no_robot_contact": no_contact,
            "gripper_open": bool(gripper), "linear_speed": float(m["object_speed"]),
            "angular_speed": float(m["object_angular_speed"]), "pose": pose}

def hold_frame_ok(frame, task_id):
    if task_id in (0, 7):
        return bool(frame["goal"])
    return bool(frame["goal"] and frame["no_robot_contact"] and frame["supported"]
                and frame["gripper_open"] and frame["pose"]["valid"])
