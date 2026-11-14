"""T4 completion contract alignment and a paused-hold scheduling race guard.

No task IDs, desired plans, coordinates, private case data or new thresholds.
Raw native/adjusted evidence stays intact. Only the stop candidate must meet
the native target that the original independent Easy-10 protocol scores.
"""
from functools import wraps

VERSION='paused-hold-drop-native-completion-v1'

def install_completion(module=None):
    if module is None:
        from repair6 import completion as module
    cls=module.CompletionGate
    old=cls.observe
    if getattr(old,'_t09_native_completion',False):return
    @wraps(old)
    def observe(gate,row,subject,target_task,return_only=False,full_contract=False):
        current_native=row.get('goal_frame',{}).get('goal') is True
        return old(gate,row,subject,target_task,return_only,
                   full_contract=bool(full_contract and current_native))
    observe._t09_native_completion=True
    cls.observe=observe

def install_hold(cls):
    old=cls.apply
    if getattr(old,'_t09_paused_hold',False):return
    @wraps(old)
    def apply(bridge,action,phase):
        # Owner callers hold state.lock and env_lock. Mode may have changed
        # between their outer running check and acquiring these locks.
        # A paused no-op is never an env.step or a fabricated action receipt.
        if phase=='async_wait_hold' and bridge.state.mode=='paused':
            bridge.log('t09_paused_hold_dropped',version=VERSION,
                reason='mode_changed_before_owner_lock',dropped_at_physics_step=bridge.physics_steps,
                action_applied=False,task_replayed=False)
            return None
        return old(bridge,action,phase)
    apply._t09_paused_hold=True
    cls.apply=apply

def identity(cls):
    from repair6.completion import CompletionGate
    return dict(version=VERSION,
        paused_hold_guarded=any(getattr(base.__dict__.get('apply'),'_t09_paused_hold',False) for base in cls.__mro__),
        guarded_apply_classes=[base.__module__+'.'+base.__name__ for base in cls.__mro__ if getattr(base.__dict__.get('apply'),'_t09_paused_hold',False)],
        native_completion_guarded=bool(getattr(CompletionGate.observe,'_t09_native_completion',False)),
        completion_basis='current_native_target_plus_original_release_stability_invariants_and_40_hold',
        raw_native_adjusted_measurements_preserved=True,thresholds_changed=False,
        independent_score_changed=False,planner_truth_added=False)

def install(cls):
    install_completion()
    install_hold(cls)
