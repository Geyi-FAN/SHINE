from dataclasses import dataclass
import numpy as np
from scipy.spatial.transform import Rotation

@dataclass
class ContactExitConfig:
    contact_distance: float = 0.001
    support_normal_z: float = 0.65
    minimum_support_force: float = 0.001
    maximum_start_speed: float = 0.15
    maximum_height_change: float = 0.012
    maximum_object_displacement: float = 0.035
    maximum_orientation_change: float = 0.45
    stable_linear_speed: float = 0.012
    stable_angular_speed: float = 0.20
    stable_frames: int = 5
    unsupported_frames: int = 2
    open_gripper_gap: float = 0.065
    retreat_distance: float = 0.08
    minimum_retreat_distance: float = 0.045
    minimum_clearance_gain: float = 0.035
    position_tolerance: float = 0.008
    orientation_tolerance: float = 0.10
    maximum_translation_per_step: float = 0.012
    maximum_rotation_per_step: float = 0.08
    release_steps: int = 40
    retreat_when_unilateral: bool = True
    minimum_opening_progress: float = 0.002
    release_retreat_translation_per_step: float = 0.004
    allow_initial_incidental_gripper_contacts: bool = True
    maximum_penetration_increase: float = 0.002
    maximum_other_object_displacement: float = 0.015
    maximum_other_object_orientation_change: float = 0.20

    def __post_init__(self):
        if self.stable_frames < 1 or self.unsupported_frames < 1:
            raise ValueError('Frame thresholds must be positive')
        if self.retreat_distance <= 0 or self.maximum_translation_per_step <= 0:
            raise ValueError('Motion distances must be positive')

