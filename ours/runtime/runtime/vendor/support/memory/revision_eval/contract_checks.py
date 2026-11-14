"""Runtime contracts for the v3 pilot, independent of MuJoCo and model imports.

All measurements below are existing ContactStateMonitor/Runtime.measure fields.
Relation checks use LIBERO's actual ``env.env._eval_predicate`` callback; they
never infer an in-drawer relation from a fixed world-space bowl position.
The collector must call the snapshot audit *after replay*, the frame guards
after every step, and the completion audit before marking a run trainable.
These checks supplement, rather than replace, physical replay and action audits.
"""
from copy import deepcopy
from math import sqrt


BOWL_IN_TOP = ('in', 'akita_black_bowl_1', 'wooden_cabinet_1_top_region')
BOWL_ON_PLATE = ('on', 'akita_black_bowl_1', 'plate_1')
TOP_OPEN = ('open', 'wooden_cabinet_1_top_region')
OBJECT_TOLERANCE = .025
PRESERVE_TOLERANCE = .015


def _distance(a, b):
    return sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def _report(reasons, **detail):
    return dict(passed=not reasons, reasons=reasons, **detail)


def _raise(report, prefix):
    if not report['passed']:
        raise RuntimeError(prefix + ':' + ','.join(report['reasons']))
    return report


def _predicate_true(predicate, relation):
    # Missing predicate support is not silently treated as successful evidence.
    return predicate is not None and bool(predicate(list(relation)))


def capture_revision_predicates(config, predicate):
    """Record official LIBERO relations at the switch and after each action.

    Only the newly supported clauses need these fields. Existing v3 episodes
    without these clauses keep their original evidence contract. A collector
    must call this while the live simulator is at the recorded state; positions
    or the final goal alone cannot reconstruct these relations reliably.
    """
    names = {c['predicate'] for c in config.get('acceptance_v2', {}).get('events', [])}
    wanted = {}
    if names & {'held_object_restored_supported_released', 'top_drawer_entrance_available'}:
        wanted.update(top_drawer_open=TOP_OPEN, bowl_in_top_drawer=BOWL_IN_TOP)
    if 'bowl_removed_from_plate' in names:
        wanted['bowl_on_plate'] = BOWL_ON_PLATE
    if wanted and predicate is None:
        raise RuntimeError('live_revision_predicate_callback_missing')
    return {key: bool(predicate(list(relation))) for key, relation in wanted.items()}


def _relation_sequence(at, trace, switch, keys):
    """Return pre-switch plus post-action booleans; never fill missing records."""
    values, reasons = [], []
    for i, state in enumerate([at] + [r['after'] for r in trace[switch:]]):
        measured = state.get('revision_predicates', {})
        for key in keys:
            if type(measured.get(key)) is not bool:
                reasons.append('official_relation_record_missing:' + key + ':state_' + str(switch + i))
        values.append(measured)
    return values, reasons


