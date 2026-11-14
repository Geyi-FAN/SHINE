"""Complete trained LIBERO tasks, without an Agent plan or point dependencies."""
import concurrent.futures
import copy
import json
import os
from pathlib import Path
import re
import time
ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / 'configs/native_libero_goal.json').read_text())['entries']

def text_key(text):
    return re.sub('\\s+', ' ', str(text).strip().lower().rstrip('.!?。！？'))

def native_candidate(state, fresh_episode_task, held_object):
    """Post-authorization routing. No benchmark ID or correct answer is read."""
    if not fresh_episode_task or held_object != 'none':
        return (None, 'nonstandard_takeover_or_holding')
    if state.policy_metadata.get('executor') != 'pi05_e3_v4':
        return (None, 'different_model_profile')
    from instructions import normalize_instruction
    (normalized, _) = normalize_instruction(state.instruction)
    skill = next((s for s in CATALOG if text_key(s['canonical_task']) == text_key(normalized)), None)
    if skill is None:
        return (None, 'not_a_complete_native_task')
    record = state.task_record or {}
    candidate = record.get('candidate_contract') or {}
    intrinsic_pre = set(skill.get('intrinsic_preconditions', []))
    intrinsic_keep = set(skill.get('intrinsic_constraints', []))
    if set(record.get('preconditions', [])) - intrinsic_pre or set(candidate.get('preconditions', [])) - intrinsic_pre or set(record.get('persistent_constraints', [])) - intrinsic_keep or set(candidate.get('persistent_constraints', [])) - intrinsic_keep or record.get('reference_memory_ids') or state.deferred_task:
        return (None, 'extra_obligations_or_memory')
    evidence = record.get('clarification_evidence') or {}
    raw = evidence.get('resolved_instruction') if evidence.get('status') == 'resolved' else None
    raw = raw or record.get('user_utterance') or record.get('requested_instruction') or state.instruction
    if record.get('confirmed_proposal_id'):
        routing_raw = re.sub('(?:,\\s*|\\s+)(?:but\\s+)?ask\\s+(?:for\\s+(?:my|our)\\s+confirmation|me\\s+to\\s+confirm)\\s+before\\s+(?:starting|you\\s+start|execution|executing)\\s*[.!]?\\s*$', '', raw, flags=re.I)
        if routing_raw.strip():
            raw = routing_raw
    if re.search('\\b(?:keep|remain|without|unless|if|until|before|after|return|back|close|shut|not|never)\\b|\\bdon[’\\x27]t\\b|归位|放回|保持|不要|别动|如果|等.{0,8}(?:完成|结束)|关闭|关上', raw, re.I):
        return (None, 'raw_request_has_extra_or_negative_clause')
    if skill['task_id'] != 3 and re.search('\\b(?:then|next|also|afterwards)\\b|然后|接着|再去', raw, re.I):
        return (None, 'raw_request_has_additional_sequence')
    (raw_normalized, _) = normalize_instruction(raw)
    exact_raw = text_key(raw_normalized) == text_key(skill['canonical_task'])
    check = record.get('semantic_check') or candidate.get('semantic_check') or {}
    trusted_resolution = check.get('decision') == 'checked'
    if not exact_raw and (not trusted_resolution) and (not record.get('confirmed_proposal_id')):
        return (None, 'raw_request_not_resolved')
    if re.search('\\bball\\b', raw, re.I) and (not record.get('speech_correction_evidence')):
        return (None, 'unresolved_ball_bowl_conflict')
    return (copy.deepcopy(skill), 'complete_trained_task_in_standard_episode')

def identity(state):
    return (state.episode, state.task_id, state.version)

