"""Deterministic scheduling/identity regressions; no audio, GPU or robot calls."""
import ast
from collections import deque
from concurrent.futures import Future
import os
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import patch
import numpy as np

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
sys.path.insert(0, str(B/'freeze/voice/robot_gateway'))
from native_prefetch.scheduler import NativePrefetchMixin
from native_execution import NativeExecution


class Pool:
    def __init__(self): self.calls = []
    def submit(self, fn, *args):
        self.calls.append((fn, args))
        return Future()


class State:
    episode = 'e'; task_id = 't'; version = 1; mode = 'running'; step = 10
    def __init__(self):
        self.queue = deque(); self.accepted = []; self.events = []
    def accept_actions(self, version, actions, *args):
        assert version == self.version
        self.accepted.append(actions.copy()); self.queue.extend(actions.tolist())
        return True
    def _hold(self, mode, reason): self.mode = mode; self.queue.clear()
    def event(self, *args): self.events.append(args)


class Base:
    def __init__(self):
        self.future = None; self.orphans = []; self.owner = ('e','t',1)
        self.work_owner = (self.owner, 1); self.epoch = 1; self.call = 0
        self.initially_satisfied = False; self.pool = Pool(); self.logs = []
        self.skill = {'canonical_task': 'put the bowl on the stove'}
    def log(self, kind, **kw): self.logs.append((kind, kw))
    def invalidate(self, state):
        if self.future is not None:
            self.future.cancel(); self.orphans.append(self.future)
        self.future = None; self.epoch += 1; self.call = 0
    def _status(self, *args): pass
    def _observe_target(self, *args): pass
    def _goal(self): return False
    def tick(self, state, obs):
        if self.future is not None: self.invalidate(state)


class Scheduler(NativePrefetchMixin, Base):
    # The real C3r Native subclass owns this, never the scheduler.
    def _finish(self, state, **kw): self.logs.append(('terminal_candidate', {}))


def result():
    return dict(actions=np.repeat(np.arange(10)[:,None], 7, axis=1),
                seconds=.09, observed_at=1., prompt='same', marker={}, frame=10)


class SchedulingTests(unittest.TestCase):
    def setUp(self): self.s = State(); self.n = Scheduler()
    def ready(self, bootstrap=False, request_frame=10):
        self.n.bootstrap = bootstrap; self.n.work_frame = request_frame
        self.n.future = Future(); self.n.future.set_result(result())
    def test_requests_while_authorized_queue_is_nonempty(self):
        self.s.queue.extend([1,2,3]); self.n.tick(self.s, {})
        self.assertEqual(len(self.n.pool.calls), 1)
        self.assertEqual(list(self.s.queue), [1,2,3]); self.assertFalse(self.s.accepted)
    def test_bootstrap_four_actions_and_immediate_overlap(self):
        self.ready(True); self.s.step = 12; self.n.tick(self.s, {})
        np.testing.assert_array_equal(self.s.accepted[0][:,0], [0,1,2,3])
        self.assertEqual(len(self.n.pool.calls), 1); self.assertFalse(self.n.bootstrap)
    def test_later_commit_is_frame_aligned(self):
        self.ready(); self.s.step = 14; self.n.tick(self.s, {})
        np.testing.assert_array_equal(self.s.accepted[0][:,0], [4,5,6,7])
    def test_early_response_does_not_overwrite_queued_actions(self):
        self.ready(); self.s.queue.extend([1,2]); self.n.tick(self.s, {})
        self.assertFalse(self.s.accepted); self.assertTrue(self.n.future.done())
    def test_expired_horizon_stops_instead_of_replaying_old_actions(self):
        self.ready(); self.s.step = 17; self.n.tick(self.s, {})
        self.assertFalse(self.s.accepted); self.assertEqual(self.s.mode, 'needs_review')
        self.assertEqual(self.s.failure_detail['code'], 'prediction_horizon_expired')
    def test_stale_generation_never_commits(self):
        self.ready(); self.n.work_owner = (self.n.owner, 0); self.n.tick(self.s, {})
        self.assertFalse(self.s.accepted)
        self.assertIn('stale_result_discarded', [k for k,v in self.n.logs])
    def test_new_task_version_invalidates_pending_prediction(self):
        self.ready(); self.s.version = 2; self.n.tick(self.s, {})
        self.assertFalse(self.s.accepted); self.assertEqual(self.n.owner, ('e','t',2))
        self.assertTrue(self.n.bootstrap)
    def test_pause_cancels_pending_prediction(self):
        self.n.future = Future(); self.s.mode = 'paused'; self.n.tick(self.s, {})
        self.assertFalse(self.s.accepted); self.assertIsNone(self.n.future)
    def test_numeric_decode_and_prompt_match_native(self):
        raw = np.linspace(-1.2, 1.2, 70).reshape(10,7)
        requests = []
        self.n.client = types.SimpleNamespace(infer=lambda req: requests.append(req) or dict(actions=raw))
        module = types.ModuleType('policy_backend')
        module.build_smol_inputs = lambda obs,prompt: dict(observation=obs, prompt=prompt)
        with patch.dict(sys.modules, {'policy_backend':module}), patch.dict(os.environ, {}, clear=True):
            full = self.n._infer({'state':'same'}, 'e:t:1', 0, 10)
            old = NativeExecution._infer(self.n, {'state':'same'}, 'e:t:1', 0, 10)
        self.assertEqual(full['actions'].shape, (10,7))
        np.testing.assert_array_equal(full['actions'][:4], old['actions'])
        self.assertEqual(requests[0], requests[1]); self.assertEqual(requests[0]['evaluation_seed'], 7)
    def test_c3r_current_contract_finish_and_capture_time_are_unchanged(self):
        with patch.dict(os.environ, {'C3R_PROFILE':'recovery'}):
            parent = runpy.run_path(str(B/'c3r/gateway.py'), run_name='test_parent')['source']
            new = runpy.run_path(str(B/'native_prefetch/gateway.py'), run_name='test_new')['source']
        def method(src, name):
            nodes = [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef) and n.name=='Native']
            self.assertEqual(len(nodes), 1)
            return next(n for n in nodes[0].body if isinstance(n,ast.FunctionDef) and n.name==name)
        for name in ['_finish','_infer']:
            self.assertEqual(ast.dump(method(parent,name)), ast.dump(method(new,name)))
        compile(new, 'candidate_gateway', 'exec')
        self.assertEqual(new.count('install_completion(SingleOwnerBridge)'), 1)
        self.assertEqual(new.count('install_c3r(SingleOwnerBridge)'), 1)


if __name__ == '__main__': unittest.main()
