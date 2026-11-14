"""Independent, versioned evaluator text fixes; never imported by a planner."""
import re

VERSION = 'audio-switch-t3-evidence-v1.3-textfix'


def normalize_sentence(text):
    return re.sub(r'\s+', ' ', text.strip().lower()).rstrip(' .!?;,:。！？；，：')


def restore_radius(case, clause, rules):
    r = rules['restore']
    special = (case.get('source_task') == r['special_source_task'] and
               normalize_sentence(case.get('previous_instruction', '')) == normalize_sentence(r['special_previous_instruction']) and
               clause['object'] == r['special_object'])
    return r['upper_drawer_bowl_radius_m'] if special else r['radius_m']


def install_runtime_radius(bridge):
    """Use the same sentence normalization in this NEW runtime's final judge."""
    import benchmark_metrics.events as events
    original = events.restore_radius
    events.restore_radius = restore_radius
    for module in (bridge.runner, bridge.authority.extensions, bridge.authority.published):
        if getattr(module, 'restore_radius', None) is original:
            module.restore_radius = restore_radius


def goal_from_full(text, instruction_goal):
    found = []
    clauses = re.split(r'[.;]|\bthen\b|\bfinally\b', text, flags=re.I)
    action_and = r'\band\s+(?=(?:please\s+)?(?:turn|switch|put|place|set|open|close|shut|push|slide|return|keep|leave)\b)'
    for clause in clauses:
        # Preserve the legacy combined open-top + "put the bowl inside" task:
        # its second clause may refer implicitly to the just-opened drawer.
        if not re.search(r"\b(?:do\s+not|don't|never|avoid|no\s+longer)\b", clause, re.I):
            whole = instruction_goal(clause)
            if whole is not None:
                found.append(whole)
        for part in re.split(action_and, clause, flags=re.I):
        # No positive goal is inferred from a negated clause. Splitting only at
        # action boundaries preserves "bowl and plate" and object names.
            if re.search(r"\b(?:do\s+not|don't|never|avoid|no\s+longer)\b", part, re.I):
                continue
            goal = instruction_goal(part)
            if goal is None and re.search(r'\b(?:put|place|set)\b.{0,30}\bbowl\b.{0,25}\b(?:in|into|inside)\b.{0,20}\b(?:top|upper)\b.{0,12}\bdrawer\b', part, re.I):
                goal = 3
            if goal is not None:
                found.append(goal)
    return found[-1] if found else None
