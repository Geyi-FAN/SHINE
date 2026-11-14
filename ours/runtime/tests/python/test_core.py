import sys
from pathlib import Path
import tempfile
import time
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "robot_gateway"))
from core import RobotState, TaskError


class TaskControlTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = RobotState(self.tmp.name)
        self.state.ready = True
        self.state.mode = "idle"
        self.seq = 0

    def tearDown(self):
        self.state.db.close()
        self.tmp.cleanup()

    def call(self, name, **kw):
        self.seq += 1
        return self.state.command(
            name,
            {"episode_id": self.state.episode, "expected_task_version": self.state.version, **kw},
            f"request-{self.seq}",
        )

    def test_stale_inference_is_discarded_after_revision(self):
        self.call("robot_start_task", instruction="open the middle drawer")
        old = self.state.version
        self.call("robot_revise_task", instruction="put the bowl on the plate")
        self.assertFalse(self.state.accept_actions(old, np.ones((3, 7)), 140, time.monotonic()))
        self.assertEqual(self.state.queue, [])
        self.assertEqual(self.state.stale_results_dropped, 1)

    def test_pause_clears_queue_and_preserves_gripper(self):
        self.call("robot_start_task", instruction="pick up the bowl")
        self.state.accept_actions(self.state.version, np.ones((3, 7)), 140, time.monotonic())
        self.state.next_action()
        self.call("robot_pause")
        self.assertIsNone(self.state.next_action())
        self.assertEqual(self.state.queue, [])
        self.assertEqual(self.state.last_gripper, 1.0)

    def test_repeated_request_is_idempotent(self):
        args = {
            "episode_id": self.state.episode,
            "expected_task_version": 0,
            "instruction": "open the drawer",
        }
        first = self.state.command("robot_start_task", args, "same-id")
        second = self.state.command("robot_start_task", args, "same-id")
        self.assertEqual(first, second)
        self.assertEqual(self.state.version, 1)
        with self.assertRaises(TaskError):
            self.state.command("robot_start_task", {**args, "instruction": "other task"}, "same-id")

    def test_stale_request_cannot_override_newer_task(self):
        self.call("robot_start_task", instruction="open the drawer")
        with self.assertRaisesRegex(TaskError, "stale_task_version"):
            self.state.command(
                "robot_revise_task",
                {
                    "episode_id": self.state.episode,
                    "expected_task_version": 0,
                    "instruction": "close drawer",
                },
                "late",
            )
        self.assertEqual(self.state.instruction, "open the drawer")

    def test_restore_recalls_intent_without_reset(self):
        self.state.reset_count = 1
        first = self.call("robot_start_task", instruction="open the middle drawer")
        self.call("robot_revise_task", instruction="put the bowl on the plate")
        self.call("robot_restore_task", memory_id=first["memory_id"])
        self.assertEqual(self.state.instruction, "open the middle drawer of the cabinet")
        self.assertEqual(self.state.reset_count, 1)
        self.assertEqual(
            len([x for x in self.state.memory() if x["kind"] == "task_instruction"]), 3
        )

    def test_new_episode_does_not_replay_old_memories(self):
        first = self.call("robot_start_task", instruction="open the drawer")
        other = RobotState(self.tmp.name)
        other.ready = True
        with self.assertRaises(TaskError):
            other.command(
                "robot_restore_task",
                {
                    "episode_id": other.episode,
                    "expected_task_version": 0,
                    "memory_id": first["memory_id"],
                },
                "new-restore",
            )
        self.assertFalse(any(x["kind"] == "task_instruction" for x in other.memory()))
        other.db.close()

    def test_cancelled_task_cannot_resume_silently(self):
        self.call("robot_start_task", instruction="open drawer")
        self.call("robot_cancel_task")
        with self.assertRaises(TaskError):
            self.call("robot_resume")
        with self.assertRaises(TaskError):
            self.call("robot_pause")

    def test_explicit_reset_starts_new_episode_and_rejects_old_actions(self):
        self.state.reset_count = 1
        first = self.call("robot_start_task", instruction="open drawer")
        old_episode, old_version = self.state.episode, self.state.version
        args = {"episode_id": old_episode, "expected_task_version": old_version}
        receipt = self.state.request_reset(args, "reset-1")
        self.assertEqual(self.state.mode, "resetting")
        self.assertFalse(self.state.ready)
        self.assertFalse(
            self.state.accept_actions(old_version, np.ones((3, 7)), 150, time.monotonic())
        )
        obs = {
            "robot0_eef_pos": np.zeros(3),
            "robot0_eef_quat": np.array([0.0, 0.0, 0.0, 1.0]),
            "robot0_gripper_qpos": np.zeros(2),
        }
        self.state.finish_reset(obs)
        self.assertNotEqual(self.state.episode, old_episode)
        self.assertEqual(self.state.reset_count, 2)
        self.assertEqual(self.state.mode, "idle")
        self.assertIsNone(self.state.task_id)
        self.assertEqual(self.state.instruction, "")
        self.assertFalse(any(e["kind"] == "task_instruction" for e in self.state.memory()))
        self.assertEqual(receipt, self.state.request_reset(args, "reset-1"))
        with self.assertRaisesRegex(TaskError, "stale_episode"):
            self.state.request_reset(args, "another-reset")
        with self.assertRaises(TaskError):
            self.call("robot_restore_task", memory_id=first["memory_id"])
        self.call("robot_start_task", instruction="put bowl on plate")
        self.assertFalse(
            self.state.accept_actions(old_version, np.ones((3, 7)), 150, time.monotonic())
        )

    def test_observation_timeout_does_not_execute_stale_actions(self):
        self.call("robot_start_task", instruction="open drawer")
        self.assertFalse(
            self.state.accept_actions(
                self.state.version, np.ones((3, 7)), 5000, time.monotonic() - 5
            )
        )

    def test_speech_hold_is_idempotent_while_paused(self):
        self.call("robot_start_task", instruction="open drawer")
        self.state.interrupt()
        version = self.state.version
        self.state.interrupt()
        self.assertEqual(self.state.version, version)


if __name__ == "__main__":
    unittest.main()
