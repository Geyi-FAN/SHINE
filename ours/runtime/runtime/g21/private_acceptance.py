"""Private current-contract acceptance using the unchanged independent scorer.

Never returns a plan or an object pose. Cheap predicates only schedule a full
check; only the frozen evaluator can accept. Past success is insufficient.
"""
from collections import deque


class CurrentContractAcceptance:
    version = 'current-contract-stop-v1'

    def __init__(self, case, contract, rules, initial, score, native_stop, stride=4):
        from benchmark_metrics.events import restore_radius
        from benchmark_metrics.predicates import drawer_gap
        self.case, self.contract, self.rules = case, contract, rules
        self.score, self.native_stop, self.stride = score, native_stop, stride
        self.subject = None
        self.last_check = -stride
        self.checks = 0
        self.last_score = None
        self.finished = False
        self.impossible = False
        self.restore = {}
        self.close = {}
        for clause in contract['clauses']:
            if clause['kind'] == 'restore_episode_start':
                length = max(rules['restore'][key] for key in
                             ('position_steps', 'support_steps', 'release_steps', 'stable_steps', 'withdraw_steps'))
                self.restore[clause['id']] = dict(clause=clause, radius=restore_radius(case, clause, rules),
                                                 rows=deque(maxlen=length), seen=False)
            if clause['kind'] == 'close_event':
                q = initial.get('articulation', {}).get(clause['joint'])
                self.close[clause['id']] = dict(clause=clause, streak=0,
                                               seen=q is not None and drawer_gap(q) <= rules['close']['gap_m'])

    @staticmethod
    def current_pass(score, row, contract):
        if score.get('final_release_evidence',{}).get('passed') is False:
            return False
        if row.get('adjusted_goal') is not True:
            return False
        instruction = score.get('instruction_adjusted', {})
        if instruction.get('success') is not True:
            return False
        for clause in contract['clauses']:
            cid, kind = clause['id'], clause['kind']
            if kind == 'native_target':
                continue  # Current native OR adjusted physical target is checked above.
            if kind == 'completion_order':
                if instruction.get('clauses_at_evaluation_step', {}).get(cid, {}).get('value') is not True:
                    return False
            elif score.get('components', {}).get(cid, {}).get('last_state') is not True:
                return False
        return True

    def _update_candidates(self, row):
        from benchmark_metrics.events import restore_window
        from benchmark_metrics.predicates import drawer_gap
        for entry in self.restore.values():
            entry['rows'].append(row['source'])
            if not entry['seen']:
                entry['seen'] = bool(restore_window(list(entry['rows']), entry['clause'],
                                                     entry['radius'], self.rules)['complete'])
        for entry in self.close.values():
            closed = drawer_gap(row['source']['articulation'][entry['clause']['joint']]) <= self.rules['close']['gap_m']
            entry['streak'] = entry['streak'] + 1 if closed else 0
            entry['seen'] |= entry['streak'] >= self.rules['close']['confirmation_steps']
        return all(e['seen'] for e in self.restore.values()) and all(e['seen'] for e in self.close.values())

    def observe(self, row, subject):
        if self.finished:
            return None
        if self.subject is None:
            self.subject = tuple(subject)
        if tuple(subject) != self.subject:
            return None  # A different task requires a newly bound contract.
        native_reason = self.native_stop.observe(row)
        possible = self._update_candidates(row)
        due = row['step'] - self.last_check >= self.stride
        if not native_reason and (not possible or row.get('adjusted_goal') is not True or not due or self.impossible):
            return None
        self.last_check = row['step']
        self.last_score = self.score()
        self.checks += 1
        accepted = self.current_pass(self.last_score, row, self.contract)
        # A raw native goal may become true while the object is still settling.
        # Its positive stop is only a candidate until the SAME v2.5 terminal
        # release/support/stability predicate holds. Permanent contract failures
        # and all existing outer action/wall budgets retain their old behavior.
        if (self.last_score.get('final_release_evidence',{}).get('passed') is False
                and self.last_score.get('instruction_adjusted',{}).get('success') is True
                and native_reason in('native_target_reached','target_and_trailing_close_completed')):
            native_reason=None
        if accepted or native_reason:
            self.finished = True
            return dict(schema=self.version, subject=list(self.subject), accepted=accepted,
                        reason='current_full_contract_accepted' if accepted else native_reason,
                        score_step=row['step'], world_physics_step=row.get('world_physics_step', row['step']),
                        native_goal=bool(row['goal_frame']['goal']), adjusted_goal=row.get('adjusted_goal'),
                        source='independent_frozen_v25_current_state_and_ordered_history')
        # Permanent order/high-release/preservation failures cannot be repaired by
        # later frames. Keep running the frozen native stop/budget, without O(N^2)
        # repeated full-prefix scoring during every subsequent holding tick.
        clauses = self.last_score.get('instruction_adjusted', {}).get('clauses_at_evaluation_step', {})
        for clause in self.contract['clauses']:
            value = clauses.get(clause['id'], {}).get('value')
            if clause['kind'] in ('preserve_position', 'preserve_articulation_state',
                                  'preserve_containment', 'preserve_predicate_state', 'preserve_relation') and value is False:
                self.impossible = True
            if clause['kind'] == 'completion_order' and value is False:
                before = next(c for c in self.contract['clauses'] if c['id'] == clause['before'])
                after = next(c for c in self.contract['clauses'] if c['id'] == clause['after'])
                after_seen = (row.get('adjusted_goal') is True if after['kind']=='native_target'
                              else self.last_score.get('completion_events',{}).get(after['id']) is not None)
                if before['kind'] in ('restore_episode_start', 'close_event') and after_seen:
                    self.impossible = True
        return None
