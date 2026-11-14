import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "robot_gateway"))
from core import RobotState, TaskError
from priority_stop import PriorityStop
from grounding import ENTITIES, inventory_from_names


class PriorityStopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = RobotState(self.tmp.name)
        self.state.ready = True
        self.state.mode = "idle"
        self.state.scene_inventory = inventory_from_names(v[0] for v in ENTITIES.values())
        self.state.command("robot_start_task", self.args(instruction="open the middle drawer"), "start")

    def tearDown(self):
        self.state.db.close()
        self.tmp.cleanup()

    def args(self, **extra):
        return dict(episode_id=self.state.episode, expected_task_version=self.state.version, **extra)

    def test_receipt_waits_for_actual_pause_and_old_actions_are_discarded(self):
        old = self.state.version
        self.state.last_gripper = 1.0
        self.state.accept_actions(old, np.ones((3, 7)), 10, time.monotonic())
        q = PriorityStop()
        item = q.submit(self.args(source="qwen_realtime_current_user", user_utterance="Stop."), "pause")
        self.assertEqual(self.state.mode, "running")
        self.assertFalse(item.event.is_set())
        q.drain(self.state.command)
        receipt = q.wait(item)
        self.assertEqual(receipt["state"], "paused")
        self.assertEqual(self.state.last_gripper, 1.0)
        self.assertEqual(self.state.queue, [])
        self.assertFalse(self.state.accept_actions(old, np.ones((2, 7)), 10, time.monotonic()))

    def test_admission_does_not_wait_on_simulator_lock(self):
        q = PriorityStop()
        admitted = threading.Event()
        args = self.args()
        with self.state.lock:
            t = threading.Thread(target=lambda: (q.submit(args, "pause"), admitted.set()))
            t.start()
            self.assertTrue(admitted.wait(0.5))
        t.join()

    def test_stale_version_and_negative_speech_still_rejected(self):
        for args in [self.args(expected_task_version_bad=True),
                     self.args(source="qwen_realtime_current_user", user_utterance="Don't stop.")]:
            if args.pop("expected_task_version_bad", None):
                args["expected_task_version"] -= 1
            q = PriorityStop()
            item = q.submit(args, "rejected-" + str(args))
            q.drain(self.state.command)
            with self.assertRaises(TaskError):
                q.wait(item)
            self.assertEqual(self.state.mode, "running")

    def test_expired_or_cancelled_pause_never_executes_later(self):
        now = [0.0]
        q = PriorityStop(clock=lambda: now[0], lifetime=1)
        item = q.submit(self.args(), "old")
        now[0] = 2
        q.drain(self.state.command)
        with self.assertRaisesRegex(ValueError, "expired"):
            q.wait(item)
        self.assertEqual(self.state.mode, "running")

    def test_duplicate_request_keeps_single_version_change(self):
        q = PriorityStop()
        args = self.args()
        a, b = q.submit(args, "same"), q.submit(args, "same")
        q.drain(self.state.command)
        self.assertEqual(q.wait(a), q.wait(b))
        self.assertEqual(self.state.version, args["expected_task_version"] + 1)

    def test_direct_pause_invalidates_proposal_and_waiting_without_transcript_prewrite(self):
        self.state.command("robot_schedule_task", self.args(instruction="put the bowl on the plate", source="qwen_realtime_current_user", user_utterance="After the current task is completed, put the bowl on the plate."), "schedule")
        self.state.command("robot_propose_task", self.args(instruction="put the bowl on the plate", source="qwen_realtime_current_user", user_utterance="先不要执行，先问我是否把碗放到盘子上"), "propose")
        self.assertIsNotNone(self.state.deferred_task)
        self.assertIsNotNone(self.state.pending_proposal)
        q = PriorityStop()
        item = q.submit(self.args(source="qwen_realtime_current_user", user_utterance="Stop."), "direct")
        q.drain(self.state.command)
        self.assertEqual(q.wait(item)["state"], "paused")
        self.assertIsNone(self.state.pending_proposal)
        self.assertIsNone(self.state.deferred_task)

    def test_bounded_queue(self):
        q = PriorityStop(capacity=1)
        q.submit(self.args(), "one")
        with self.assertRaisesRegex(ValueError, "queue_full"):
            q.submit(self.args(), "two")


if __name__ == "__main__":
    unittest.main()
