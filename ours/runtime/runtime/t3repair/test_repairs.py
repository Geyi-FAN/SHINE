import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import sys

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B/'freeze/f28d/source'))
sys.path.insert(0, str(B/'repair6/reference'))
from t3repair import stages, memory, scoring
from t3repair.terminal import CompletionGate

SUBJECT = ('ep', 'task', 1)
RULES = {'restore': dict(position_steps=1, support_steps=1, support_min_true=1,
                        release_steps=1, stable_steps=1, stable_diameter_m=.005,
                        withdraw_steps=1, withdraw_distance_m=.08)}


def row(step, goal=True, contact=False, supported=True):
    frame = dict(object_position=[0, 0, 0], eef_position=[0, 0, .1],
                 support_contact=supported, target_contact=contact)
    return dict(world_physics_step=step, simulation_time=step*.05,
                adjusted_goal=goal, source=frame, target=frame)


class TerminalTests(unittest.TestCase):
    def test_forty_new_frames_required(self):
        g = CompletionGate(SUBJECT, RULES)
        for i in range(1, 41):
            self.assertFalse(g.observe(row(i), SUBJECT, 1, full_contract=True))
        self.assertTrue(g.observe(row(41), SUBJECT, 1, full_contract=True))

    def test_repeated_snapshot_cannot_complete(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=2)
        for _ in range(100):
            self.assertFalse(g.observe(row(1), SUBJECT, 1, full_contract=True))
        self.assertEqual(g.hold_seen, 0)

    def test_old_task_frame_cannot_count(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=1)
        g.observe(row(1), SUBJECT, 1, full_contract=True)
        self.assertFalse(g.observe(row(2), ('ep', 'old', 1), 1, full_contract=True))
        self.assertEqual(g.hold_seen, 0)

    def test_noncausal_simulation_clock_rejected(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=1)
        g.observe(row(1), SUBJECT, 1, full_contract=True)
        r = row(2); r['simulation_time'] = .05
        self.assertFalse(g.observe(r, SUBJECT, 1, full_contract=True))

    def test_missing_clock_rejected(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=1)
        r = row(1); del r['world_physics_step']
        self.assertFalse(g.observe(r, SUBJECT, 1, full_contract=True))

    def test_gripper_contact_blocks_completion(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=1)
        for i in range(1, 8):
            self.assertFalse(g.observe(row(i, contact=True), SUBJECT, 1, full_contract=True))

    def test_no_support_blocks_completion(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=1)
        for i in range(1, 8):
            self.assertFalse(g.observe(row(i, supported=False), SUBJECT, 1, full_contract=True))

    def test_lost_goal_restarts_hold(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=2)
        g.observe(row(1), SUBJECT, 1, full_contract=True)
        g.observe(row(2), SUBJECT, 1, full_contract=True)
        g.observe(row(3, goal=False), SUBJECT, 1, full_contract=False)
        self.assertFalse(g.holding)
        self.assertFalse(g.observe(row(4), SUBJECT, 1, full_contract=True))
        self.assertFalse(g.observe(row(5), SUBJECT, 1, full_contract=True))
        self.assertTrue(g.observe(row(6), SUBJECT, 1, full_contract=True))

    def test_contract_failure_blocks_target_contact(self):
        g = CompletionGate(SUBJECT, RULES, hold_ticks=1)
        for i in range(1, 8):
            self.assertFalse(g.observe(row(i), SUBJECT, 1, full_contract=False))


STAGE = dict(operation='grasp_bowl', kind='grasp', object='bowl', goal='Grasp the bowl')


