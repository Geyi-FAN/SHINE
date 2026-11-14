"""One task authority owns queue guards; no simulator pose/plan is read here."""
def advance_verified_queue(state):
    if(state.mode!='completed' or state.completion_status!='verified' or
       not state.deferred_task or
       (state.agent_execution or {}).get('completion_current_verified')is not True):
        return
    # RobotState independently validates episode/predecessor/version, cancellation,
    # replacement, speech-input barriers and native-only release prerequisites.
    # A stale symbolic monitor snapshot must not add a second release gate.
    state._run_deferred()
