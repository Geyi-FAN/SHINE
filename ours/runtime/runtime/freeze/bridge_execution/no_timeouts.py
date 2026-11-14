"""Current continuation protocol: no per-stage timer or reserved target budget.

The v1 controller remains frozen for historical runs. We reuse its physical
observation and logging methods, but provide explicit no-timeout initialization
and progression. Final scoring failures are never execution prerequisites.
"""
import json
from collections import deque
from pathlib import Path
from benchmark_metrics.predicates import drawer_gap
from .controller import ExecutionController as FrozenV1PhysicalObserver

def load_execution_policy(path=None):
    path=Path(path) if path else Path(__file__).with_name('configs')/'continue_v2_no_timeouts.json'
    value=json.loads(path.read_text())
    for key in ['stage_max_steps','preparation_deadline_steps','target_reserved_steps']:
        if value.get(key) is not None:
            raise ValueError('No-timeout protocol cannot specify '+key)
    return value

class ExecutionController(FrozenV1PhysicalObserver):
    def __init__(self,case,contract,plan,rules,initial_articulation,initial_guards,budget,policy=None):
        self.case=case;self.contract=contract;self.plan=plan;self.rules=rules
        self.policy=policy or load_execution_policy();self.budget=budget
        for key in ['stage_max_steps','preparation_deadline_steps','target_reserved_steps']:
            if self.policy.get(key) is not None:raise ValueError('Execution timeouts disabled: '+key)
        self.preparation_deadline=None
        self.index=0;self.stage_enter_step=0;self.streak=0;self.entry=True
        self.transitions=[];self.physical_events={};self.close_streak={}
        self.window=deque(maxlen=max(rules['restore'][k] for k in ['position_steps','support_steps','release_steps','stable_steps','withdraw_steps'])+1)
        self.restore_clause=next((c for c in contract['clauses'] if c['kind']=='restore_episode_start'),None)
        self.close_clauses=[c for c in contract['clauses'] if c['kind']=='close_event']
        assert all(s['kind'] in {'return','close','open_top','grasp','target'} for s in plan['stages'])
        assert plan['stages'][-1]['kind'] in {'target','close'}, 'Only target or explicitly requested trailing close can be final'
        for c in self.close_clauses:
            if drawer_gap(initial_articulation[c['joint']])<=rules['close']['gap_m']:
                self.physical_events[c['id']]=0
        self._progress(initial_guards,0,initial=True)

    def _progress(self,guards,step,initial=False,high_release=False):
        while self.index<len(self.plan['stages'])-1:
            stage=self.plan['stages'][self.index];kind=stage['kind'];skip=False
            if kind=='return' and high_release:
                self._finish(step,'failed','HIGH_UNSUPPORTED_RELEASE');high_release=False;initial=True
                continue
            if kind in {'return','close'}:
                ready=('restore' if kind=='return' else 'close') in self.physical_events
            else:
                skip=bool((kind=='grasp' and guards[-3]) or (self.entry and guards[self.index]))
                if not initial:self.streak=self.streak+1 if guards[self.index] else 0
                ready=skip or self.streak>=stage['stable_frames']
            self.entry=False
            if ready:
                self._finish(step,'completed','PHYSICAL_READY',skip);initial=True
                continue
            # An unmet physical guard is not a confirmed failure. Keep the
            # current stage, exactly as before timeout policies were introduced.
            return