def drawer_transition_audit(contract, result, trace, at, switch):
    """Prove conditional set-down and open-before-insertion in recorded order.

    Actions have zero-based indices; a completed event at step k has consumed
    actions [0, k). Opening starts at the first >12 mm increase in drawer travel
    from the switch state, not at its later fully-open threshold. Stable release
    must finish before that action. The official open predicate must already be
    true in the state immediately before the first recorded In transition.
    """
    states, missing = _relation_sequence(at, trace, switch,
        ('top_drawer_open', 'bowl_in_top_drawer'))
    if missing:
        bad = _report(missing, evidence='recorded_live_libero_relations')
        return dict(putback=bad, entrance=deepcopy(bad))
    start = at.get('articulation', {}).get('top')
    if start is None:
        bad = _report(['top_drawer_joint_measurement_missing'])
        return dict(putback=bad, entrance=deepcopy(bad))
    opening = None
    for step in range(switch, len(trace)):
        value = trace[step]['after'].get('articulation', {}).get('top')
        if value is None:
            bad = _report(['top_drawer_joint_measurement_missing:step_' + str(step)])
            return dict(putback=bad, entrance=deepcopy(bad))
        if opening is None and float(value) < float(start) - .012:
            opening = step
    held = bool(contract.get('source_object') and at.get('target_contact')
                and not at.get('support_contact'))
    required = held and not states[0]['top_drawer_open']
    problems, release = [], None
    if required:
        end = result.get('restore_end_step')
        if not contract.get('restore') or end is None or opening is None:
            problems.append('required_putback_before_drawer_open_event_missing')
        elif not switch <= end <= opening:
            problems.append('putback_did_not_finish_before_drawer_motion')
        elif contract.get('source_reference') is None:
            problems.append('conditional_putback_initial_reference_missing')
        else:
            release = stable_release_audit(trace, end, start_step=switch,
                object_name=contract['source_object'], reference=contract['source_reference'])
            problems.extend(release['reasons'])
    putback = _report(problems, required=required, held_at_switch=held,
        top_open_at_switch=states[0]['top_drawer_open'],
        drawer_open_start_step=opening, release=release,
        evidence='recorded_switch_condition_and_consecutive_post_action_release_states')
    problems, insertion = [], None
    if states[0]['bowl_in_top_drawer']:
        problems.append('bowl_already_inside_at_switch_no_insertion_event')
    else:
        for offset in range(1, len(states)):
            if states[offset]['bowl_in_top_drawer']:
                insertion = switch + offset - 1
                if not states[offset - 1]['top_drawer_open']:
                    problems.append('drawer_not_officially_open_before_bowl_insertion')
                break
        if insertion is None:
            problems.append('recorded_bowl_insertion_event_missing')
    entrance = _report(problems, insertion_action_step=insertion,
        evidence='official_open_in_pre_action_state_before_first_official_In_transition')
    return dict(putback=putback, entrance=entrance)


def repair_contract(config, contract):
    """Return a copy with relation preservation instead of contradictory anchors."""
    ct = deepcopy(contract)
    ct['contract_version'] = 'interaction_revision.contract.v3'
    if config['branch'] == 'CLOSE_INPLACE':
        ct['preserve_object'] = False
        ct['preserve_relation'] = list(BOWL_IN_TOP)
    return ct


