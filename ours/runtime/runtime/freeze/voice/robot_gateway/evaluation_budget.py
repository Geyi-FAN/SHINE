"""Opt-in independent rollout cap. Carries no task, stage or object labels."""
import json
from pathlib import Path


class EvaluationActionBudget:
    def __init__(self, marker):
        self.marker = Path(marker)
        self.episode = None
        self.consumed = 0
        self.limit = None

    def before_action(self, state):
        if self.episode is None and self.marker.exists():
            value = json.loads(self.marker.read_text())
            if value.get("episode_id") != state.episode or value.get("max_action_steps") != 1200:
                raise ValueError("invalid_independent_evaluation_budget")
            self.episode, self.limit = state.episode, 1200
            state.event("evaluation_budget_armed", dict(limit=self.limit, source="independent_rollout_evaluator"))
        if self.episode != state.episode:
            return
        if self.consumed >= self.limit and state.mode in ("running", "verifying"):
            state._hold("budget_exhausted", "independent_post_switch_1200_action_budget")
            state.event("evaluation_budget_exhausted", dict(consumed=self.consumed, limit=self.limit))

    def after_action(self, state, policy_action):
        if self.episode == state.episode and policy_action:
            self.consumed += 1
