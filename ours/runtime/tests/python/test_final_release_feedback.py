"""Final-only feedback regression; no plan, pose or point is disclosed."""
import copy
import unittest
from types import SimpleNamespace
from benchmark_metrics.config import load_rules
from g21.private_acceptance import CurrentContractAcceptance
from unified.final_release import evidence

class FinalReleaseFeedback(unittest.TestCase):
    def bridge(self, frames=None, target=6, **flags):
        frame=dict(object_position=[0.,0.,.81],eef_position=[0.,0.,1.],target_contact=False,support_contact=True)
        if frames is None:frames=[copy.deepcopy(frame) for _ in range(5)]
        return SimpleNamespace(case=dict(target_task=target),cache_reader=SimpleNamespace(windows=dict(cheese=frames,bowl=frames)),rules=load_rules(),**flags)

    def test_native_goal_alone_without_release_cannot_accept(self):
        b=self.bridge();b.cache_reader.windows['cheese'][-1]['target_contact']=True
        self.assertFalse(evidence(b)['passed'])

    def test_unsupported_or_still_settling_cannot_accept(self):
        for failure in ['support','motion','short']:
            b=self.bridge();frames=b.cache_reader.windows['cheese']
            if failure=='support':frames[-1]['support_contact']=False
            elif failure=='motion':frames[0]['object_position'][0]=.02
            else:frames.pop()
            self.assertFalse(evidence(b)['passed'],failure)

    def test_existing_five_frame_window_four_support_votes_and_release(self):
        b=self.bridge();b.cache_reader.windows['cheese'][0]['support_contact']=False
        r=evidence(b);self.assertTrue(r['passed']);self.assertTrue(r['required'])
        self.assertFalse(r['position_or_point_disclosed'])
        self.assertNotIn('object_position',r)

    def test_missing_measurements_never_accept(self):
        self.assertFalse(evidence(self.bridge([]))['passed'])

    def test_nonplacement_and_explicit_open_close_return_keep_existing_gates(self):
        for b in [self.bridge(target=0),self.bridge(live_close_only='middle'),self.bridge(live_open_only='top'),self.bridge(return_only=True)]:
            r=evidence(b);self.assertTrue(r['passed']);self.assertFalse(r['required'])

    def controller(self, score, reason='native_target_reached'):
        return CurrentContractAcceptance({},dict(clauses=[dict(id='target',kind='native_target')]),{}, {},lambda:score,SimpleNamespace(observe=lambda row:reason))

    def test_positive_native_stop_pending_support_continues_then_accepts(self):
        score=dict(instruction_adjusted=dict(success=True),final_release_evidence=dict(passed=False))
        c=self.controller(score);row=dict(step=1,adjusted_goal=True,goal_frame=dict(goal=True))
        self.assertIsNone(c.observe(row,('episode','task',1)));self.assertFalse(c.finished)
        score['final_release_evidence']['passed']=True;row['step']=5
        self.assertTrue(c.observe(row,('episode','task',1))['accepted'])

    def test_permanent_instruction_failure_and_outer_budget_are_not_suppressed(self):
        score=dict(instruction_adjusted=dict(success=False),final_release_evidence=dict(passed=False))
        c=self.controller(score);row=dict(step=1,adjusted_goal=True,goal_frame=dict(goal=True))
        r=c.observe(row,('episode','task',1));self.assertFalse(r['accepted']);self.assertTrue(c.finished)
        score['instruction_adjusted']['success']=True;c=self.controller(score,reason='policy_budget_exhausted')
        self.assertFalse(c.observe(row,('episode','task',1))['accepted'])

    def test_wrong_task_cannot_reuse_ready_support(self):
        score=dict(instruction_adjusted=dict(success=True),final_release_evidence=dict(passed=True))
        c=self.controller(score);c.subject=('episode','old',1)
        self.assertIsNone(c.observe(dict(step=1,adjusted_goal=True,goal_frame=dict(goal=True)),('episode','new',1)))
        self.assertFalse(c.finished)
