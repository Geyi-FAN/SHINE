"""Physical restore predicates shared by rollout audit and acceptance checks."""
import numpy as np

def gates(m,ref,tol):
 return dict(position=float(np.linalg.norm(np.asarray(m['object_position'])-ref))<=tol,
  released=not m['target_contact'],supported=bool(m['support_contact']),open=m['gripper_gap']>=.065,
  linear=m['object_speed']<=.012,angular=m['object_angular_speed']<=.20)


def order_errors(goal, restore25, withdrawn):
    errors=set()
    if goal and not restore25: errors.add('target_reached_before_restore25')
    if goal and not withdrawn: errors.add('target_reached_before_withdraw')
    return errors
