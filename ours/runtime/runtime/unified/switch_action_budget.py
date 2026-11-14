"""Causal evaluator budget shared by old/new task, never a planning input."""
import json
from pathlib import Path


class SwitchActionBudget:
    def __init__(self, marker, log):
        self.marker=Path(marker)
        self.log=log
        self.episode=None
        self.limit=None
        self.consumed=0
        self.previous_control=None
        self.previous_policy=False
        self.marker_identity=None

    def before(self,state,control,policy):
        if self.episode is None and self.marker.exists():
            data=json.loads(self.marker.read_text())
            if data.get('episode_id')!=state.episode or data.get('max_action_steps')!=1200:
                raise ValueError('invalid_independent_evaluation_budget')
            start=data.get('start_control')
            if not isinstance(start,int) or isinstance(start,bool) or not 0<=start<=control:
                raise ValueError('invalid_independent_budget_start_control')
            self.episode=state.episode;self.limit=1200
            # At most the already completed owner interval since the marker was
            # written. This conservative causal count cannot grant extra actions.
            self.consumed=max(0,control-start)
            self.log('independent_switch_budget_armed',start_control=start,
                     consumed=self.consumed,limit=self.limit,source='label_free_evaluator_marker')
        if self.episode is not None and state.episode!=self.episode:
            raise ValueError('switch_budget_reused_across_episode')
        if policy and self.limit is not None and self.consumed>=self.limit:
            if state.mode in ('running','verifying'):
                state._hold('budget_exhausted','independent_post_switch_1200_action_budget')
            self.log('independent_switch_budget_exhausted',consumed=self.consumed,limit=self.limit)
            return False
        return True

    def after(self,policy):
        if self.limit is not None and policy:self.consumed+=1
