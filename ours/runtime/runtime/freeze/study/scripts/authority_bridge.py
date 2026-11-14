"""Published benchmark termination/scoring and pretrial snapshot fidelity.

All functions here run on the private evaluator side. No contract, GT pose,
next-stage answer, or shadow event becomes a planner input.
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / 'authority_src'


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, AUTHORITY / relative)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


extensions = load('metric_extensions', 'metric_extensions.py')
published = load('coverage_published_protocol', 'protocol.py')
state = load('coverage_published_sim_state', 'sim_state.py')


class BenchmarkTerminal:
    """StopController is authoritative; final target does not require Agent assent."""
    def __init__(self, case, contract, rules, initial):
        self.case, self.contract, self.rules, self.initial = case, contract, rules, initial
        self.controller = published.StopController(case, contract, rules)
        self.observed_rows = 0

    def check(self, measurements, decision):
        reason = None
        for row in measurements[self.observed_rows:]:
            reason = self.controller.observe(row) or reason
        self.observed_rows = len(measurements)
        result = dict(frame=measurements[-1]['step'] if measurements else 0,
                      final_agent_stage=reason is not None, stop=reason is not None, passed=False,
                      source='published_original_v25_StopController', benchmark_stop_reason=reason)
        if reason is not None:
            score = extensions.evaluate_episode(dict(measurements=measurements, metric_initial=self.initial),
                                                 self.case, self.contract, self.rules)
            result.update(instruction_adjusted=score['instruction_adjusted'],
                          passed=score['instruction_adjusted']['success'] is True)
        return result


def checked_restore(case, out):
    def restore(env, context):
        obs = state.restore(env, context)
        restored = state.capture(env)
        mismatches = []
        signed_zero = False
        for key in ('body_pos', 'body_quat', 'state'):
            expected = np.asarray(context[key])[1:] if key == 'state' else np.asarray(context[key])
            actual = np.asarray(restored[key])[1:] if key == 'state' else np.asarray(restored[key])
            a, b = np.round(actual, 8), np.round(expected, 8)
            if not np.array_equal(a, b):
                mismatches.append(dict(field=key, max_abs_error=float(np.max(np.abs(a-b)))))
            signed_zero |= bool(np.any((a == 0) & (b == 0) & (np.signbit(a) != np.signbit(b))))
        assert not mismatches, ('Frozen context not reproduced at original8-decimal precision', mismatches)
        raw_equal = state.identity(restored) == state.identity(context)
        assert raw_equal or signed_zero, 'A non-zero identity mismatch cannot use signed-zero normalization'
        resource = Path(case.get('authority_resource_root', ROOT / 'imported/benchmark_original'))
        from PIL import Image
        comparisons = {}
        for name, key in [('main', 'agentview_image'), ('wrist', 'robot0_eye_in_hand_image')]:
            actual = np.ascontiguousarray(obs[key][::-1, ::-1])
            image = resource / 'observations' / case['snapshot_id'] / ('smolvla_switch_256_' + name + '.png')
            expected = np.asarray(Image.open(image).convert('RGB'))
            delta = np.abs(actual.astype(np.int16) - expected.astype(np.int16))
            stats = dict(exact=bool(np.array_equal(actual, expected)), max_channel_error=int(delta.max()),
                         mean_channel_error=float(delta.mean()), changed_pixel_fraction=float(np.any(delta>0, axis=-1).mean()))
            # Exact published observation-boundary rule; no scoring tolerance changed.
            assert stats['max_channel_error'] <= 2 and stats['changed_pixel_fraction'] <= .001 and stats['mean_channel_error'] <= .001, (name, stats)
            comparisons[name] = stats
        (out / 'source_context_check.json').write_text(json.dumps(dict(
            method='frozen_complete_snapshot_before_any_model_action',
            raw_identity_matches=raw_equal, signed_zero_only_equivalence=not raw_equal and signed_zero,
            original8_decimal_values_equal=True, observations=comparisons,
            no_reset_or_state_writes_after_policy_start=True), ensure_ascii=False, indent=2) + '\n')
        return obs
    return restore


def install(runner, case, out, oracle=False):
    runner.SwitchTerminal = BenchmarkTerminal
    runner.evaluate_episode = extensions.evaluate_episode
    runner.metric_evidence = published.evidence
    runner.restore = checked_restore(case, out)
    runner.capture = state.capture
    runner.identity = state.identity
    if oracle:
        from bridge_execution.no_timeouts import ExecutionController
        runner.ExecutionController = ExecutionController
    else:
        import episode_history
        episode_history.restore = state.restore
        import oracle_review
        from bridge_execution.no_timeouts import ExecutionController
        oracle_review.ExecutionController = ExecutionController