class ContactStateMonitor:
    """Read contacts, support and velocity from the real current simulation.

    Construct after initial settling and before the source trajectory starts.
    The reference object pose is used to reject lifted/displaced starting
    states. A bilateral finger contact is only a grasp *candidate*, not proof
    of a stable grasp. Support requires an actual loaded contact below the
    object's inertial center with a sufficiently vertical contact normal. The
    body frame origin is not necessarily its center (LIBERO's bowl uses a frame
    near its bottom); support must not be measured against that frame origin.
    """

    def __init__(self, env, target_name='cream_cheese_1', config=None):
        import mujoco

        self.mj = mujoco
        self.env = env
        self.config = config or ContactExitConfig()
        if len(env.robots) != 1:
            raise ValueError('Contact exit requires one robot')
        self.robot = env.robots[0]
        self.model = env.sim.model._model
        self.live = env.sim.data._data
        self.target_name = target_name
        self.target = env.env.objects_dict[target_name]
        self.target_body = env.sim.model.body_name2id(self.target.root_body)
        self.target_geoms = self._geom_ids(self.target.contact_geoms)
        self.object_bodies = {name: env.sim.model.body_name2id(obj.root_body)
                              for name, obj in env.env.objects_dict.items()}
        self.object_geom_owner = {geom: name for name, obj in env.env.objects_dict.items()
                                  for geom in self._geom_ids(obj.contact_geoms)}
        self.gripper_geoms = self._geom_ids(self.robot.gripper.contact_geoms)
        self.robot_geoms = self._geom_ids(
            self.robot.robot_model.contact_geoms + self.robot.gripper.contact_geoms)
        important = self.robot.gripper.important_geoms
        self.left_geoms = self._geom_ids(important['left_fingerpad'])
        self.right_geoms = self._geom_ids(important['right_fingerpad'])
        self.left_finger_geoms = self._geom_ids(important['left_finger'])
        self.right_finger_geoms = self._geom_ids(important['right_finger'])
        self.finger_geoms = self.left_finger_geoms | self.right_finger_geoms
        self.qidx = np.asarray(self.robot._ref_joint_pos_indexes)
        self.gidx = np.asarray(self.robot._ref_gripper_joint_pos_indexes)
        self.site = self.robot.eef_site_id
        self.reference_position = self.live.xpos[self.target_body].copy()
        self.reference_rotation = self.live.xmat[self.target_body].reshape(3, 3).copy()
        self._last_time = None
        self._support_streak = 0
        self._stable_streak = 0

    def _geom_ids(self, names):
        return {self.env.sim.model.geom_name2id(n) for n in names}

    def _geom_name(self, geom_id):
        return self.env.sim.model.geom_id2name(int(geom_id)) or f'geom_{geom_id}'

    def measure(self):
        cfg, data = self.config, self.live
        pos = data.xpos[self.target_body].copy()
        center_of_mass = data.xipos[self.target_body].copy()
        mat = data.xmat[self.target_body].reshape(3, 3).copy()
        velocity = np.zeros(6)
        # mj_objectVelocity returns angular then linear velocity in world axes.
        self.mj.mj_objectVelocity(self.model, data, self.mj.mjtObj.mjOBJ_BODY,
                                 self.target_body, velocity, 0)
        target_hits, supports, unexpected, incidental, robot_details = [], [], [], [], []
        left, right, left_pad, right_pad, finger = False, False, False, False, False
        for index, contact in enumerate(data.contact[:data.ncon]):
            if contact.dist > cfg.contact_distance or contact.efc_address < 0:
                continue
            a, b = int(contact.geom1), int(contact.geom2)
            pair = [self._geom_name(a), self._geom_name(b)]
            target_pair = a in self.target_geoms or b in self.target_geoms
            robot_pair = a in self.robot_geoms or b in self.robot_geoms
            if target_pair:
                other = b if a in self.target_geoms else a
                if other in self.robot_geoms:
                    target_hits.append(pair)
                    left |= other in self.left_finger_geoms
                    right |= other in self.right_finger_geoms
                    left_pad |= other in self.left_geoms
                    right_pad |= other in self.right_geoms
                    finger |= other in self.finger_geoms
                elif other not in self.target_geoms:
                    force = np.zeros(6)
                    self.mj.mj_contactForce(self.model, data, index, force)
                    normal_z = float(abs(contact.frame.reshape(3, 3)[0, 2]))
                    # Test real contact geometry, never a BDDL region's stub.
                    if (contact.pos[2] < center_of_mass[2] - 0.001
                            and normal_z >= cfg.support_normal_z
                            and force[0] >= cfg.minimum_support_force):
                        supports.append({'pair': pair, 'normal_z': normal_z,
                                         'normal_force': float(force[0]),
                                         'contact_position': contact.pos.copy().tolist(),
                                         'object_com_z': float(center_of_mass[2])})
            if robot_pair:
                object_name, robot_geom = None, None
                if a in self.object_geom_owner and b in self.robot_geoms:
                    object_name, robot_geom = self.object_geom_owner[a], b
                elif b in self.object_geom_owner and a in self.robot_geoms:
                    object_name, robot_geom = self.object_geom_owner[b], a
                if robot_geom in self.left_finger_geoms:
                    robot_part = 'left_finger'
                elif robot_geom in self.right_finger_geoms:
                    robot_part = 'right_finger'
                elif robot_geom in self.gripper_geoms:
                    robot_part = 'palm'
                else:
                    robot_part = 'arm_or_other'
                robot_details.append({'pair': pair, 'distance': float(contact.dist),
                                      'penetration': max(0., -float(contact.dist)),
                                      'object': object_name, 'robot_part': robot_part})
                allowed = target_pair and (
                    (a in self.gripper_geoms and b in self.target_geoms)
                    or (b in self.gripper_geoms and a in self.target_geoms))
                incidental_object = None
                if not allowed:
                    if a in self.gripper_geoms and b in self.object_geom_owner:
                        incidental_object = self.object_geom_owner[b]
                    elif b in self.gripper_geoms and a in self.object_geom_owner:
                        incidental_object = self.object_geom_owner[a]
                if incidental_object is not None and incidental_object != self.target_name:
                    incidental.append({'pair': pair, 'object': incidental_object,
                                       'penetration': max(0., -float(contact.dist))})
                    allowed = cfg.allow_initial_incidental_gripper_contacts
                if not allowed:
                    unexpected.append(pair)
        speed = float(np.linalg.norm(velocity[3:]))
        angular_speed = float(np.linalg.norm(velocity[:3]))
        supported = bool(supports)
        stable = supported and speed <= cfg.stable_linear_speed and angular_speed <= cfg.stable_angular_speed
        now = float(data.time)
        if self._last_time is None or now != self._last_time:
            self._support_streak = self._support_streak + 1 if supported else 0
            self._stable_streak = self._stable_streak + 1 if stable else 0
            self._last_time = now
        bilateral = bool(left and right)
        if target_hits:
            state = ('grasped_supported' if bilateral else 'touch_only') if supported else (
                'grasped_airborne' if bilateral else 'unsupported_contact')
        else:
            state = 'clear_supported' if supported else 'clear_unsettled'
        displacement = float(np.linalg.norm(pos - self.reference_position))
        height_change = float(pos[2] - self.reference_position[2])
        angle = float(np.linalg.norm(Rotation.from_matrix(mat @ self.reference_rotation.T).as_rotvec()))
        eef_pos = data.site_xpos[self.site].copy()
        eef_quat = Rotation.from_matrix(data.site_xmat[self.site].reshape(3, 3)).as_quat()
        object_velocities = {}
        for name, body in self.object_bodies.items():
            object_velocity = np.zeros(6)
            self.mj.mj_objectVelocity(self.model, data, self.mj.mjtObj.mjOBJ_BODY,
                                     body, object_velocity, 0)
            object_velocities[name] = {
                'linear': object_velocity[3:].tolist(),
                'angular': object_velocity[:3].tolist(),
                'linear_speed': float(np.linalg.norm(object_velocity[3:])),
                'angular_speed': float(np.linalg.norm(object_velocity[:3])),
            }
        result = {
            'state': state,
            'eligible_contact_exit': bool(state in ('touch_only', 'grasped_supported')
                and finger and not unexpected and speed <= cfg.maximum_start_speed
                and abs(height_change) <= cfg.maximum_height_change
                and displacement <= cfg.maximum_object_displacement
                and angle <= cfg.maximum_orientation_change),
            'target_contact': bool(target_hits), 'target_contacts': target_hits,
            'finger_contact': bool(finger), 'bilateral_finger_contact': bilateral,
            'bilateral_pad_contact': bool(left_pad and right_pad),
            'support_contact': supported, 'support_contacts': supports,
            'unexpected_contacts': unexpected,
            'incidental_contacts': incidental, 'robot_contact_details': robot_details,
            'all_object_poses': {name: {'position': data.xpos[body].copy().tolist(),
                                      'quaternion_wxyz': data.xquat[body].copy().tolist()}
                                 for name, body in self.object_bodies.items()},
            'all_object_velocities': object_velocities,
            'object_position': pos.tolist(),
            'object_center_of_mass': center_of_mass.tolist(),
            'object_quaternion_wxyz': data.xquat[self.target_body].copy().tolist(),
            'object_linear_velocity': velocity[3:].tolist(),
            'object_angular_velocity': velocity[:3].tolist(),
            'object_speed': speed, 'object_angular_speed': angular_speed,
            'object_displacement': displacement, 'object_height_change': height_change,
            'object_orientation_change': angle,
            'eef_position': eef_pos.tolist(),
            'eef_quaternion_wxyz': eef_quat[[3, 0, 1, 2]].tolist(),
            'joint_positions': data.qpos[self.qidx].copy().tolist(),
            'gripper_positions': data.qpos[self.gidx].copy().tolist(),
            'gripper_gap': float(np.abs(data.qpos[self.gidx]).sum()),
            'eef_target_distance': float(np.linalg.norm(eef_pos - pos)),
            'simulation_time': now, 'support_streak': self._support_streak,
            'stable_streak': self._stable_streak, 'object_stable': bool(stable),
        }
        return result
