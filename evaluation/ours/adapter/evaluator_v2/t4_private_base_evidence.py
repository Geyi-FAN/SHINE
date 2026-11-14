"""Private benchmark evidence, equivalent original T4 v4 source predicates."""
import copy
import json
import time
from collections import deque

BODY = {'bowl': 'akita_black_bowl_1', 'wine_bottle': 'wine_bottle_1', 'cheese': 'cream_cheese_1'}
SOURCE = {1: 'bowl', 2: 'wine_bottle', 3: 'bowl', 4: 'bowl', 5: 'plate', 6: 'cheese', 8: 'bowl', 9: 'wine_bottle'}
GOALS = ['open_middle', 'bowl_stove', 'bottle_cabinet', 'bowl_drawer', 'bowl_cabinet', 'push_plate',
         'cheese_bowl', 'turn_on_stove', 'bowl_plate', 'bottle_rack']
GOAL_OBJECTS = [None, 'bowl', 'wine_bottle', 'bowl', 'bowl', 'plate', 'cheese', None, 'bowl', 'wine_bottle']


def source_ready(ticks, spec, retained=False):
    phase = spec.get('phase')
    if phase not in ('M2', 'M4'):
        return False
    count = 5 if phase == 'M2' else 10
    if len(ticks) < count:
        return False
    window = list(ticks)[-count:]
    entity = SOURCE[spec['source_task']]
    for t in window:
        item = t['physical']['objects'].get(entity)
        measurement = t['measurements'].get(entity)
        if not item or not measurement:
            return False
        if phase == 'M2':
            ref = t['episode_initial_positions'][BODY[entity]]
            if not (t['physical']['held_object'] == entity and not item['supported']
                    and item['bilateral_contact'] and measurement['object_position'][2] - ref[2] >= (.02 if retained else .03)):
                return False
        else:
            q = t['proprioception']['robot0_gripper_qpos']
            if not (t['physical']['native_goal_relations'].get(GOALS[spec['source_task']]) is True
                    and t['physical']['held_object'] == 'none' and item['supported']
                    and not item['bilateral_contact'] and abs(q[0] - q[1]) >= .04):
                return False
    if phase == 'M4':
        points = [t['measurements'][entity]['object_position'] for t in window]
        if not all(sum((a-b)**2 for a, b in zip(p, q)) <= .002**2 for p in points for q in points):
            return False
    return True


def intrinsic_target_ready(bridge):
    """Final-only private release/stability guard, same T4 physical rules.

    It returns no intermediate event/pose/plan to a language model.
    """
    from benchmark_metrics.events import restore_window
    obj = GOAL_OBJECTS[bridge.case['target_task']]
    if obj is None:
        return True
    frames = list(bridge.cache_reader.windows[obj])
    if not frames:
        return False
    clause = dict(reference_position=frames[-1]['object_position'], stable_required=True, withdraw_required=False)
    return bool(restore_window(frames, clause, 1e6, bridge.rules)['complete'])


class TickRecorder:
    def __init__(self, bridge, xyz, spec):
        self.bridge, self.xyz, self.spec = bridge, xyz, spec
        self.recent = deque(maxlen=12)
        self.policy_goal_seen = {}
        self.path = bridge.root / 'recordings' / bridge.state.episode / 'control_ticks.jsonl'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a', buffering=1)

    def record(self, phase, stepped=True):
        b = self.bridge
        measurements = {}
        keys = ('object_position', 'eef_position', 'support_contact', 'target_contact', 'finger_contact',
                'bilateral_finger_contact', 'object_speed', 'gripper_gap', 'articulation', 'geometric_support_contact', 'container_support_evidence')
        for name, window in b.cache_reader.windows.items():
            if window:
                measurements[name] = {key: copy.deepcopy(window[-1][key]) for key in keys if key in window[-1]}
        row = dict(time=time.time(), monotonic=time.monotonic(), step=b.physics_steps,
                   simulation_time=float(b.env.sim.data.time), control_step=b.control_steps,
                   episode_id=b.state.episode, task_id=b.state.task_id, version=b.state.version,
                   mode=b.state.mode, phase=phase,
                   policy_action=stepped and phase in ('authorized_kernel_control', 'authorized_native_control', 'source_policy'),
                   physical=copy.deepcopy(b.cache_reader.snapshot), measurements=measurements,
                   episode_initial_positions=self.xyz,
                   proprioception=dict(robot0_gripper_qpos=b.obs['robot0_gripper_qpos'].tolist()))
        self.recent.append(row)
        if row['policy_action'] and row['physical']['native_goal_relations'].get(GOALS[b.case['target_task']]) is True:
            self.policy_goal_seen[b.state.task_id] = True
        self.stream.write(json.dumps(row, separators=(',', ':')) + '\n')
