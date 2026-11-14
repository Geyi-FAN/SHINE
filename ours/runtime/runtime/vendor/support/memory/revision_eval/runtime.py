from pathlib import Path
import numpy as np
from .tasks import TASKS
from .metrics import frame_measure
from .contact import ContactStateMonitor, ContactExitConfig
JOINTS={'middle':'wooden_cabinet_1_middle_level','top':'wooden_cabinet_1_top_level','stove':'flat_stove_1_button'}

def strict_config():
    return ContactExitConfig(unsupported_frames=1,
        allow_initial_incidental_gripper_contacts=False,
        maximum_start_speed=.10, maximum_height_change=.005,
        maximum_object_displacement=.010, maximum_orientation_change=.15,
        maximum_other_object_displacement=.005,
        maximum_other_object_orientation_change=.10)

class Runtime:
    def goals(self, env, task_id):
        from libero.libero import get_libero_path
        from libero.libero.envs.bddl_utils import robosuite_parse_problem
        if task_id not in self.goal_cache:
            t = self.suite.get_task(task_id)
            self.goal_cache[task_id] = robosuite_parse_problem(str(Path(get_libero_path('bddl_files')) / t.problem_folder / t.bddl_file))['goal_state']
        return all(env.env._eval_predicate(g) for g in self.goal_cache[task_id])

    def monitor(self, env, task):
        mon = ContactStateMonitor(env, TASKS[task][1] or 'akita_black_bowl_1', strict_config())
        base = mon.measure
        addresses = {k: int(mon.model.jnt_qposadr[env.sim.model.joint_name2id(v)]) for k, v in JOINTS.items()}
        def measure():
            m = base()
            pairs=[]
            for contact in mon.live.contact[:mon.live.ncon]:
                a=mon.object_geom_owner.get(int(contact.geom1));b=mon.object_geom_owner.get(int(contact.geom2))
                if a and b and a!=b and contact.dist<0:
                    pairs.append(dict(objects=sorted((a,b)),penetration=float(-contact.dist)))
            m['object_object_contacts']=pairs
            m['articulation'] = {k: float(mon.live.qpos[i]) for k, i in addresses.items()}
            m['goals'] = {str(i): bool(self.goals(env, i)) for i in range(10)}
            return m
        mon.measure = measure
        return mon

    def frame(self, mon, task):
        frame = frame_measure(self, mon, task)
        if task in (0, 7):
            m = mon.measure()
            token = 'wooden_cabinet' if task == 0 else 'flat_stove'
            contact = any(token in ' '.join(x['pair']) for x in m['robot_contact_details'])
            frame['no_robot_contact'] = not contact
            frame['stable'] = bool(frame['goal'] and not contact)
        return frame

def phase_candidates(trace, source):
    """Label teacher states after rollout; labels/future states never enter policy input."""
    result = {}
    streak = 0; interacted = False
    for t, row in enumerate(trace):
        if t < 5: continue
        m = row['before']; goal = m['goals'][str(source)]
        if source in (0, 5, 7):
            prefix = {0:'D', 5:'P', 7:'K'}[source]
            if goal: stage = 2
            elif source == 5:
                interacted = interacted or m['target_contact'] or np.linalg.norm(np.asarray(m['object_position'])-trace[0]['before']['object_position']) > .005
                stage = int(interacted)
            else:
                key = 'middle' if source == 0 else 'stove'
                interacted = interacted or abs(m['articulation'][key]-trace[0]['before']['articulation'][key]) > .002 or any(('wooden_cabinet' if source==0 else 'flat_stove') in ' '.join(x['pair']) for x in m['robot_contact_details'])
                stage = int(interacted)
            label = prefix+str(stage)
        else:
            # A goal container (cheese on bowl) is valid support even if the
            # source monitor's fixed-table support list excludes that object.
            released = not m['target_contact'] and m['object_speed']<=.012 and m['object_angular_speed']<=.20 and m['gripper_gap'] >= .065
            streak = streak + 1 if goal and released else 0
            if streak >= 5: stage = 4
            elif m['target_contact'] and not m['support_contact']:
                if not m['bilateral_finger_contact'] or m['object_speed']>.30:continue
                # A descent toward the native target after a stable lift labels placement.
                previous = trace[max(0, t-5)]['before']
                descended = m['object_position'][2] < previous['object_position'][2]-.008
                shifted = np.linalg.norm(np.asarray(m['object_position'])[:2]-trace[0]['before']['object_position'][:2]) > .075
                stage = 3 if descended and shifted else 2
            elif m['target_contact']:
                displaced = np.linalg.norm(np.asarray(m['object_position'])-trace[0]['before']['object_position']) > .05
                stage = 3 if displaced else 1
            elif not interacted and not goal and np.linalg.norm(np.asarray(m['object_position'])-trace[0]['before']['object_position']) < .005:
                stage = 0
            else: continue  # released-unsettled/recovery is explicitly not mislabelled M4.
            label = 'M'+str(stage)
            if source == 3:
                opened = m['articulation']['top'] < -.14
                initial = trace[0]['before']['articulation']['top']
                if stage == 0 and not opened: label = 'C1' if abs(m['articulation']['top']-initial)>.002 or m['robot_contact_details'] else 'C0'
                else: label = 'C'+str(stage+2)
            interacted = interacted or m['target_contact']
        result.setdefault(label, []).append(t)
    return result
