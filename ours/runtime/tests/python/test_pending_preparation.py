"""Queue cancellation/replacement/late-result tests, with fake model transport."""

import copy
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from pending_preparation import install


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.episode = "e"
        self.task_id = "source"
        self.version = 1
        self.instruction = "old task"
        self.mode = "running"
        self.deferred_task = None
        self.dialogue_transactions = {}

    def command(self, name, slot=None):
        if name == "schedule":
            self.deferred_task = copy.deepcopy(slot)
            self.dialogue_transactions[slot["deferred_id"]] = {"revision": 1}
        elif name == "cancel":
            self.deferred_task = None
        elif name == "consume":
            self.task_id = "successor"
            self.instruction = self.deferred_task["instruction"]
            self.deferred_task = None
            self.version += 1
        return {"accepted": True}

    def _run_deferred(self):
        if self.deferred_task:
            self.command("consume")


class PendingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        template = Path(self.temp.name) / "wording.py"
        template.write_text(
            "def normalize(agent, raw, observed_context=None):\n"
            "    return request_json(raw)\n"
        )
        self.calls = []
        self.foreground = []
        self.logs = []
        self.state = State()
        self.bridge = types.SimpleNamespace(
            log=lambda kind, **kw: self.logs.append((kind, kw)),
            close=lambda: None,
            token=lambda: (
                self.state.episode,
                self.state.task_id,
                1,
                self.state.version,
            ),
        )

        def answer(raw):
            self.calls.append(raw)
            return dict(
                output=dict(
                    execution_task="put the cheese in the bowl", semantic_changes=[]
                )
            )

        def foreground(agent, raw, context=None):
            self.foreground.append(raw)
            return {"foreground": True}

        self.language = types.ModuleType("task_language")
        self.language.__file__ = str(template)
        self.language.normalize = foreground
        self.language.wording_errors = lambda raw, text: []
        fake = {
            "task_language": self.language,
            "text_transport": types.SimpleNamespace(
                request_json=answer,
                connection=lambda role: (
                    {"model": "test", "chat_url": "http://unused"},
                    "fake",
                ),
            ),
            "instructions": types.SimpleNamespace(
                normalize_instruction=lambda raw, previous: (raw, None)
            ),
            "t3repair": types.ModuleType("t3repair"),
            "t3repair.wording": types.SimpleNamespace(
                reused_task=lambda raw: dict(output=dict(execution_task=raw))
            ),
        }
        self.patcher = patch.dict(sys.modules, fake)
        self.patcher.start()
        install(self.bridge, self.state)

    def tearDown(self):
        self.bridge.close()
        self.patcher.stop()
        self.temp.cleanup()

    def schedule(self, identity="q"):
        self.state.command(
            "schedule",
            dict(
                episode_id="e",
                predecessor_task_id="source",
                deferred_id=identity,
                instruction="把奶酪放入碗中",
                candidate_utterance="把奶酪放入碗中",
                authorized_request_id=identity,
                voice_input_id="voice",
            ),
        )
        for entry in self.bridge.pending_preparation["entries"].values():
            entry["future"].result(timeout=1)

    def test_actual_consumption_binds_once_without_any_action(self):
        self.schedule()
        self.assertEqual(self.state.task_id, "source")
        self.state._run_deferred()
        value = self.language.normalize(None, self.state.instruction)
        self.assertEqual(value["prepared_for_deferred_id"], "q")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.foreground, [])

    def test_cancelled_preparation_cannot_bind(self):
        self.schedule()
        self.state.command("cancel")
        self.state._run_deferred()
        self.language.normalize(None, "把奶酪放入碗中")
        self.assertEqual(self.foreground, ["把奶酪放入碗中"])
        self.assertFalse(self.bridge.pending_preparation["bound"])

    def test_replacement_discards_old_queue_identity(self):
        self.schedule("q1")
        self.schedule("q2")
        self.state._run_deferred()
        value = self.language.normalize(None, self.state.instruction)
        self.assertEqual(value["prepared_for_deferred_id"], "q2")
        self.assertTrue(
            any(kind == "pending_preparation_invalidated" for kind, _ in self.logs)
        )

    def test_pause_new_version_or_observed_context_prevents_reuse(self):
        for change in ("pause", "version", "context", "task", "episode"):
            with self.subTest(change=change):
                self.schedule(change)
                self.state._run_deferred()
                original = (
                    self.state.mode,
                    self.state.version,
                    self.state.task_id,
                    self.state.episode,
                )
                context = None
                if change == "pause":
                    self.state.mode = "paused"
                elif change == "version":
                    self.state.version += 1
                elif change == "context":
                    context = {"bowl_location": "stove"}
                elif change == "task":
                    self.state.task_id = "foreign"
                else:
                    self.state.episode = "other"
                before = len(self.foreground)
                self.language.normalize(None, "把奶酪放入碗中", context)
                self.assertEqual(len(self.foreground), before + 1)
                (
                    self.state.mode,
                    self.state.version,
                    self.state.task_id,
                    self.state.episode,
                ) = original

    def test_english_preparation_does_not_override_foreground_permission(self):
        self.state.command(
            "schedule",
            dict(
                episode_id="e",
                predecessor_task_id="source",
                deferred_id="english",
                instruction="put the cheese in the bowl",
                candidate_utterance="put the cheese in the bowl",
                authorized_request_id="r",
                voice_input_id="v",
            ),
        )
        self.state._run_deferred()
        self.language.normalize(None, self.state.instruction)
        self.assertEqual(len(self.foreground), 1)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
