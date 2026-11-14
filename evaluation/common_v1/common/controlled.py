import copy
from t3_source_window import reached
def source_check(result, preparation, ticks, spec, metadata, actions_sha256):
    failures = []
    trigger = result.get('trigger_tick') or {}
    initial = result.get('initial_tick') or {}
    switch = next((x for x in result.get('turns', []) if x.get('turn_id') == 'U1'), {})
    source_id = result.get('source_task_id')
    count = metadata['steps']
    source_steps = [x for x in ticks if x.get('physics_tick') is True
        and x.get('phase') == 'T3_private_fixed_preparation_not_method_actions'
        and x.get('time', float('inf')) <= trigger.get('time', 0)]
    checks = {
        'proof_passed': preparation.get('passed') is True,
        'U0_before_preparation': preparation.get('source_U0_precedes_preparation') is True,
        'correct_source_key': preparation.get('source_key') == str(spec['source_task']) + '_' + spec['phase'],
        'endpoint_exact_identity': preparation.get('actual_state_identity') == metadata['state_identity'],
        'registered_actions_hash': actions_sha256 == metadata['actions_sha256'],
        'every_registered_reference_tick_present': len(source_steps) == count and count > 0,
        'reference_steps_ordered': [x['step'] for x in source_steps] == list(range(1, count + 1)),
        'reference_bound_to_actual_U0': bool(source_id) and all(x.get('task_id') == source_id for x in source_steps),
        'not_falsified_as_method_policy': all(x.get('policy_action') is False for x in source_steps),
        'trigger_before_U1': 0 < trigger.get('time', 0) <= switch.get('audio_started_wall', -1),
    }
    try:
        # The original physical predicate is unchanged. Its action-count gate
        # now explicitly counts recorded reference controls, never VLA calls.
        sample = dict(trigger, policy_actions=len(source_steps))
        checks['original_physical_trigger'] = reached(sample, spec, source_id,
            initial['measurements']['bowl']['articulation']['stove'])
    except (KeyError, ValueError, TypeError):
        checks['original_physical_trigger'] = False
    failures = [name for name, passed in checks.items() if not passed]
    return dict(name='controlled_source_reference_actions_and_original_physical_trigger',
        status='pass' if not failures else 'fail', checks=checks,
        reference_controls=len(source_steps), method_source_policy_required=False,
        reference_controls_not_counted_as_method_VLA=True, failures=failures)



def adapt_source_check(legacy, check, result):
    controlled = copy.deepcopy(legacy)
    previous = [x for x in controlled.get('checks', []) if x['name'] == 'independent_trigger_predicate']
    if not previous:
        early = any(x.get('name') == 'source_trigger_reached' and x.get('status') == 'fail' for x in controlled.get('checks', []))
        no_switch = not result.get('trigger_tick') and not any(x.get('turn_id') == 'U1' for x in result.get('turns', []))
        if early and no_switch and all(controlled.get(k) == 'fail' for k in ['interaction', 'target', 'instruction']):
            controlled['controlled_source_early_rejection'] = 'source never reached; preserve all original failures'
            controlled['original_natural_interaction'] = legacy['interaction']
            controlled['original_natural_trigger_check'] = None
            controlled['track_not_comparable_to_natural_preparation'] = True
            return controlled
    assert len(previous) == 1, 'exactly_one_natural_source_action_predicate_expected'
    controlled['checks'] = [x for x in controlled['checks'] if x['name'] != 'independent_trigger_predicate'] + [check]
    controlled['failures'] = [x['name'] for x in controlled['checks'] if x['status'] != 'pass']
    controlled['interaction'] = 'pass' if not controlled['failures'] else 'fail'
    controlled['scoring_version'] += '; controlled-source-v2: explicit reference provenance replaces method-source-action gate only'
    controlled['original_natural_interaction'] = legacy['interaction']
    controlled['original_natural_trigger_check'] = previous[0]
    controlled['track_not_comparable_to_natural_preparation'] = True
    return controlled

