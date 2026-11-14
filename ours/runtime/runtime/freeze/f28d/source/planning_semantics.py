"""Explain supplied observation predicates; reject contradictions, never plan.

No simulator, case identity, reference answer, or benchmark contract is read.
Agent remains the sole author of stages and subgoal text.
"""
import copy
import re


ADDENDUM = '''
INDEPENDENT DRAWER PREDICATES:
"open" means the observed opening satisfies the OPEN operation's completion
criterion; it does NOT mean "not closed". "closed_current" is an independent
current closed criterion. "closed_confirmed" adds temporal confirmation.
Read both predicates. open=false AND closed_current=false means PARTIAL opening
or insufficient completion evidence, NEVER "already closed". A partially open
drawer can be closed directly; closing it is not a contradictory user request.
null is unavailable evidence. A clear request to close a drawer does not require
that it was previously fully open. Likewise, close=false does not mean fully open.
If a requested physical state is already reliably satisfied, do not demand that
the user change the request or re-enact its action; retain the requested order
and plan only what is still necessary. If evidence is genuinely unknown, ask for
observation rather than treating that missing observation as a contradictory goal.

PRESERVATION AND TIME WORDS:
"at its instruction-switch opening" means keep the drawer opening at the moment
the current instruction took over, INCLUDING zero opening (closed). It never
requests opening a drawer, and "instruction switch" is a TIME, not a stove
button or spatial destination. Keep/leave is a constraint, not another movement.
"put cheese in the bowl; keep the bowl at its current position" is compatible:
move the cheese, preserve the destination bowl. Do not ask to move the bowl or
place cheese beside it. An independently requested bowl move is different.
Do not invent a new operation solely to satisfy a preservation clause.

CLARIFICATION VERSUS OBSERVATION:
Use need_clarification for genuinely conflicting or underspecified USER goals.
Use need_observation for unresolved physical evidence. Clear user goals do not
become conflicting just because a goal predicate is false, partially satisfied,
or already true. Available current references authorize only their matching
operation; missing future points do not block a valid current operation.
These rules never authorize a return/release destination absent from the task,
never establish containment or ownership from user words, and never turn an
unconfirmed completion into an accepted event. You still write the entire plan.
'''


def explain(inp):
    result = copy.deepcopy(inp)
    meanings = {}
    for name, row in result['physical_state'].get('drawers', {}).items():
        opened, closed = row.get('open'), row.get('closed_current')
        if opened is True and closed is True:
            meaning = 'inconsistent_observations_need_observation'
        elif opened is True:
            meaning = 'open_goal_observed_satisfied'
        elif closed is True:
            meaning = 'closed_current_observed_satisfied'
        elif opened is False and closed is False:
            meaning = 'partial_or_neither_goal_confirmed_NOT_closed'
        else:
            meaning = 'unknown_do_not_invert_missing_predicates'
        meanings[name] = dict(open_predicate=opened, closed_predicate=closed,
            interpretation=meaning, source='logical reading of supplied independent S1 predicates; not new measurements')
    result['physical_state']['drawer_predicate_interpretation'] = meanings
    return result


def errors(inp, output):
    if not isinstance(output, dict):
        return []
    errors = []
    user = inp['user_message']
    words = str(output.get('request') or '') + ' ' + str(output.get('rationale') or '')
    if output.get('status') == 'hold':
        facts = inp['physical_state']
        completed = {e.get('operation') for e in inp.get('completed_events', []) if e.get('outcome') == 'completed'}
        # These recognizers validate explicit public goals; they never write a
        # plan, choose its order, or establish new completion evidence.
        patterns = {
            'turn_on_stove': r'\bturn\s+on\s+(?:the\s+)?stove\b',
            'push_plate': r'\bpush\s+(?:the\s+)?plate\b',
            'cheese_bowl': r'\b(?:put|place)\s+(?:the\s+)?(?:cream\s+)?cheese\s+(?:in|into)\s+(?:the\s+)?bowl\b',
            'bowl_stove': r'\b(?:put|place)\s+(?:the\s+)?bowl\s+(?:on|onto)\s+(?:the\s+)?stove\b',
            'bowl_plate': r'\b(?:put|place)\s+(?:the\s+)?bowl\s+(?:on|onto)\s+(?:the\s+)?plate\b',
            'bowl_cabinet': r'\b(?:put|place)\s+(?:the\s+)?bowl\s+on\s+(?:the\s+)?(?:top\s+of\s+the\s+)?cabinet\b',
            'bottle_cabinet': r'\b(?:put|place)\s+(?:the\s+)?(?:wine\s+)?bottle\s+on\s+(?:the\s+)?(?:top\s+of\s+the\s+)?cabinet\b',
            'bottle_rack': r'\b(?:put|place)\s+(?:the\s+)?(?:wine\s+)?bottle\s+(?:on|in|into)\s+(?:the\s+)?(?:wine\s+)?rack\b',
        }
        unproven = [op for op, pattern in patterns.items()
            if re.search(pattern, user, re.I) and op not in completed
            and facts.get('native_goal_relations', {}).get(op) is not True]
        for level in ['top', 'middle']:
            row = facts.get('drawers', {}).get(level, {})
            for verb, field in [('open', 'open'), ('close', 'closed_current')]:
                op = verb + '_' + level
                if (re.search(r'\b' + verb + r'\s+(?:the\s+)?' + level + r'\s+drawer\b', user, re.I)
                        and op not in completed and row.get(field) is not True):
                    unproven.append(op)
        if unproven:
            errors.append('UNPROVEN_ALL_DONE: You returned hold although explicit user goals have neither supplied true current predicates nor accepted completed events: '+', '.join(unproven)+'. False/unknown is not completion. Re-read the remaining request and generate your own plan or request concrete missing observations. This validator does not supply a next stage or assert task success.')
    if output.get('status') == 'need_clarification':
        for name, row in inp['physical_state'].get('drawers', {}).items():
            relevant = re.search(r'\b' + re.escape(name) + r'\b', words, re.I)
            if relevant and row.get('open') is False and row.get('closed_current') is False and re.search(r'\bclosed\b', words, re.I):
                errors.append('INDEPENDENT_PREDICATES: For '+name+' drawer, supplied open=false AND closed_current=false. Neither goal is confirmed; this is not affirmative closed. Re-read your claimed contradiction. A requested close can execute from a partial opening. Generate your own plan, or name a genuinely different missing observation; no completion is being supplied.')
        preserve = bool(re.search(r'instruction[- ]switch opening', user, re.I))
        if preserve and re.search(r'\bopening\b', words, re.I) and re.search(r'\b(?:closed|open)\b', words, re.I):
            errors.append('PRESERVATION_BASELINE: instruction-switch opening is the existing opening degree at takeover, including zero. The wording does not require open. Reconsider this alleged user contradiction using supplied state and any actual independent missing evidence. Do not invent an opening operation or a reference position.')
        bowl_stays = bool(re.search(r'\bkeep\s+the\s+bowl\s+at\s+its\s+(?:current\s+)?position', user, re.I))
        cheese_into_bowl = bool(re.search(r'(?:cheese|奶酪).*(?:in|into|入|里).*(?:bowl|碗)', user, re.I))
        if bowl_stays and cheese_into_bowl and re.search(r'contradict|conflict', words, re.I):
            errors.append('DESTINATION_PRESERVATION: Moving cheese into a bowl does not require moving that bowl. Preserving the bowl position is compatible with this placement. Reconsider your claimed conflict without adding bowl manipulation or a new cheese destination. Other genuinely missing evidence remains unknown.')
    return errors