def snapshot_contract_audit(config, initial, at, contract, *, predicate=None):
    """Check live eligibility, not just a phase label cached in a source bank.

No-effect RESTORE/FULL_RESTORE states remain catalog entries, but must not be
counted as distinct undo demonstrations. An automatic BASE set-down is exempt:
it may need to release a supported grasp even with negligible object movement.
Stage checks here cover observable instantaneous conditions. Placement direction
and five-frame terminal stability still need the source bank phase labeler.
"""
    reasons = []
    source, target = int(config['source']), int(config['target'])
    branch, phase = config['branch'], config['phase']
    goals = at.get('goals', {})
    if not config.get('control', branch in ('CONTINUE', 'PAUSE')):
        if goals.get(str(target), False):
            reasons.append('new_goal_already_satisfied_at_switch')
    contact = bool(at.get('target_contact'))
    bilateral = bool(at.get('bilateral_finger_contact'))
    supported = bool(at.get('support_contact'))
    if phase in ('M1', 'C3') and not (contact and supported):
        reasons.append('phase_requires_supported_contact')
    if phase in ('M2', 'C4') and not (contact and bilateral and not supported):
        reasons.append('phase_requires_airborne_bilateral_grasp')
    if phase in ('M3', 'C5') and not contact:
        reasons.append('placement_phase_requires_contact')
    if phase in ('M2', 'M3', 'C4', 'C5') and contact and not supported:
        if not bilateral or float(at.get('object_speed', float('inf'))) > .30:
            reasons.append('unstable_airborne_grasp')
    if phase in ('M0', 'C2') and contact:
        reasons.append('precontact_phase_already_contacting_object')
    if phase in ('M4', 'C6'):
        if (not goals.get(str(source), False) or contact
                or float(at.get('object_speed', float('inf'))) > .012
                or float(at.get('object_angular_speed', float('inf'))) > .20
                or float(at.get('gripper_gap', 0.)) < .065):
            reasons.append('terminal_object_state_not_released_stable')
    if phase in ('D2', 'P2', 'K2') and not goals.get(str(source), False):
        reasons.append('terminal_source_goal_not_satisfied')

    changes = {}
    name = contract.get('source_object')
    if name and name in initial.get('all_object_poses', {}) and name in at.get('all_object_poses', {}):
        changes['object_displacement_m'] = _distance(
            at['all_object_poses'][name]['position'],
            initial['all_object_poses'][name]['position'])
    # Require a real object effect for an explicitly distinct restoration branch.
    if branch in ('RESTORE', 'FULL_RESTORE') and contract.get('restore'):
        if 'object_displacement_m' not in changes:
            reasons.append('restore_reference_missing')
        elif changes['object_displacement_m'] <= OBJECT_TOLERANCE:
            reasons.append('no_changed_object_effect_to_restore')
    # A future catalog edit must not silently pair "leave it where it is" with
    # a controller that returns a moved object to its episode-start position.
    for clause in config.get('acceptance_v2', {}).get('invariants', []):
        if (clause['predicate'] == 'source_object_unchanged'
                and clause.get('object') == name and contract.get('restore')
                and changes.get('object_displacement_m', 0.) >
                    float(clause.get('tolerance_m', PRESERVE_TOLERANCE)) + OBJECT_TOLERANCE):
            reasons.append('declared_preservation_conflicts_with_restore_motion')
    close = contract.get('close')
    if close:
        tolerance = .08 if close == 'stove' else .012
        value = at.get('articulation', {}).get(close)
        if value is None:
            reasons.append('close_joint_measurement_missing')
        else:
            changes['close_joint_distance_from_zero'] = abs(float(value))
            if abs(float(value)) <= tolerance:
                reasons.append('no_changed_joint_effect_to_close')
    relation = contract.get('preserve_relation')
    if relation and not _predicate_true(predicate, relation):
        reasons.append('required_relation_absent_at_switch')
    payload = contract.get('payload')
    if payload and not _predicate_true(predicate, payload):
        reasons.append('payload_relation_absent_at_switch')
    return _report(reasons, changes=changes)


def contract_frame_audit(contract, after, *, predicate=None):
    """Continuous old-result preservation, including moving drawer contents."""
    reasons = []
    for key, reference in contract.get('preserve_joints', {}).items():
        tolerance = .08 if key == 'stove' else .012
        if abs(after['articulation'][key] - reference) > tolerance:
            reasons.append('preserved_joint_changed:' + key)
    if contract.get('preserve_object'):
        name = contract['source_object']
        if _distance(after['all_object_poses'][name]['position'],
                     contract['preserve_reference']['position']) > PRESERVE_TOLERANCE:
            reasons.append('preserved_object_moved')
    for key, reason in (('preserve_relation', 'preserved_relation_broken'),
                        ('payload', 'payload_relation_broken')):
        relation = contract.get(key)
        if relation and not _predicate_true(predicate, relation):
            reasons.append(reason)
    if contract.get('closed_active'):
        key = contract['close']
        relation = (['turnoff', 'flat_stove_1'] if key == 'stove' else
                    ['close', 'wooden_cabinet_1_' + key + '_region'])
        if not _predicate_true(predicate, relation):
            reasons.append('required_closed_state_lost')
    if contract.get('restored_active'):
        if _distance(after['all_object_poses'][contract['source_object']]['position'],
                     contract['source_reference']['position']) > OBJECT_TOLERANCE:
            reasons.append('restored_object_moved_again')
    return _report(reasons)


def enforce_contract_frame(contract, after, *, predicate=None):
    return _raise(contract_frame_audit(contract, after, predicate=predicate), 'contract_v3')


