"""Overlap Native inference, retain three-action commits and align by world frame.

This mixin does not decide task completion, route tasks, read benchmark labels,
or apply an action. The existing C3r Native subclass keeps its _finish override
and the Gateway remains the only env.step owner.
"""
import copy
import os
from pathlib import Path
import time


def identity(state):
    return state.episode, state.task_id, state.version


class NativePrefetchMixin:
    backend = 'NativeRealtimePrefetch'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bootstrap = True
        self.work_frame = None
        self.commits = 0

    def invalidate(self, state):
        super().invalidate(state)
        self.bootstrap = True
        self.work_frame = None

    def _reject(self, state, code, detail):
        state.failure_detail = dict(code=code, detail=detail,
            recovery='动作预测未及时衔接，已停止；请检查动作服务后明确重新执行。')
        state._hold('needs_review', code)
        self.invalidate(state)
        state.event('task_needs_review', state.failure_detail)

    def _infer(self, observation, key, call, frame):
        # Identical policy inputs / seed / normalization to NativeExecution.
        # Keep all ten predictions solely for choosing the time-aligned three.
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
        actions = np.asarray(answer['actions'], float)
        self.log('policy_finished', task_key=key, call=call, frame=frame,
                 seconds=seconds, server_seconds=answer.get('inference_seconds'))
        if actions.shape != (10, 7) or not np.isfinite(actions).all():
            raise ValueError('Invalid native action chunk')
        actions = np.clip(actions, -1, 1)
        actions[:, 6] = np.where(actions[:, 6] > 0, 1., -1.)
        return dict(actions=actions, seconds=seconds, prompt=prompt, frame=frame,
                    observed_at=began,
                    marker=dict(source='native_complete_task', valid=False, yx=None))

    def tick(self, state, obs):
        self.orphans = [f for f in self.orphans if not f.done()]
        current = identity(state)
        if self.owner != current:
            self.invalidate(state)
            self.owner = current
        if state.mode != 'running':
            super().tick(state, obs)
            return
        if self.initially_satisfied is None:
            self.initially_satisfied = self._goal()
            self.log('native_task_started', identity=list(current), skill=self.skill,
                     initially_satisfied=self.initially_satisfied,
                     planner_called=False, prefetch=True)
            if self.initially_satisfied:
                self._finish(state, already_satisfied=True)
                return
        self._status(state)
        self._observe_target(state, False)
        if state.mode != 'running':
            return
        if self.future is not None and self.future.done() and not state.queue:
            future = self.future
            self.future = None
            if self.work_owner != (current, self.epoch):
                self.log('stale_result_discarded')
                return
            try:
                result = future.result()
            except Exception as error:
                self._reject(state, 'native_policy_error', str(error)[:500])
                return
            elapsed = state.step - self.work_frame
            offset = 0 if self.bootstrap else elapsed
            if offset < 0 or offset + 3 > len(result['actions']):
                self.log('prediction_horizon_expired', frame=state.step,
                         request_frame=self.work_frame, offset=offset)
                self._reject(state, 'prediction_horizon_expired',
                             '推理返回时，10步预测已不足3步可用：' + str(offset))
                return
            selected = result['actions'][offset:offset + 3]
            self.log('policy_result', identity=list(current), prompt=result['prompt'],
                     marker=result['marker'], frame=result['frame'],
                     prefetch=True, aligned_offset=offset)
            accepted = state.accept_actions(current[2], selected,
                result['seconds'] * 1000, result['observed_at'])
            self.log('prefetch_commit', identity=list(current), frame=state.step,
                     request_frame=self.work_frame, elapsed_physics_steps=elapsed,
                     aligned_offset=offset, bootstrap=self.bootstrap,
                     accepted=accepted, action_count=len(selected),
                     actions=selected.tolist())
            if accepted:
                self.bootstrap = False
                self.commits += 1
            else:
                self.bootstrap = True
        if self.future is not None or len(self.orphans) >= 2:
            return
        key = ':'.join(map(str, (*current, 'prefetch', self.epoch)))
        self.work_owner = (current, self.epoch)
        self.work_frame = state.step
        self.log('prefetch_requested', identity=list(current), frame=state.step,
                 call=self.call, queued_actions=len(state.queue),
                 bootstrap=self.bootstrap)
        self.future = self.pool.submit(self._infer, copy.deepcopy(obs), key,
                                       self.call, state.step)
        self.call += 1
