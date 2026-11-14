import sys, tempfile, unittest, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "robot_gateway"))
from core import RobotState, TaskError
from grounding import ENTITIES, inventory_from_names
from semantics import confirmation_answer


class ConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = RobotState(self.tmp.name)
        self.s.ready = True
        self.s.mode = "idle"
        self.s.scene_inventory = inventory_from_names(v[0] for v in ENTITIES.values())
        self.seq = 0

    def tearDown(self):
        self.s.db.close()
        self.tmp.cleanup()

    def call(self, name, **kwargs):
        self.seq += 1
        return self.s.command(
            name,
            {"episode_id": self.s.episode, "expected_task_version": self.s.version, **kwargs},
            str(self.seq),
        )

    def voice(self, name, text, **kwargs):
        return self.call(
            name,
            source="qwen_realtime_current_user",
            user_utterance=text,
            voice_input_id=f"input-{self.seq}",
            **kwargs,
        )

    def propose(self):
        r = self.voice(
            "robot_start_task", "请打开抽屉", instruction="open the middle drawer of the cabinet"
        )
        self.assertEqual(r["status"], "needs_confirmation")
        self.assertFalse(r["executed"])
        self.assertIsNone(self.s.task_id)
        return r["pending_proposal"]

    def test_delay_execution_until_confirmation_is_not_a_physical_negation(self):
        r = self.voice(
            "robot_propose_task", "先不要执行，先问我是否把碗放到盘子上",
            instruction="put the bowl on the plate",
        )
        self.assertEqual(r["status"], "needs_confirmation")
        self.assertIsNone(self.s.task_id)
        p = r["pending_proposal"]
        r = self.voice("robot_resolve_proposal", "确认执行",
                       proposal_id=p["proposal_id"], decision="confirm")
        self.assertEqual(r["status"], "accepted")

    def test_confirmation_does_not_remove_physical_prohibition(self):
        with self.assertRaisesRegex(TaskError, "semantic_constraint_lost|instruction_entity_mismatch"):
            self.voice("robot_propose_task",
                       "先不要执行，先问我是否把碗放到盘子上，不要动奶酪",
                       instruction="put the bowl on the plate")

    def test_do_not_execute_without_confirmation_context_is_not_permission(self):
        with self.assertRaisesRegex(TaskError, "semantic_constraint_lost"):
            self.voice("robot_start_task", "不要执行把碗放到盘子上",
                       instruction="put the bowl on the plate")

    def test_proposal_is_exact_and_only_new_yes_can_execute(self):
        p = self.propose()
        self.assertEqual(self.s.version, 0)
        with self.assertRaisesRegex(TaskError, "confirmation_requires_new"):
            self.call(
                "robot_resolve_proposal",
                proposal_id=p["proposal_id"],
                decision="confirm",
                source="qwen_realtime_current_user",
                user_utterance="好",
                voice_input_id=p["voice_input_id"],
            )
        r = self.voice(
            "robot_resolve_proposal", "好", proposal_id=p["proposal_id"], decision="confirm"
        )
        self.assertEqual(r["status"], "accepted")
        self.assertEqual(self.s.instruction, p["instruction"])
        self.assertIsNone(self.s.pending_proposal)
        self.assertEqual(self.s.task_record["confirmed_proposal_id"], p["proposal_id"])

    def test_bare_yes_cannot_start_without_proposal(self):
        for answer in ("好", "好的，确认执行。", "不用，算了。"):
            with self.assertRaisesRegex(TaskError, "speech_does_not_authorize"):
                self.voice("robot_start_task", answer, instruction="put the bowl on the plate")
        with self.assertRaisesRegex(TaskError, "unknown_or_expired"):
            self.voice("robot_resolve_proposal", "好", proposal_id="invented", decision="confirm")

    def test_rejection_and_wrong_answer_never_execute(self):
        p = self.propose()
        with self.assertRaisesRegex(TaskError, "explicit_answer"):
            self.voice(
                "robot_resolve_proposal", "谢谢", proposal_id=p["proposal_id"], decision="confirm"
            )
        r = self.voice(
            "robot_resolve_proposal", "不用", proposal_id=p["proposal_id"], decision="reject"
        )
        self.assertFalse(r["executed"])
        self.assertIsNone(self.s.pending_proposal)
        self.assertEqual(self.s.version, 0)

    def test_expiry_version_disconnect_and_new_input_invalidate(self):
        for invalidation in ("expiry", "version", "disconnect", "utterance"):
            p = self.propose()
            if invalidation == "expiry":
                self.s.pending_proposal["expires_at"] = time.time() - 1
            elif invalidation == "version":
                self.s._hold("paused", "test")
            elif invalidation == "disconnect":
                self.s.interrupt("voice_client_disconnected")
            else:
                self.s.record_interaction(
                    {"episode_id": self.s.episode, "input_id": "different", "text": "改成把奶酪放到碗里"}
                )
            with self.assertRaisesRegex(TaskError, "unknown_or_expired"):
                self.voice(
                    "robot_resolve_proposal", "好", proposal_id=p["proposal_id"], decision="confirm"
                )
            self.assertIsNone(self.s.task_id)

    def test_transcript_confirmation_is_only_a_bound_candidate_not_execution(self):
        p = self.propose()
        result = self.s.record_interaction(
            {
                "episode_id": self.s.episode,
                "task_version": self.s.version,
                "input_id": "fresh-answer",
                "text": "好的，确认执行。",
            }
        )
        self.assertEqual(
            result["confirmation"], {"proposal_id": p["proposal_id"], "decision": "confirm"}
        )
        self.assertIsNone(self.s.task_id)
        duplicate = self.s.record_interaction(
            {
                "episode_id": self.s.episode,
                "task_version": self.s.version,
                "input_id": "fresh-answer",
                "text": "好的，确认执行。",
            }
        )
        self.assertNotIn("confirmation", duplicate)

    def test_natural_spoken_confirmation_and_rejection(self):
        for text, decision in [
            ("嗯，确认执行吧。", "confirm"),
            ("可以执行。", "confirm"),
            ("开始执行。", "confirm"),
            ("就按这个执行。", "confirm"),
            ("嗯，不执行。", "reject"),
            ("先不要执行。", "reject"),
        ]:
            with self.subTest(text=text):
                p = self.voice(
                    "robot_propose_task",
                    "把碗放到盘子上，先问我确认再执行",
                    instruction="put the bowl on the plate",
                )["pending_proposal"]
                result = self.s.record_interaction(
                    {
                        "episode_id": self.s.episode,
                        "task_version": self.s.version,
                        "input_id": "answer-" + str(self.seq),
                        "text": text,
                    }
                )
                self.assertEqual(
                    result["confirmation"], {"proposal_id": p["proposal_id"], "decision": decision}
                )
                r = self.voice("robot_resolve_proposal", text, **result["confirmation"])
                self.assertEqual(
                    r["status"], "accepted" if decision == "confirm" else "proposal_rejected"
                )
                if decision == "confirm":
                    self.call("robot_cancel_task")

    def test_filler_keeps_proposal_without_authorizing_motion(self):
        p = self.propose()
        for i, text in enumerate(["嗯。", "呃，嗯。", "哦。"]):
            r = self.s.record_interaction(
                {
                    "episode_id": self.s.episode,
                    "task_version": self.s.version,
                    "input_id": "filler-" + str(i),
                    "text": text,
                }
            )
            self.assertNotIn("confirmation", r)
            self.assertEqual(self.s.pending_proposal["proposal_id"], p["proposal_id"])
            self.assertIsNone(self.s.task_id)

    def test_questions_quotes_mixed_commands_and_orphan_answers_do_not_confirm(self):
        for text in [
            "确认执行吗？",
            "可以执行？",
            "他说“确认执行”",
            "确认执行，但是先不要动",
            "不执行，改成打开抽屉",
            "如果可以执行",
            "嗯。",
        ]:
            self.assertIsNone(confirmation_answer(text), text)
        for text in ["开始执行。", "嗯，确认执行吧。", "不执行。"]:
            with self.assertRaisesRegex(TaskError, "speech_does_not_authorize"):
                self.voice("robot_start_task", text, instruction="put the bowl on the plate")

    def test_duplicate_confirmation_cannot_replay(self):
        p = self.propose()
        args = {
            "episode_id": self.s.episode,
            "expected_task_version": 0,
            "proposal_id": p["proposal_id"],
            "decision": "confirm",
        }
        r = self.s.command("robot_resolve_proposal", args, "same")
        version = self.s.version
        self.assertEqual(self.s.command("robot_resolve_proposal", args, "same"), r)
        self.assertEqual(self.s.version, version)

    def test_explicit_request_to_confirm_works_even_if_cloud_calls_start(self):
        r = self.voice(
            "robot_start_task",
            "把碗放到盘子里，先问我确认再执行",
            instruction="put the bowl on the plate",
        )
        self.assertEqual(r["status"], "needs_confirmation")

    def test_wait_for_my_confirmation_cannot_start_early(self):
        r = self.voice(
            "robot_start_task",
            "先准备把碗放到盘子上，等我确认。",
            instruction="put the bowl on the plate",
        )
        self.assertEqual(r["status"], "needs_confirmation")
        self.assertIsNone(self.s.task_id)

    def test_hard_errors_cannot_be_laundered_through_proposal(self):
        for text, inst in [
            ("把葡萄放到碗里", "put the cream cheese in the bowl"),
            ("不要关抽屉", "close the middle drawer"),
            (
                "先关上中间抽屉再把碗放到盘子上",
                "put the bowl on the plate, then close the middle drawer",
            ),
        ]:
            with self.assertRaises(TaskError):
                self.voice("robot_propose_task", text, instruction=inst)
            self.assertIsNone(self.s.pending_proposal)

    def test_complete_order_and_constraints_pass(self):
        r = self.voice(
            "robot_start_task",
            "先关上中间抽屉，再把碗放到盘子上",
            instruction="Close the middle drawer first, then put the bowl on the plate.",
        )
        self.assertEqual(r["status"], "accepted")
        self.assertEqual(self.s.task_record["semantic_check"]["decision"], "checked")

    def test_deferred_and_conditional_requests_do_not_switch_now(self):
        for text in ("等这个做完再把碗放到盘子上", "如果我让你把碗放到盘子上"):
            with self.assertRaises(TaskError):
                self.voice("robot_start_task", text, instruction="put the bowl on the plate")
            self.assertIsNone(self.s.task_id)

    def test_dropped_release_return_and_spatial_constraints_rejected(self):
        for text in ("把碗放回原位", "把碗放到盘子上并松手", "把碗放到左边的盘子上"):
            with self.assertRaises(TaskError):
                self.voice("robot_start_task", text, instruction="put the bowl on the plate")
