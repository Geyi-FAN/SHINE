"""Optional controller guards. These NEVER contribute to benchmark scoring."""

def grasp_handover(grasp_valid, target_reached, rules):
    if target_reached: return 'evaluate_target'
    c=rules['controller_only'];n=c['grasp_confirmation_steps'];loss=c['grasp_loss_steps']
    if len(grasp_valid)>=n and all(grasp_valid[-n:]):return 'allow_transport'
    if len(grasp_valid)>=loss and not any(grasp_valid[-loss:]):return 'pause_and_reassess_grasp'
    return 'wait'
