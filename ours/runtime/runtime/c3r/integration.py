"""Bind C3r to the existing single owner, task tokens and pause lifecycle."""
import functools
import numpy as np


def abort_program(recovery, frame, reason):
    if recovery is None or recovery.active is None:
        return False
    pose = recovery.active
    pose.done = True
    pose.reason = reason
    recovery._record(dict(frame=frame, event='code_policy_cancelled', reason=reason,
                          steps=pose.ticks, creates_completion=False))
    recovery.active = None
    recovery.pose_stage = None
    return True


def stage_errors(bridge, previous, inp, out):
    errors = previous(inp, out)
    if not errors or not isinstance(out, dict) or out.get('status') != 'plan_ready':
        return errors
    mon, recovery = bridge.saved_mon, bridge.saved_recovery
    if mon is None or recovery is None or not mon.samples:
        return errors
    from stage_lifecycle import classify
    verdict = classify(mon.active, out.get('remaining_plan') or [], mon.last,
                       mon.samples[-1]['width'], mon.held, recovery.visual_facts)
    # Only the frozen C3r same-object, fresh empty/support prerequisite may
    # replace T3's strict equality guard. The runner performs admission again.
    if verdict['mode'] == 'interrupt_for_reacquisition':
        bridge.log('c3r_reacquisition_plan_admitted', **verdict)
        # This exception applies only to T3's unfinished-stage equality check.
        # Keep every other validator's error, even when the prerequisite itself
        # is fresh and valid; otherwise composition could hide a bad plan.
        return [e for e in errors if not str(e).startswith('ACTIVE_STAGE_NOT_RETIRED')]
    return errors


def install(cls):
    if getattr(cls, '_c3r_integrated', False):
        return
    hooks, start, apply = cls.install_hooks, cls.start, cls.apply

    def install_hooks(b):
        hooks(b)
        import cap_recovery, local_transport
        from t3repair import stages
        # CodeRecovery imports a separate function alias. Wrapping only the
        # existing RecoveryObserver would leave this request outside pause and
        # late-result validation. Use the exact same bridge network boundary.
        transport = local_transport.recovery_request_json
        cap_recovery.recovery_request_json = lambda req, timeout=90: b.network(
            'recovery', transport, req, timeout=timeout)
        original_class = cap_recovery.CodeRecovery
        b.saved_code_recovery = None
        b.saved_code_subject = None

        def factory(folder, user_message, episode_id):
            subject = tuple(b.token()[:3])
            if b.saved_code_subject != subject:
                abort_program(b.saved_code_recovery, b.control_steps, 'task_replaced')
                b.saved_code_recovery = original_class(folder, user_message, episode_id)
                b.saved_code_subject = subject
            # Keep attempts and call limits across a same-task resume. Log to
            # the original generation directory rather than losing history.
            return b.saved_code_recovery

        cap_recovery.CodeRecovery = factory
        previous_errors = stages.errors
        stages.errors = lambda inp, out: stage_errors(b, previous_errors, inp, out)

    def start_kernel(b, *args, **kwargs):
        if b.saved_code_recovery is not None:
            abort_program(b.saved_code_recovery, b.control_steps,
                          'kernel_generation_changed_requires_fresh_recovery')
        return start(b, *args, **kwargs)

    def apply_action(b, action, phase):
        value = np.asarray(action, dtype=float)
        if value.shape != (7,) or not np.isfinite(value).all():
            raise ValueError('C3r gateway requires a finite seven-dimensional action')
        return apply(b, value, phase)

    cls.install_hooks = install_hooks
    cls.start = start_kernel
    cls.apply = apply_action
    cls._c3r_integrated = True
