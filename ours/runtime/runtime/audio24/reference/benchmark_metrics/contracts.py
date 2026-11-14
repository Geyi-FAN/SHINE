"""Canonical case instruction contract; historical plan-only clauses are excluded."""
SUPPORTED = {'native_target','restore_episode_start','close_event','completion_order',
             'preserve_position','preserve_articulation_state','preserve_containment'}

def validate_contract(contract):
    clauses = contract['clauses']; ids = [c['id'] for c in clauses]
    if len(ids) != len(set(ids)): raise ValueError('Duplicate clause IDs')
    if sum(c['kind']=='native_target' for c in clauses) != 1: raise ValueError('Exactly one target required')
    events = {c['id'] for c in clauses if c['kind'] in {'native_target','restore_episode_start','close_event'}}
    for c in clauses:
        if not c.get('source','').startswith('case.instruction'):
            raise ValueError('Clause is not grounded in the canonical case instruction')
        if c['kind']=='completion_order' and (c['before'] not in events or c['after'] not in events):
            raise ValueError('Order references unknown completion event')
    # Unsupported kinds intentionally evaluated as unknown, never discarded.
