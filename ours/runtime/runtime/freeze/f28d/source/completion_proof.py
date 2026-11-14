"""Shared evidence at a completed drawer event, not a second acceptance vote."""
import copy


def build_drawer_proof(event, recent_verifier_calls, s1_candidate):
    operation = event.get('operation', '')
    if operation not in ('open_top', 'open_middle', 'close_top', 'close_middle'):
        return None
    accepted = [item for item in recent_verifier_calls
                if item.get('operation') == operation and item.get('entered') == event.get('entered_step')
                and item.get('accepted') is True and item.get('schema_valid') is True
                and item.get('physical_guard') is True and item.get('temporal_evidence') is True
                and item.get('frame', -1) <= event['confirmed_step']]
    # Use the evidence that ACTUALLY authorized the commit, not unrelated old
    # positive answers separated by a later negative one.
    suffix = []
    for item in reversed(recent_verifier_calls):
        if item.get('operation') != operation or item.get('entered') != event.get('entered_step'):
            continue
        if item not in accepted:
            break
        suffix.append(item)
        if len(suffix) == 2:
            break
    suffix.reverse()
    if not suffix or (not s1_candidate and (len(suffix) < 2 or suffix[-1]['frame'] - suffix[0]['frame'] < 6)):
        return None
    if suffix[-1]['frame'] != event['confirmed_step']:
        return None
    if operation.startswith('close_'):
        if not all(item.get('independent_drawer_guard', {}).get('passed') is True for item in suffix):
            return None
    frames = sorted({frame for item in suffix for check in item.get('response', {}).get('checks', [])
                     for frame in check.get('evidence_frames', []) if isinstance(frame, int) and 0 <= frame <= event['confirmed_step']})
    if not frames:
        return None
    return dict(schema='accepted_drawer_completion_proof_v1', operation=operation,
                entered_step=event['entered_step'], confirmed_step=event['confirmed_step'],
                evidence_frames=frames, accepted_verifier_frames=[item['frame'] for item in suffix],
                s1_joint_candidate=bool(s1_candidate), existing_hard_guards_passed=True,
                independent_close_geometry_passed=operation.startswith('close_'),
                source='same validated evidence that committed the online event; no simulator object/joint truth')


def valid_drawer_proof(event):
    proof = event.get('completion_proof') or {}
    if proof.get('schema') != 'accepted_drawer_completion_proof_v1':
        return False
    if any(proof.get(key) != event.get(key) for key in ('operation', 'entered_step', 'confirmed_step')):
        return False
    if proof.get('existing_hard_guards_passed') is not True:
        return False
    calls = proof.get('accepted_verifier_frames') or []
    if not calls or calls[-1] != event['confirmed_step']:
        return False
    if not proof.get('s1_joint_candidate') and (len(calls) < 2 or calls[-1] - calls[-2] < 6):
        return False
    if event['operation'].startswith('close_') and proof.get('independent_close_geometry_passed') is not True:
        return False
    frames = proof.get('evidence_frames') or []
    return bool(frames) and all(isinstance(frame, int) and 0 <= frame <= event['confirmed_step'] for frame in frames)
