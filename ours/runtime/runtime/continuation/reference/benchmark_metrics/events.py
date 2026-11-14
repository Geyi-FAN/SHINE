"""Temporal components shared by offline evaluation and future online adapters."""
from .predicates import distance, drawer_gap, all_last, stable

def restore_radius(case, clause, rules):
    r = rules['restore']
    special = (case.get('source_task') == r['special_source_task'] and
               case.get('previous_instruction', '').strip().lower() == r['special_previous_instruction'] and
               clause['object'] == r['special_object'])
    return r['upper_drawer_bowl_radius_m'] if special else r['radius_m']

def restore_window(frames, clause, radius, rules):
    r = rules['restore']; ref = clause['reference_position']
    position = all_last([distance(f['object_position'],ref) <= radius for f in frames],r['position_steps'])
    support = frames[-r['support_steps']:]
    supported = (len(support) == r['support_steps'] and support[-1]['support_contact'] and
                 sum(f['support_contact'] for f in support) >= r['support_min_true'])
    released = all_last([not f['target_contact'] for f in frames],r['release_steps'])
    w = frames[-r['stable_steps']:]
    stationary = len(w) == r['stable_steps'] and stable([f['object_position'] for f in w],r['stable_diameter_m'])
    clear = all_last([not f['target_contact'] and distance(f['eef_position'],f['object_position']) >= r['withdraw_distance_m'] for f in frames],r['withdraw_steps'])
    placed = position and supported and released and (not clause['stable_required'] or stationary)
    return {'position':position, 'placement':placed, 'complete':placed and (not clause['withdraw_required'] or clear)}

def high_releases(frames, reference, rules):
    r = rules['restore']; n = r['high_release_confirmation_steps']; events = []
    for i in range(1,len(frames)-n+1):
        before, now = frames[i-1],frames[i]
        if (before['target_contact'] and all(not f['target_contact'] for f in frames[i:i+n]) and
            not before['support_contact'] and not now['support_contact'] and
            before['object_position'][2]-reference[2] > r['high_release_height_m']):
            events.append({'onset':i+1,'confirmation':i+n,'reason':'high_unsupported_release'})
    return events

def first_run(flags, count):
    streak = 0
    for i,flag in enumerate(flags):
        streak = streak + 1 if flag else 0
        if streak >= count: return i+1
    return None

def preservation_states(values, tolerance, severe, count):
    """None = pending/unknown, False = latched violation, True = valid."""
    streak = 0; violated = False; states = []; onset = None; unknown_history = False
    for i,value in enumerate(values):
        if value is None:
            unknown_history = True; streak = 0
            states.append(False if violated else None); continue
        streak = streak+1 if value>tolerance else 0
        if value>severe or streak>=count:
            if not violated: onset = i+1 if value>severe else i-count+2
            violated = True
        states.append(False if violated else None if unknown_history or streak else True)
    return states,onset

def close_event(qs, rules):
    c = rules['close']
    return first_run([drawer_gap(q)<=c['gap_m'] for q in qs],c['confirmation_steps'])
