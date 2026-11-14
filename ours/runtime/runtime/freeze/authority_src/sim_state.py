"""Capture complete source contexts; restoring is permitted only before a trial."""
import hashlib
import numpy as np

OBJECTS = ('akita_black_bowl_1', 'cream_cheese_1', 'wine_bottle_1', 'plate_1')
FIXTURES = ('wooden_cabinet_1', 'flat_stove_1', 'wine_rack_1')
CONTROLLER = ('initial_joint', 'initial_ee_pos', 'initial_ee_ori_mat', 'goal_pos', 'goal_ori')
DATA_FIELDS = ('qacc_warmstart', 'ctrl', 'act', 'mocap_pos', 'mocap_quat', 'qfrc_applied', 'xfrc_applied')


def capture(env):
    result = dict(state=np.asarray(env.get_sim_state()).copy(),
                  body_pos=np.asarray(env.sim.model.body_pos).copy(),
                  body_quat=np.asarray(env.sim.model.body_quat).copy(),
                  gripper_current_action=np.asarray(env.env.robots[0].gripper.current_action).copy())
    for name in DATA_FIELDS: result['data_' + name] = np.asarray(getattr(env.sim.data, name)).copy()
    controller = env.env.robots[0].controller
    for name in CONTROLLER:
        if hasattr(controller, name): result['controller_' + name] = np.asarray(getattr(controller, name)).copy()
    result['env_time'] = np.array([env.env.cur_time, env.env.timestep], dtype=float)
    # robosuite's sensors sample within a control step. Their clocks are part
    # of the context: equal qpos/qvel alone does not imply equal RGB frames.
    for name, sensor in env.env._observables.items():
        result['sensor_clock_' + name] = np.array([sensor._time_since_last_sample,
                                                   sensor._current_delay, sensor._sampled])
        if not name.endswith('_image'):
            result['sensor_value_' + name] = np.asarray(sensor._current_observed_value).copy()
    for name, value in env.env._obs_cache.items():
        if not name.endswith('_image'):
            result['sensor_cache_' + name] = np.asarray(value).copy()
    return result


def restore(env, context):
    # Call only at the beginning of a new trial, never at interruption.
    env.sim.model.body_pos[:] = context['body_pos']
    env.sim.model.body_quat[:] = context['body_quat']
    obs = env.regenerate_obs_from_state(context['state'])
    for name in DATA_FIELDS: getattr(env.sim.data, name)[:] = context['data_' + name]
    controller = env.env.robots[0].controller
    controller.update(force=True)
    for name in CONTROLLER:
        if 'controller_' + name in context: setattr(controller, name, context['controller_' + name].copy())
    env.env.robots[0].gripper.current_action = context['gripper_current_action'].copy()
    env.env.cur_time = float(context['env_time'][0]); env.env.timestep = int(context['env_time'][1])
    env.env.done = False
    for name, sensor in env.env._observables.items():
        clock = context['sensor_clock_' + name]
        sensor._time_since_last_sample = float(clock[0])
        sensor._current_delay = float(clock[1]);sensor._sampled = bool(clock[2])
        if name.endswith('_image'):
            key = {'agentview_image':'main_raw_image', 'robot0_eye_in_hand_image':'wrist_raw_image'}[name]
            sensor._current_observed_value = context[key].copy()
        else:
            sensor._current_observed_value = context['sensor_value_' + name].copy()
    env.env._obs_cache = {k.removeprefix('sensor_cache_'):v.copy() for k,v in context.items()
                          if k.startswith('sensor_cache_')}
    for name, sensor in env.env._observables.items():
        if name.endswith('_image'):env.env._obs_cache[name] = sensor._current_observed_value.copy()
    return env.env._get_observations()


def identity(context):
    h = hashlib.sha256()
    for name in ('body_pos', 'body_quat', 'state'):
        value = context[name][1:] if name == 'state' else context[name]
        h.update(np.ascontiguousarray(np.round(value, 8)).tobytes())
    return h.hexdigest()


def layout(env):
    positions = {}
    for name in OBJECTS + FIXTURES:
        obj = env.env.objects_dict.get(name) or env.env.fixtures_dict[name]
        body = env.sim.model.body_name2id(obj.root_body)
        positions[name] = np.asarray(env.sim.data.body_xpos[body]).copy()
    descriptor = np.concatenate([positions[n][:2] for n in OBJECTS + FIXTURES])
    return descriptor, positions


def observation_state(obs):
    quat = np.asarray(obs['robot0_eef_quat'], dtype=float).copy()
    quat[3] = np.clip(quat[3], -1, 1)
    den = np.sqrt(1 - quat[3] ** 2)
    aa = np.zeros(3) if np.isclose(den, 0) else quat[:3] * 2 * np.arccos(quat[3]) / den
    return np.concatenate([obs['robot0_eef_pos'], aa, obs['robot0_gripper_qpos']]).astype(np.float32)
