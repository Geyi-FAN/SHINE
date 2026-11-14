"""Adapter for the frozen evaluator's action/measurement trace.

Unknown evidence stays unknown. In particular, native target false is not enough
information to reconstruct an expanded target region or drawer containment.
"""
from .predicates import distance

def policy_measurements(trace):
    frames = []; last = 0; hold_seen = False
    for m in trace['measurements']:
        phase = m.get('phase')
        if phase == 'hold': hold_seen = True; continue
        if phase != 'policy': raise ValueError('Missing/unsupported measurement phase')
        if hold_seen: raise ValueError('Policy measurements after hold phase')
        step = m['step']
        if step != last+1: raise ValueError('Policy steps must be contiguous and start at 1')
        last = step; frames.append(m)
    return frames

def restore_frames(measurements, obj, identity_tolerance):
    frames = []
    for m in measurements:
        source = m['source']
        for key in ('target_contact','support_contact'):
            if type(source[key]) is not bool: raise ValueError('Contact evidence must be boolean')
        if distance(source['object_position'],source['all_object_poses'][obj]['position']) > identity_tolerance:
            raise ValueError('Source monitor is not the restore object')
        frames.append(source)
    return frames

def region_for_frame(frame, site):
    # Optional enrichment produced by simulator-native site geometry extraction.
    return frame.get('metric_evidence', {}).get('regions', {}).get(site)

def containment(frame, clause_id):
    return frame.get('metric_evidence', {}).get('containment', {}).get(clause_id)