class StageTests(unittest.TestCase):
    def monitor(self):
        m = SimpleNamespace(active=None, entered=None, last=10, windows=[1, 2, 3], events=[])
        def select(s):
            if m.active: raise ValueError('Cannot replace unfinished stage')
            m.active = copy.deepcopy(s); m.entered = m.last
        m.select = select
        return stages.install_monitor(m, lambda *a, **k: None)

    def test_continue_preserves_windows_and_entered_step(self):
        m = self.monitor(); m.select(STAGE); m.last = 20
        m.select(dict(STAGE, goal='Pick up the bowl'))
        self.assertEqual(m.entered, 10); self.assertEqual(m.windows, [1, 2, 3]); self.assertEqual(m.events, [])

    def test_unfinished_different_operation_rejected(self):
        m = self.monitor(); m.select(STAGE)
        with self.assertRaises(ValueError): m.select(dict(STAGE, operation='return_bowl'))
        self.assertEqual(m.active, STAGE)

    def test_completed_operation_allows_next(self):
        m = self.monitor(); m.select(STAGE); m.active = None
        m.events.append(dict(operation='grasp_bowl', outcome='completed'))
        m.last = 20; m.select(dict(STAGE, operation='return_bowl'))
        self.assertEqual(m.entered, 20)

    def test_guard_rejects_jump_and_accepts_continue(self):
        inp = dict(physical_state=dict(active_execution_stage=STAGE))
        self.assertFalse(stages.errors(inp, dict(status='plan_ready', remaining_plan=[STAGE])))
        self.assertTrue(stages.errors(inp, dict(status='plan_ready', remaining_plan=[dict(STAGE, operation='return_bowl')])))

    def test_observation_does_not_authorize_replacement(self):
        self.assertFalse(stages.errors(dict(physical_state=dict(active_execution_stage=STAGE)), dict(status='need_observation')))

    def test_input_keeps_eight_top_level_fields(self):
        inp = dict(user_message='put', physical_state={}, completed_events=[], reference_availability=[], episode_id='e', task_version=1, frame=10, mode='s1')
        new = stages.input_with_stage(inp, SimpleNamespace(active=STAGE, entered=8, last=10))
        self.assertEqual(set(new), set(inp)); self.assertNotIn('active_execution_stage', inp['physical_state'])

    def test_existing_exact_completion_retires_stale_pointer(self):
        m=self.monitor();m.select(STAGE);m.last=20
        m.events=[dict(operation='grasp_bowl',object='bowl',outcome='completed',entered_step=10,confirmed_step=18)]
        m.select(dict(STAGE,operation='return_bowl'))
        self.assertEqual(m.active['operation'],'return_bowl');self.assertEqual(len(m.events),1)

    def test_old_repeated_operation_event_cannot_retire_current(self):
        m=self.monitor();m.select(STAGE);m.last=20
        m.events=[dict(operation='grasp_bowl',object='bowl',outcome='completed',entered_step=2,confirmed_step=9)]
        self.assertFalse(stages.reconcile_monitor(m,lambda *a,**k:None));self.assertIsNotNone(m.active)


class MemoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): memory.install()

    def setUp(self):
        from scene_memory import SceneMemory
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.m = SceneMemory(Path(self.tmp.name)/'events.jsonl', episode_id='e')
        self.pose = [0, 0, 0, 1, 0, 0, 0, .16]

    def point(self, entity='top_drawer_interior', k='K3', xy=None):
        return dict(entity=entity, keypoint=k, yx224=xy or [100, 110], det_confidence=.8, keypoint_confidence=.9)

    def facts(self, delta=0, static=True):
        pose = self.pose.copy(); pose[-1] += delta
        return {'top_drawer_interior': dict(static=static, pose=pose)}

    def seed(self):
        self.m.evidence(1, self.facts(), 'c'); self.m.ingest([self.point()], 1)

    def test_small_drawer_jitter_retains_cache(self):
        self.seed(); self.m.evidence(2, self.facts(delta=.0005), 'c'); self.m.ingest([], 2)
        self.assertEqual(self.m.resolve('top_drawer_interior', 'K3')[1], 'cached')

    def test_drawer_motion_invalidates(self):
        self.seed(); self.m.evidence(2, self.facts(delta=.006), 'c')
        self.assertIsNone(self.m.resolve('top_drawer_interior', 'K3')[0])

    def test_closed_drawer_invalidates(self):
        self.seed(); self.m.evidence(2, self.facts(static=False), 'c')
        self.assertIsNone(self.m.resolve('top_drawer_interior', 'K3')[0])

    def test_fresh_preferred_over_anchor(self):
        self.seed(); self.m.evidence(2, self.facts(), 'c'); self.m.ingest([self.point(xy=[101, 111])], 2)
        p, status = self.m.resolve('top_drawer_interior', 'K3')
        self.assertEqual(status, 'fresh'); self.assertEqual(p['frame'], 2)

    def test_camera_change_invalidates(self):
        self.seed(); self.m.evidence(2, self.facts(), 'other')
        self.assertIsNone(self.m.resolve('top_drawer_interior', 'K3')[0])

    def test_no_cross_k_fallback(self):
        self.seed(); self.assertIsNone(self.m.resolve('top_drawer_interior', 'K1')[0])

    def test_anchor_pixel_jump_rejected(self):
        self.seed(); self.m.evidence(2, self.facts(), 'c'); self.m.ingest([self.point(xy=[180, 180])], 2)
        p, status = self.m.resolve('top_drawer_interior', 'K3')
        self.assertEqual(status, 'cached'); self.assertEqual(p['yx224'], [100, 110])

    def test_object_movement_invalidates(self):
        p = [0, 0, 0, 1, 0, 0, 0]
        self.m.evidence(1, {'bowl':dict(static=True, cache_reusable=True, pose=p)}, 'c')
        self.m.ingest([self.point('bowl', 'K1')], 1)
        p2 = p.copy(); p2[0] = .006
        self.m.evidence(2, {'bowl':dict(static=True, cache_reusable=True, pose=p2)}, 'c')
        self.assertIsNone(self.m.resolve('bowl', 'K1')[0])

    def test_low_confidence_not_cached(self):
        self.m.evidence(1, self.facts(), 'c'); p = self.point(); p['det_confidence'] = .09
        self.m.ingest([p], 1); self.assertIsNone(self.m.resolve('top_drawer_interior', 'K3')[0])


class ScoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, '/mnt/disk_2/geyi/audio_t3_f28d90_20261101/scoring')
        from t1_contract import instruction_goal
        cls.parse = staticmethod(instruction_goal)

    def test_compound_and_final_stove(self):
        self.assertEqual(scoring.goal_from_full('Return the bowl to its episode-start position, release it stably, then close the top drawer, and turn on the stove.', self.parse), 7)

    def test_negated_stove_not_counted(self):
        self.assertIsNone(scoring.goal_from_full('Do not turn on the stove.', self.parse))

    def test_negative_clause_keeps_actual_goal(self):
        self.assertEqual(scoring.goal_from_full('Put the bowl on the stove; do not turn on the stove.', self.parse), 1)

    def test_open_and_place_top_drawer(self):
        self.assertEqual(scoring.goal_from_full('Open the top drawer and put the bowl inside the top drawer.', self.parse), 3)

    def test_open_and_place_implicit_same_drawer(self):
        self.assertEqual(scoring.goal_from_full('Open the top drawer and put the bowl inside. Keep the plate at its position.', self.parse), 3)

    def test_combined_then_later_goal_is_last(self):
        self.assertEqual(scoring.goal_from_full('Open the top drawer and put the bowl inside and turn on the stove.', self.parse), 7)

    def test_unrequested_return_not_added(self):
        self.assertEqual(scoring.goal_from_full('Put the cream cheese in the bowl.', self.parse), 6)

    def test_radius_punctuation_equivalent(self):
        r = {'restore':dict(special_source_task=3, special_previous_instruction='open the top drawer and put the bowl inside', special_object='bowl', upper_drawer_bowl_radius_m=.07, radius_m=.035)}
        for text in ['open the top drawer and put the bowl inside', 'Open the top drawer and put the bowl inside.', ' open the top drawer and put the bowl inside! ']:
            self.assertEqual(scoring.restore_radius(dict(source_task=3, previous_instruction=text), dict(object='bowl'), r), .07)

    def test_radius_different_task_does_not_match(self):
        r = {'restore':dict(special_source_task=3, special_previous_instruction='open the top drawer and put the bowl inside', special_object='bowl', upper_drawer_bowl_radius_m=.07, radius_m=.035)}
        self.assertEqual(scoring.restore_radius(dict(source_task=0, previous_instruction=r['restore']['special_previous_instruction']), dict(object='bowl'), r), .035)


if __name__ == '__main__': unittest.main()
