"""Select one action producer per authorized task; keep the symbolic path lazy."""
import os
from pathlib import Path
import time
from native_execution import NativeExecution, native_candidate


class RoutedExecution:
    def __init__(self, env, memory, client, root, symbolic_factory=None, native_factory=None):
        self.env, self.memory, self.client = env, memory, client
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        if symbolic_factory is None:
            from unified_execution import UnifiedExecution
            symbolic_factory = UnifiedExecution
        self.symbolic_factory = symbolic_factory
        self.native_factory = native_factory or NativeExecution
        self.engine = None
        self.symbolic = None
        self.retired = []
        self.task_key = None
        self.episode = None
        self.seen_tasks = set()
        self.enabled = os.environ.get('VOICE_NATIVE_LIBERO_GOAL', '0') == '1'
        self.current_profile = 'symbolic'

    def _symbolic(self):
        if self.symbolic is None:
            self.symbolic = self.symbolic_factory(self.env, self.memory, self.client, self.root)
        return self.symbolic

    def _qa(self, state):
        reader = getattr(self.memory, 'reader', None)
        facts = getattr(reader, 'drawer_qa_facts', None)
        old = getattr(state, 'qa_drawers', {})
        if facts and (old.get('episode_id') != state.episode or time.time()-old.get('observed_at', 0) >= .2):
            state.qa_drawers = dict(source='simulator_physical_facts_v2.5', episode_id=state.episode,
                observed_step=state.step, observed_at=time.time(), drawers=facts())

    def tick(self, state, obs):
        self._qa(state)
        if self.episode != state.episode:
            if self.engine is not None:
                self.engine.invalidate(state)
                if self.engine is not self.symbolic:
                    self.engine.close()
                    self.retired.append(self.engine)
            self.engine = None
            self.episode = state.episode
            self.seen_tasks.clear()
            self.task_key = None
            state.execution_profile = 'symbolic'
            state.native_handoff_ready = True
            state.agent_execution = dict(phase='selected', execution_profile='symbolic')
        key = (state.episode, state.task_id)
        if state.task_id and key != self.task_key and state.mode == 'running':
            if self.engine is not None:
                self.engine.invalidate(state)
                if self.engine is not self.symbolic:
                    self.engine.close()
                    self.retired.append(self.engine)
            fresh = not self.seen_tasks
            self.seen_tasks.add(key)
            self.task_key = key
            reader = getattr(self.memory, 'reader', None)
            held = getattr(reader, 'snapshot', {}).get('held_object')
            skill, reason = native_candidate(state, fresh, held) if self.enabled else (None, 'feature_disabled')
            if skill:
                self.current_profile = 'native_libero_goal'
                self.engine = self.native_factory(self.env, self.memory, self.client, self.root, skill)
            else:
                self.current_profile = 'symbolic'
                self.engine = self._symbolic()
            state.execution_profile = self.current_profile
            state.native_handoff_ready = self.current_profile != 'native_libero_goal'
            if state.task_record is not None:
                state.task_record['execution_profile'] = self.current_profile
                state.task_record['native_skill_id'] = skill['skill_id'] if skill else None
            state.queue.clear()
            state.event('execution_profile_selected', dict(execution_profile=self.current_profile,
                reason=reason, canonical_task=skill['canonical_task'] if skill else None))
        if self.engine is not None:
            self.engine.tick(state, obs)

    def record_applied_action(self, state, policy_action):
        method = getattr(self.engine, 'record_applied_action', None)
        if method:
            method(state, policy_action)

    def invalidate(self, state):
        if self.engine:
            self.engine.invalidate(state)

    def select_backend(self, state, backend, episode, version, config_path):
        previous = state.version
        result = self._symbolic().select_backend(state, backend, episode, version, config_path)
        if state.version != previous and self.engine is not self.symbolic:
            self.invalidate(state)
        return result

    def close(self):
        if self.engine and self.engine is not self.symbolic:
            self.engine.close()
        if self.symbolic:
            self.symbolic.close()
