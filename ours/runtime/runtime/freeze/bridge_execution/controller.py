"""Physical progression that cannot be blocked by an Instruction failure.

No final scorer, score-controller events or Instruction status is accepted as
input. Execution outcomes never create benchmark completion events. Only the
saved physical trajectory determines Target/Instruction SR.
"""
from collections import deque
from benchmark_metrics.events import restore_radius,restore_window,high_releases
from benchmark_metrics.predicates import drawer_gap
from .config import load_execution_policy

class ExecutionController:
    def __init__(self,case,contract,plan,rules,initial_articulation,initial_guards,budget,policy=None):
        self.case=case;self.contract=contract;self.plan=plan;self.rules=rules
        self.policy=policy or load_execution_policy();self.budget=budget
        self.preparation_deadline=budget*self.policy['preparation_budget_numerator']//self.policy['preparation_budget_denominator']
        self.index=0;self.stage_enter_step=0;self.streak=0;self.entry=True
        self.transitions=[];self.physical_events={};self.close_streak={}
        self.window=deque(maxlen=max(rules['restore'][k] for k in ['position_steps','support_steps','release_steps','stable_steps','withdraw_steps'])+1)
        self.restore_clause=next((c for c in contract['clauses'] if c['kind']=='restore_episode_start'),None)
        self.close_clauses=[c for c in contract['clauses'] if c['kind']=='close_event']
        assert all(s['kind'] in {'return','close','open_top','grasp','target'} for s in plan['stages'])
        assert plan['stages'][-1]['kind']=='target'
        for c in self.close_clauses:
            if drawer_gap(initial_articulation[c['joint']])<=rules['close']['gap_m']:
                self.physical_events[c['id']]=0
        self._progress(initial_guards,0,initial=True)

    def _finish(self,step,outcome,reason,already_satisfied=False):
        stage=self.plan['stages'][self.index]
        self.transitions.append(dict(step=step,stage=self.index,kind=stage['kind'],outcome=outcome,
                                     reason=reason,already_satisfied=already_satisfied,
                                     entered_step=self.stage_enter_step,spent_steps=step-self.stage_enter_step,
                                     creates_scoring_success=False))
        self.index+=1;self.stage_enter_step=step;self.streak=0;self.entry=True

    def _progress(self,guards,step,initial=False,high_release=False):
        while self.index<len(self.plan['stages'])-1:
            stage=self.plan['stages'][self.index];kind=stage['kind'];skip=False
            if kind=='return' and high_release:
                self._finish(step,'failed','HIGH_UNSUPPORTED_RELEASE');high_release=False;initial=True
                continue
            if kind in {'return','close'}:
                event_id='restore' if kind=='return' else 'close'
                ready=event_id in self.physical_events
            else:
                skip=bool((kind=='grasp' and guards[-3]) or (self.entry and guards[self.index]))
                if not initial:self.streak=self.streak+1 if guards[self.index] else 0
                ready=skip or self.streak>=stage['stable_frames']
            self.entry=False
            if ready:
                self._finish(step,'completed','PHYSICAL_READY',skip);initial=True
                continue
            spent=step-self.stage_enter_step
            if step>=self.preparation_deadline:
                self._finish(step,'timeout' if spent else 'skipped','PREPARATION_BUDGET_EXHAUSTED');initial=True
                continue
            if spent>=self.policy['stage_max_steps'][kind]:
                self._finish(step,'timeout','STAGE_EXECUTION_TIMEOUT');initial=True
                continue
            return

    def observe(self,row,guards):
        step=row['step'];sm=row.get('source');drop=False
        if sm is not None:self.window.append(sm)
        if self.restore_clause is not None and sm is not None:
            c=self.restore_clause
            flags=restore_window(list(self.window),c,restore_radius(self.case,c,self.rules),self.rules)
            if flags['complete']:self.physical_events.setdefault(c['id'],step)
            if self.plan['stages'][self.index]['kind']=='return':
                drop=bool(high_releases(list(self.window)[-self.rules['restore']['high_release_confirmation_steps']-1:],c['reference_position'],self.rules))
        for c in self.close_clauses:
            if c['id'] in self.physical_events:continue
            ok=drawer_gap(sm['articulation'][c['joint']])<=self.rules['close']['gap_m']
            self.close_streak[c['id']]=self.close_streak.get(c['id'],0)+1 if ok else 0
            if self.close_streak[c['id']]>=self.rules['close']['confirmation_steps']:
                self.physical_events[c['id']]=step
        self._progress(guards,step,high_release=drop)

    @property
    def at_target(self):return self.plan['stages'][self.index]['kind']=='target'