class NativeExecution:
    backend = 'NativeCompleteTask'

    def __init__(self, env, memory, client, root, skill, goal_reader=None):
        (self.env, self.memory, self.client) = (env, memory, client)
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.skill = copy.deepcopy(skill)
        self.goal_reader = goal_reader or self._read_goal
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        self.future = None
        self.orphans = []
        self.owner = None
        self.work_owner = None
        self.epoch = 0
        self.call = 0
        self.actions_seen = 0
        self.initially_satisfied = None
        self.target_latched = None
        self.receipt = None
        self.closed = False

    def log(self, kind, **values):
        with (self.root / 'execution.jsonl').open('a') as stream:
            stream.write(json.dumps(dict(time=time.time(), kind=kind, backend=self.backend, **values)) + '\n')

    def _read_goal(self):
        return all((bool(self.env.env._eval_predicate(p)) for p in self.skill['native_predicates']))

    def _goal(self):
        value = self.goal_reader()
        if not isinstance(value, bool):
            raise ValueError('Native goal predicate returned unknown evidence')
        return value

    def invalidate(self, state):
        if self.future is not None:
            self.future.cancel()
            self.orphans.append(self.future)
        self.future = None
        self.epoch += 1
        self.call = 0
        self.log('native_generation_invalidated', identity=list(identity(state)), generation=self.epoch)

    def _status(self, state, phase='executing'):
        state.execution_profile = 'native_libero_goal'
        state.agent_execution = dict(backend=self.backend, execution_profile='native_libero_goal', phase=phase, generation=self.epoch, complete_task=self.skill['canonical_task'], operation='native_task', subgoal=None, planner_called=False, target_latched=self.target_latched is not None)
        if self.receipt:
            state.agent_execution['completion_receipt'] = self.receipt

    def _handoff_ready(self):
        reader = getattr(self.memory, 'reader', None)
        facts = getattr(reader, 'snapshot', {})
        if facts.get('held_object') != 'none':
            return False
        obj = self.skill.get('object')
        if obj is None:
            return True
        item = facts.get('objects', {}).get(obj, {})
        return item.get('supported') is True and item.get('robot_contact') is False

    def _finish(self, state, already_satisfied=False):
        receipt = dict(status='verified', source='native_libero_goal_v2', episode_id=state.episode, task_id=state.task_id, native_task_id=self.skill['task_id'], native_goal_current=True, authorized_policy_actions=self.actions_seen, already_satisfied=already_satisfied, target_event=self.target_latched, terminal_hold_required=False, additional_release_required=False)
        self.receipt = receipt
        state._hold('completed', 'native_libero_goal_satisfied')
        self.invalidate(state)
        self._status(state, 'completed')
        state.completion_status = 'verified'
        state.latest_evidence = dict(native_goal=True, receipt=receipt)
        state.agent_execution.update(completion_current_verified=True, completion_receipt=receipt)
        state.native_handoff_ready = self._handoff_ready()
        state.event('task_completed', dict(instruction=state.instruction, evidence='native_libero_goal_v2', completion_receipt=receipt, planner_backend=self.backend))

    def _observe_target(self, state, policy_action):
        if state.mode != 'running' or identity(state) != self.owner:
            return
        current = self._goal()
        if not current or not self.actions_seen:
            return
        if self.target_latched is None:
            self.target_latched = dict(time=time.time(), frame=state.step, observed_on_policy_action=bool(policy_action), execution_version=state.version)
            self.log('native_target_latched', identity=list(self.owner), event=self.target_latched)
            state.event('native_target_reached', dict(skill_id=self.skill['skill_id'], canonical_task=self.skill['canonical_task'], **self.target_latched))
        state.native_handoff_ready = self._handoff_ready()
        if state.deferred_task and (not state.native_handoff_ready):
            self._status(state, 'handoff_settling')
            return
        self._finish(state)

    def record_applied_action(self, state, policy_action):
        if state.mode != 'running' or identity(state) != self.owner:
            return
        if policy_action:
            self.actions_seen += 1
            if self.actions_seen == 1:
                self.log('first_applied_action', identity=list(self.owner), frame=state.step)
        self._observe_target(state, policy_action)

    def _infer(self, observation, key, call, frame):
        import numpy as np
        from policy_backend import build_smol_inputs
        prompt = self.skill['canonical_task'].rstrip() + '\n'
        request = build_smol_inputs(observation, prompt, conditioning_mode='complete_task')
        request.update(evaluation_case_id=key, evaluation_call_index=call)
        if call == 0:
            request['evaluation_seed'] = 7
        recording = os.environ.get('VOICE_EVAL_RECORD_DIR')
        if recording:
            from PIL import Image
            folder = Path(recording) / 'policy_inputs' / key.replace('/', '_')
            folder.mkdir(parents=True, exist_ok=True)
            Image.fromarray(request['observation/image']).save(folder / f'{call:06d}.png')
        self.log('policy_started', task_key=key, call=call, frame=frame, prompt=prompt)
        began = time.monotonic()
        answer = self.client.infer(request)
        seconds = time.monotonic() - began
        self.log('policy_finished', task_key=key, call=call, frame=frame, seconds=seconds, server_seconds=answer.get('inference_seconds'))
        actions = np.asarray(answer['actions'], float)
        if actions.shape != (10, 7) or not np.isfinite(actions).all():
            raise ValueError('Invalid native action chunk')
        actions = np.clip(actions[:3], -1, 1)
        actions[:, 6] = np.where(actions[:, 6] > 0, 1.0, -1.0)
        return dict(actions=actions, seconds=seconds, prompt=prompt, frame=frame, observed_at=began, marker=dict(source='native_complete_task', valid=False, yx=None))

    def tick(self, state, obs):
        self.orphans = [f for f in self.orphans if not f.done()]
        current = identity(state)
        if self.owner != current:
            self.invalidate(state)
            self.owner = current
        if state.mode == 'completed' and state.completion_status == 'verified':
            self._status(state, 'completed')
            state.agent_execution['completion_current_verified'] = self._goal()
            state.native_handoff_ready = self._handoff_ready()
            if state.deferred_task and state.native_handoff_ready:
                state._run_deferred()
            return
        if state.mode != 'running':
            if self.future:
                self.invalidate(state)
            return
        if self.initially_satisfied is None:
            self.initially_satisfied = self._goal()
            self.log('native_task_started', identity=list(current), skill=self.skill, initially_satisfied=self.initially_satisfied, planner_called=False)
            if self.initially_satisfied:
                self._finish(state, already_satisfied=True)
                return
        self._status(state)
        self._observe_target(state, False)
        if state.mode != 'running':
            return
        if self.future is not None and self.future.done():
            future = self.future
            self.future = None
            if self.work_owner != (current, self.epoch):
                self.log('stale_result_discarded')
                return
            try:
                result = future.result()
            except Exception as error:
                state.failure_detail = dict(code='native_policy_error', detail=str(error)[:500], recovery='原生动作推理失败，已停止；请检查动作服务后明确重新执行。')
                state._hold('needs_review', 'native_policy_failure')
                state.event('task_needs_review', state.failure_detail)
                return
            self.log('policy_result', identity=list(current), prompt=result['prompt'], marker=result['marker'], frame=result['frame'])
            state.accept_actions(current[2], result['actions'], result['seconds'] * 1000, result['observed_at'])
        if self.future is not None or state.queue or len(self.orphans) >= 2:
            return
        key = ':'.join(map(str, (*current, 'native', self.epoch)))
        self.work_owner = (current, self.epoch)
        self.future = self.pool.submit(self._infer, copy.deepcopy(obs), key, self.call, state.step)
        self.call += 1

    def close(self):
        if not self.closed:
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.closed = True
