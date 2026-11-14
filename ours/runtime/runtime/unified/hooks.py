"""One reviewed composition, used by every category, without case-ID routing."""
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]


def install_authority(core):
    if getattr(core, '_unified_authority_installed', False):
        return
    sys.path[:0] = [str(B/'common_fixes'), str(B/'branch_fixes/t4/kernel')]
    from t3_adapter.runtime_repairs import install as language_guards
    language_guards(core)
    from t4_adapter.objectives import install as selected_goal_guards
    selected_goal_guards()
    from waiting_runtime import install as waiting_guards
    waiting_guards(core)
    from unified.transport import install as transport
    transport()
    core._unified_authority_installed = True


def install_bridge(cls):
    if getattr(cls, '_unified_bridge_installed', False):
        return
    sys.path[:0] = [str(B/'common_fixes'), str(B/'branch_fixes/t4/kernel')]
    from t06_goal_language import install as explicit_nouns
    from t09_goal_prefix import install as preservation_prefix
    from t03_wording import install as exact_authorized_wording
    explicit_nouns()
    preservation_prefix()
    exact_authorized_wording()
    from unified.t4_bridge import install_bridge as current_policy_guard, install_ownership
    from observed_completion import ObservedCompletion
    install_ownership(ObservedCompletion)
    current_policy_guard(cls)
    from t09_lifecycle import install as lifecycle
    from t01r_reacquisition import install as reacquisition
    from t01r_video_shape import install as video_shape
    from t06l_inspection import install as scoped_observation
    from t06l_observation_handoff import install as observation_handoff
    lifecycle(cls)
    reacquisition()
    video_shape(cls)
    scoped_observation()
    observation_handoff(cls)
    from latency_integration import install as evidence_bootstrap
    evidence_bootstrap(cls)
    from stage_continuation import install as unfinished_operation
    import planner
    unfinished_operation(planner)
    cls._unified_bridge_installed = True
