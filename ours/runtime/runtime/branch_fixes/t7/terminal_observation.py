"""Refresh terminal observations through the existing owner and real pose hold."""
TERMINAL = frozenset(['completed', 'cancelled', 'needs_review', 'budget_exhausted'])

def tick(bridge, state, due, hold_factory=None):
    if not due or state.mode not in TERMINAL:
        return False
    with state.lock:
        if state.mode not in TERMINAL or state.task_id != bridge.task:
            return False
        if not bridge.env_lock.acquire(blocking=False):
            return False
        try:
            subject = (state.mode, bridge.token())
            if getattr(bridge, '_t6_terminal_hold_subject', None) != subject:
                if hold_factory is None:
                    from hold_gate import PoseHold
                    hold_factory = PoseHold
                bridge.pose = hold_factory(bridge.obs, bridge.env.env.robots[0].controller)
                bridge._t6_terminal_hold_subject = subject
                bridge.log('terminal_symbolic_observation_hold', mode=state.mode,
                           source='current_robot_proprioception', creates_task_action=False)
            bridge.apply(bridge.pose.action(bridge.obs), 'async_wait_hold')
            return True
        finally:
            bridge.env_lock.release()