def pause_grip(at, previous_action=None):
    """Keep an existing grasp, including one still supported by the table.

    Otherwise retain the latest applied command (read source HDF5 actions[t-1]), which
also covers holding a fixture handle that is not the monitor's target object.
Without action history, partially closed contact is ambiguous and fails closed
for collection instead of silently opening a possibly loaded gripper.
"""
    if at.get('bilateral_finger_contact') or (
            at.get('target_contact') and not at.get('support_contact')):
        return 1.
    if previous_action is not None:
        if len(previous_action) != 7:
            raise ValueError('pause_previous_action_must_have_seven_dimensions')
        return 1. if float(previous_action[6]) > 0 else -1.
    if at.get('robot_contact_details') and float(at.get('gripper_gap', 0.)) < .065:
        raise RuntimeError('pause_previous_grip_command_required')
    return -1.


def pause_frame_audit(at, now):
    """Per-step preservation during PAUSE; don't only inspect its final frame."""
    reasons = []
    if _distance(at['eef_position'], now['eef_position']) > .025:
        reasons.append('pause_eef_drift')
    if at.get('bilateral_finger_contact') and not now.get('bilateral_finger_contact'):
        reasons.append('pause_lost_existing_bilateral_grasp')
    if at.get('target_contact') and not at.get('support_contact'):
        if not now.get('target_contact'):
            reasons.append('pause_lost_airborne_grasp')
    for name, old in at.get('all_object_poses', {}).items():
        if _distance(old['position'], now['all_object_poses'][name]['position']) > .025:
            reasons.append('pause_object_drift:' + name)
    for key, old in at.get('articulation', {}).items():
        if abs(now['articulation'][key] - old) > (.08 if key == 'stove' else .012):
            reasons.append('pause_articulation_changed:' + key)
    return _report(reasons)


def enforce_pause_frame(at, now):
    return _raise(pause_frame_audit(at, now), 'pause_contract_v3')


def stable_release_audit(trace, end_step, *, start_step=0, object_name=None,
                         reference=None, stable_frames=5, tolerance_m=OBJECT_TOLERANCE):
    """Inspect the actual last N post-action states of a release event.

    ``reference`` is optional for leave-in-place contact exits, mandatory at the
    caller for restore events. All N frames must follow the new instruction.
    The function can also be used by an online teacher to determine when its
    bounded release-verification loop has collected enough evidence.
    """
    end_step = int(end_step)
    begin = end_step - int(stable_frames)
    reasons = []
    if stable_frames < 1 or begin < int(start_step) or end_step > len(trace):
        return _report(['release_window_missing'], stable_frames=0, end_step=end_step)
    rows = trace[begin:end_step]
    if len(rows) != stable_frames:
        return _report(['release_window_missing'], stable_frames=0, end_step=end_step)
    for offset, row in enumerate(rows):
        m = row['after']
        prefix = 'frame_' + str(begin + offset) + ':'
        if m.get('target_contact') or float(m.get('gripper_gap', 0.)) < .065:
            reasons.append(prefix + 'object_not_released')
        if (not m.get('support_contact')
                or float(m.get('object_speed', float('inf'))) > .012
                or float(m.get('object_angular_speed', float('inf'))) > .20):
            reasons.append(prefix + 'object_not_supported_stable')
        if reference is not None:
            position = m.get('all_object_poses', {}).get(object_name, {}).get('position')
            if position is None or _distance(position, reference['position']) > tolerance_m:
                reasons.append(prefix + 'restore_position_mismatch')
    return _report(reasons, stable_frames=stable_frames if not reasons else 0,
                   begin_step=begin, end_step=end_step,
                   evidence='recorded_consecutive_post_action_states')


