"""Independent controlled-track scorer; preserve the unmodified natural score.

Only the source-action provenance check differs. Original natural scoring
requires method policy actions; controlled preparation instead requires every
registered reference action and the exact same physical source predicate.
Neither reference actions nor hold actions are called actual method VLA.
"""
import copy
import hashlib
import json
import sys
from pathlib import Path

N = Path(__file__).resolve().parents[1]
OLD = N.parent / 'our_T3_T1_T6_repair_20261109'
sys.path.insert(0, str(OLD / 'tools'))
from legacy_scoring import score as natural_score
sys.path.insert(0, str(N / 'tools'))
from t3_source_window import reached


def read(path):
    return json.loads(Path(path).read_text())


def lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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

def score(case, branch='T3'):
    assert branch == 'T3'
    before = sha(case / 'result.json')
    legacy = read(case / 'SCORE_AUDITED.json') if (case / 'SCORE_AUDITED.json').exists() else natural_score(case, branch)
    assert legacy.get('case_id') == case.name, 'Wrong natural-score evidence identity'
    (case / 'SCORE_NATURAL_PROTOCOL_UNCHANGED.json').write_text(json.dumps(legacy, ensure_ascii=False, indent=2) + '\n')
    result = read(case / 'result.json')
    spec = read(N.parents[1] / 'regressions/c3r_pi05_70_serial_20261108/data/T3/specs' / (case.name + '.json'))
    key = str(spec['source_task']) + '_' + spec['phase']
    bank = Path('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/our_t3_prepared_judge_20261109/data/T3-controlled-source-prefix-v2-20261109') / key
    try:
        check = source_check(result, read(case / 'SOURCE_PREPARATION.json'),
            lines(case / 'recordings' / result['episode_id'] / 'control_ticks.jsonl'),
            spec, read(bank / 'PREFIX.json'), sha(bank / 'actions.jsonl'))
    except (OSError, ValueError, KeyError, TypeError) as error:
        check = dict(name='controlled_source_reference_actions_and_original_physical_trigger',
            status='fail', reason=type(error).__name__)
    controlled = adapt_source_check(legacy, check, result)
    assert sha(case / 'result.json') == before
    (case / 'SCORE_CONTROLLED.json').write_text(json.dumps(controlled, ensure_ascii=False, indent=2) + '\n')
    return controlled