def completion_audit(config, contract, result, trace):
    """Verify event ordering and evidence already recorded by the SGS executor.

This does not re-create unrecorded per-frame SGS results. ``actor_finish`` must
still perform its live five-frame stability plus forty-frame hold checks; the
audit verifies their metadata and counts against the actual recorded phases.
"""
    reasons = []
    evidence_events, evidence_invariants = [], []
    switch = int(result.get('switch_step', len(trace)))
    actor = result.get('actor', {})
    start = int(result.get('target_start_step', actor.get('pure_start', switch)))
    for required, field in ((contract.get('restore'), 'restore_end_step'),
                            (contract.get('close'), 'close_end_step')):
        if required and (field not in result or not switch <= result[field] <= start):
            reasons.append('required_old_result_event_missing_or_out_of_order:' + field)
    restore = None
    if contract.get('restore') and 'restore_end_step' in result:
        restore = stable_release_audit(trace, result['restore_end_step'], start_step=switch,
                    object_name=contract['source_object'], reference=contract['source_reference'])
        reasons.extend('restore_event:' + x for x in restore['reasons'])
    if contract.get('restore') and contract.get('close'):
        if result.get('restore_end_step', len(trace) + 1) > result.get('close_start_step', -1):
            reasons.append('restore_event_must_precede_close_start')
    if config['branch'] == 'PAUSE':
        end = int(result.get('resume_step', switch))
        pause_rows = trace[switch:end]
        if end <= switch or len(pause_rows) != 40 or any(r['phase'] != 'pause_hold' for r in pause_rows):
            reasons.append('pause_resume_interval_missing_or_invalid')
    if actor.get('provider') == 'completed_goal_hold':
        rows = trace[switch:]
        if len([r for r in rows if r['phase'] == 'control_hold']) < 40:
            reasons.append('completed_control_hold_too_short')
        if any(not r['after']['goals'].get(str(config['source']), False) for r in rows):
            reasons.append('completed_control_goal_lost')
    else:
        if actor.get('stable_frames', 0) < 5 or actor.get('hold_frames', 0) < 40:
            reasons.append('sgs_evidence_missing')
        if not actor.get('final', {}).get('stable', False):
            reasons.append('sgs_final_not_stable')
        end = int(actor.get('actor_end', len(trace)))
        if sum(r['phase'] == 'sgs_hold' for r in trace[end:]) < 40:
            reasons.append('recorded_sgs_hold_too_short')
        authorized_teacher=(config.get('target_executor')=='rule_teacher' and config.get('config_id')=='R329_T02_M4_T04_SWITCH'
                            and actor.get('provider')=='rule_teacher' and actor.get('target_teacher_steps',0)>0)
        if not config.get('control') and actor.get('actor_steps', 0) <= 0 and not authorized_teacher:
            reasons.append('new_goal_not_executed_by_actor')
    # Resolve the declared catalog clauses into explicit evidence. Unknown
    # clauses fail closed; a catalog description never counts as implementation.
    declared = config.get('acceptance_v2', {})
    unsupported = []
    event_supported = {'source_object_restored_supported_released',
        'source_object_supported_released', 'required_articulation_closed',
        'pause_entered', 'explicit_resume_received', 'source_goal_sgs', 'target_goal_sgs',
        'held_object_restored_supported_released', 'top_drawer_entrance_available',
        'bowl_removed_from_plate'}
    invariant_supported = {'source_articulation_unchanged', 'source_object_unchanged',
        'restored_source_pose_preserved', 'required_closed_state_preserved',
        'payload_relation_preserved', 'stable_grasp_support_and_contact_preserved',
        'no_repeat_operation'}
    at = result.get('at_switch') or (trace[switch]['before'] if switch < len(trace) and 'before' in trace[switch] else {})
    drawer_evidence = None
    for clause in declared.get('events', []):
        name, scope = clause['predicate'], clause['scope']
        problem, evidence = [], {}
        if name not in event_supported:
            problem.append('unimplemented_acceptance_event:' + name)
            unsupported.append(name)
        elif name == 'source_object_restored_supported_released':
            if not contract.get('restore') or restore is None:
                problem.append('declared_restore_event_missing')
            else:
                problem.extend(restore['reasons']); evidence = restore
                if not switch <= result['restore_end_step'] <= start:
                    problem.append('restore_event_after_new_goal_start')
        elif name == 'source_object_supported_released':
            step = result.get('release_end_step')
            boundary = result.get('close_start_step') if scope == 'before_close' else start
            if step is None or boundary is None or not switch <= step <= boundary:
                problem.append('declared_release_event_missing_or_out_of_order')
            else:
                evidence = stable_release_audit(trace, step, start_step=switch,
                    object_name=clause.get('object'), stable_frames=clause.get('stable_frames', 5))
                problem.extend(evidence['reasons'])
        elif name == 'required_articulation_closed':
            step = result.get('close_end_step')
            receipt = result.get('close_event', {})
            key = clause['joint']
            expected = ['turnoff', 'flat_stove_1'] if key == 'stove' else ['close', 'wooden_cabinet_1_' + key + '_region']
            if (step is None or not switch <= step <= start or not receipt.get('passed')
                    or receipt.get('end_step') != step or receipt.get('predicate') != expected):
                problem.append('official_close_event_evidence_missing')
            evidence = receipt
        elif name in ('held_object_restored_supported_released', 'top_drawer_entrance_available'):
            if drawer_evidence is None:
                drawer_evidence = drawer_transition_audit(contract, result, trace, at, switch)
            evidence = drawer_evidence['putback' if name == 'held_object_restored_supported_released' else 'entrance']
            problem.extend(evidence['reasons'])
        elif name == 'bowl_removed_from_plate':
            states, missing = _relation_sequence(at, trace, switch, ('bowl_on_plate',))
            problem.extend(missing)
            step = result.get('restore_end_step', result.get('release_end_step'))
            if not missing and not states[0]['bowl_on_plate']:
                problem.append('bowl_not_on_plate_at_switch_no_removal_event')
            if step is None or not switch <= step <= min(start, len(trace)):
                problem.append('bowl_removal_not_verified_before_plate_actor_start')
            else:
                evidence = stable_release_audit(trace, step, start_step=switch,
                    object_name=BOWL_IN_TOP[1], stable_frames=5)
                problem.extend(evidence['reasons'])
                if not missing and any(states[k + 1 - switch]['bowl_on_plate'] for k in range(max(switch, step - 5), step)):
                    problem.append('bowl_still_on_plate_in_release_window')
                plate = at.get('all_object_poses', {}).get('plate_1', {}).get('position')
                if plate is None or any(
                        row['after'].get('all_object_poses', {}).get('plate_1', {}).get('position') is None
                        or _distance(row['after']['all_object_poses']['plate_1']['position'], plate) > PRESERVE_TOLERANCE
                        for row in trace[switch:step]):
                    problem.append('plate_moved_before_bowl_removal_or_pose_evidence_missing')
            evidence = dict(**evidence, before_plate_actor_step=start,
                official_on_relation_checked=not missing)
        elif name in ('pause_entered', 'explicit_resume_received'):
            end = int(result.get('resume_step', switch))
            pause = trace[switch:end]
            if len(pause) != 40 or any(r['phase'] != 'pause_hold' for r in pause):
                problem.append('pause_resume_interval_missing_or_invalid')
            if name == 'explicit_resume_received' and not result.get('resume_text_en'):
                problem.append('explicit_resume_instruction_missing')
            evidence = dict(begin_step=switch, end_step=end, recorded_hold_frames=len(pause),
                            instruction=result.get('resume_text_en'))
        elif name in ('source_goal_sgs', 'target_goal_sgs'):
            task = config['source'] if name == 'source_goal_sgs' else config['target']
            if actor.get('provider') == 'completed_goal_hold':
                hold_rows = [r for r in trace[switch:] if r['phase'] == 'control_hold']
                valid_sgs = len(hold_rows) >= 40
            else:
                end = int(actor.get('actor_end', len(trace)))
                hold_rows = trace[end:]
                valid_sgs = (actor.get('stable_frames', 0) >= 5
                    and actor.get('hold_frames', 0) >= 40 and actor.get('final', {}).get('stable', False)
                    and len(hold_rows) >= 40 and all(r['phase'] == 'sgs_hold' for r in hold_rows))
            if not valid_sgs or any(not row['after'].get('goals', {}).get(str(task), False) for row in hold_rows):
                problem.append('sgs_goal_evidence_missing_or_broken')
            evidence = dict(actor_stable_frames=actor.get('stable_frames'),
                recorded_hold_frames=len(hold_rows), target_task=task,
                evidence='live_actor_finish_SGS_and_recorded_goal_survival')
        evidence_events.append(dict(predicate=name, scope=scope, passed=not problem,
                                    reasons=problem, evidence=evidence))
        reasons.extend('declared_event:' + x for x in problem)

    for clause in declared.get('invariants', []):
        name, scope = clause['predicate'], clause['scope']
        problem, evidence = [], {}
        rows, begin = trace[switch:], switch
        if name not in invariant_supported:
            problem.append('unimplemented_acceptance_invariant:' + name)
            unsupported.append(name)
        elif name == 'source_articulation_unchanged':
            key = clause['joint']; reference = at.get('articulation', {}).get(key)
            if reference is None or any(abs(row['after']['articulation'][key] - reference) > clause['tolerance'] for row in rows):
                problem.append('source_articulation_not_preserved:' + key)
        elif name in ('source_object_unchanged', 'restored_source_pose_preserved'):
            obj = clause['object']
            if name == 'restored_source_pose_preserved':
                begin = result.get('restore_end_step')
                rows = trace[begin:] if begin is not None else []
                reference = contract.get('source_reference')
                if begin is None:problem.append('restore_invariant_start_missing')
            else:
                reference = at.get('all_object_poses', {}).get(obj)
            if reference is None or any(_distance(row['after']['all_object_poses'][obj]['position'],
                      reference['position']) > clause['tolerance_m'] for row in rows):
                problem.append('source_object_not_preserved:' + obj)
        elif name in ('required_closed_state_preserved', 'payload_relation_preserved'):
            # LIBERO relational predicates are evaluated online and cannot be
            # faithfully reconstructed from the recorded scalar pose summary.
            monitored = result.get('contract_monitored_predicates', [])
            checked = int(result.get('contract_frame_checks', 0))
            if name not in monitored or checked != len(trace) - switch:
                problem.append('continuous_relation_monitor_evidence_missing:' + name)
            if name == 'required_closed_state_preserved' and not contract.get('closed_active'):
                problem.append('closed_invariant_never_activated')
            if name == 'payload_relation_preserved':
                relation = contract.get('payload') or contract.get('preserve_relation')
                if relation != clause['relation']:
                    problem.append('payload_relation_monitor_mismatch')
            evidence = dict(successful_live_contract_checks=checked, predicate=name)
        elif name == 'stable_grasp_support_and_contact_preserved':
            end = int(result.get('resume_step', switch)); rows = trace[switch:end]
            if not at:problem.append('pause_initial_state_missing')
            else:
                for row in rows:
                    problem.extend(pause_frame_audit(at, row['after'])['reasons'])
            if len(rows) != 40:problem.append('pause_invariant_interval_missing')
        elif name == 'no_repeat_operation':
            if actor.get('provider') != 'completed_goal_hold' or any(row['phase'] != 'control_hold' for row in rows):
                problem.append('completed_goal_reexecuted')
        if not evidence:evidence = dict(begin_step=begin, checked_frames=len(rows), evidence='recorded_transition_metrics')
        evidence_invariants.append(dict(predicate=name, scope=scope, passed=not problem,
                                        reasons=problem, evidence=evidence))
        reasons.extend('declared_invariant:' + x for x in problem)
    return _report(reasons, event_order_verified=not any('event_' in x for x in reasons),
        event_evidence=evidence_events, invariant_evidence=evidence_invariants,
        declared_contract_coverage_complete=not unsupported,
        unsupported_predicates=sorted(set(unsupported)))
