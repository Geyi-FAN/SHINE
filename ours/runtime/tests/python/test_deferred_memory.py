import sys, tempfile, unittest, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "robot_gateway"))
from core import RobotState, TaskError
from grounding import ENTITIES, inventory_from_names
from temporal_memory import select_tasks


class DeferredTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = RobotState(self.tmp.name)
        self.s.ready = True
        self.s.mode = "idle"
        self.seq = 0
        self.s.scene_inventory = inventory_from_names(v[0] for v in ENTITIES.values())

    def tearDown(self):
        self.s.db.close()
        self.tmp.cleanup()

    def call(self, name, **args):
        self.seq += 1
        return self.s.command(
            name,
            {"episode_id": self.s.episode, "expected_task_version": self.s.version, **args},
            str(self.seq),
        )

    def start(self):
        return self.call(
            "robot_revise_task" if self.s.task_id else "robot_start_task",
            instruction="open the middle drawer of the cabinet",
        )

    def queue(self, **args):
        return self.call(
            "robot_schedule_task",
            instruction="put the bowl on the plate",
            source="qwen_realtime_current_user",
            user_utterance="等这个任务完成后再把碗放到盘子上",
            **args,
        )

    def complete(self):
        for _ in range(10):
            self.s.observe_completion({"goal:0": True})

    def test_waits_for_stable_completion_and_consumes_once(self):
        self.start()
        version = self.s.version
        old = self.s.task_id
        r = self.queue()
        self.assertEqual(r["status"], "scheduled")
        self.assertEqual(self.s.task_id, old)
        self.assertEqual(self.s.version, version)
        for _ in range(9):
            self.s.observe_completion({"goal:0": True})
        self.assertEqual(self.s.task_id, old)
        self.s.observe_completion({"goal:0": True})
        self.assertEqual(self.s.instruction, "put the bowl on the plate")
        self.assertNotEqual(self.s.task_id, old)
        self.assertIsNone(self.s.deferred_task)
        version = self.s.version
        for _ in range(20):
            self.s.observe_completion({"goal:0": True})
        self.assertEqual(self.s.version, version)
        self.assertEqual(
            sum(e["kind"] == "deferred_started" for e in self.s.timeline()["events"]), 1
        )

    def test_cancel_replace_require_exact_slot_and_leave_motion(self):
        self.start()
        self.queue()
        slot = self.s.deferred_task["deferred_id"]
        old = self.s.task_id
        with self.assertRaisesRegex(TaskError, "occupied"):
            self.queue()
        with self.assertRaisesRegex(TaskError, "stale"):
            self.call("robot_cancel_deferred", deferred_id="wrong")
        self.call(
            "robot_replace_deferred",
            deferred_id=slot,
            instruction="put the bowl on the plate",
            source="qwen_realtime_current_user",
            user_utterance="等这个任务完成后再把碗放到盘子上",
        )
        self.assertNotEqual(slot, self.s.deferred_task["deferred_id"])
        self.call("robot_cancel_deferred", deferred_id=self.s.deferred_task["deferred_id"])
        self.assertEqual(self.s.task_id, old)
        self.assertEqual(self.s.mode, "running")
        self.assertIsNone(self.s.deferred_task)

    def test_pause_cancel_switch_manual_completion_disconnect_invalidate(self):
        for action in (
            "robot_pause",
            "robot_cancel_task",
            "robot_revise_task",
            "robot_finish_task",
            "disconnect",
        ):
            self.start()
            self.queue()
            if action == "disconnect":
                self.s.interrupt("voice_client_disconnected")
            else:
                self.call(
                    action,
                    **(
                        {"instruction": "put the bowl on the plate"}
                        if action == "robot_revise_task"
                        else {}
                    ),
                )
            self.assertIsNone(self.s.deferred_task, action)

    def test_expiry_and_inventory_recheck_block_execution(self):
        self.start()
        self.queue()
        self.s.deferred_task["expires_at"] = time.time() - 1
        self.complete()
        self.assertEqual(self.s.mode, "completed")
        self.start()
        self.queue()
        self.s.scene_inventory = inventory_from_names(["wooden_cabinet_1"])
        self.complete()
        self.assertEqual(self.s.mode, "completed")
        self.assertIsNone(self.s.deferred_task)
        self.assertTrue(any(e["kind"] == "deferred_blocked" for e in self.s.timeline()["events"]))

    def test_no_implicit_queue_no_idle_queue_no_recovery_replay(self):
        with self.assertRaises(TaskError):
            self.queue()
        self.start()
        with self.assertRaisesRegex(TaskError, "explicit"):
            self.call(
                "robot_schedule_task",
                instruction="put the bowl on the plate",
                source="qwen_realtime_current_user",
                user_utterance="把碗放到盘子上",
            )
        self.queue()
        other = RobotState(self.tmp.name)
        try:
            self.assertIsNone(other.deferred_task)
        finally:
            other.db.close()

    def test_cancel_arrives_before_completion_blocks_handoff(self):
        self.start(); self.queue(); slot=self.s.deferred_task['deferred_id']; task=self.s.task_id
        self.s.record_interaction(dict(episode_id=self.s.episode,input_id='cancel-1',text='取消等会儿放碗的任务，当前任务继续'))
        self.complete()
        self.assertEqual(self.s.task_id,task)
        self.assertEqual(self.s.mode,'completed')
        self.assertEqual(self.s.deferred_task['dispatch_blocked_by_input'],'cancel-1')
        self.call('robot_cancel_deferred',deferred_id=slot)
        self.assertIsNone(self.s.deferred_task)

    def test_replacement_after_predecessor_completes_only_runs_new_goal(self):
        self.start()
        self.call('robot_schedule_task',instruction='put the cream cheese in the bowl',source='qwen_realtime_current_user',user_utterance='等当前任务完成后，再把奶酪放进碗里')
        slot=self.s.deferred_task['deferred_id']
        text='等当前任务完成后，改成把酒瓶放到柜顶，不放奶酪了。'
        self.s.record_interaction(dict(episode_id=self.s.episode,input_id='replace-1',text=text))
        self.complete()
        self.assertEqual(self.s.mode,'completed')
        r=self.call('robot_replace_deferred',deferred_id=slot,voice_input_id='replace-1',instruction='put the wine bottle on top of the cabinet',source='qwen_realtime_current_user',user_utterance=text)
        self.assertEqual(r['status'],'accepted')
        self.assertEqual(self.s.instruction,'put the wine bottle on top of the cabinet')
        self.assertIsNone(self.s.deferred_task)
        self.assertEqual(sum(e['kind']=='deferred_started' for e in self.s.timeline()['events']),1)

    def test_rejected_replacement_does_not_restore_old_queue(self):
        self.start();self.queue();slot=self.s.deferred_task['deferred_id']
        self.s.record_interaction(dict(episode_id=self.s.episode,input_id='replace-1',text='等当前任务完成后改成把碗放到炉灶上'))
        with self.assertRaises(TaskError):
            self.call('robot_replace_deferred',deferred_id=slot,instruction='put the grapes on the stove',source='qwen_realtime_current_user',user_utterance='等当前任务完成后改成把葡萄放到炉灶上')
        self.complete()
        self.assertEqual(self.s.mode,'completed')
        self.assertIsNotNone(self.s.deferred_task.get('dispatch_blocked_by_input'))

    def test_waiting_question_and_negated_cancel_keep_authority(self):
        self.start();self.queue()
        for i,text in enumerate(['如果取消等会儿的任务会怎样？','不要取消等会儿的任务','现在排队的任务是什么？']):
            self.s.record_interaction(dict(episode_id=self.s.episode,input_id='q'+str(i),text=text))
            self.assertNotIn('dispatch_blocked_by_input',self.s.deferred_task)
        self.complete()
        self.assertEqual(self.s.instruction,'put the bowl on the plate')

    def test_update_revision_and_input_fence_prevent_late_overwrite(self):
        self.start(); self.queue()
        first=dict(self.s.deferred_task)
        for identifier,text in [('u1','等当前任务完成后改成把碗放到炉灶上'),('u2','取消排队的任务，当前任务继续')]:
            self.s.record_interaction(dict(episode_id=self.s.episode,input_id=identifier,text=text))
        current=dict(self.s.deferred_task)
        self.assertEqual(current['transaction_revision'],first['transaction_revision']+2)
        self.assertEqual(current['dispatch_blocked_by_input'],'u2')
        with self.assertRaisesRegex(TaskError,'stale_transaction_revision'):
            self.call('robot_cancel_deferred',deferred_id=first['deferred_id'],transaction_id=first['transaction_id'],expected_transaction_revision=first['transaction_revision'])
        # Even refreshing the revision cannot transfer u2's authority to u1.
        with self.assertRaisesRegex(TaskError,'superseded_deferred_update_input'):
            self.call('robot_replace_deferred',deferred_id=current['deferred_id'],transaction_id=current['transaction_id'],expected_transaction_revision=current['transaction_revision'],voice_input_id='u1',source='qwen_realtime_current_user',user_utterance='等当前任务完成后改成把碗放到炉灶上',instruction='put the bowl on the stove')
        self.complete()
        self.assertEqual(self.s.mode,'completed')
        result=self.call('robot_cancel_deferred',deferred_id=current['deferred_id'],transaction_id=current['transaction_id'],expected_transaction_revision=current['transaction_revision'],voice_input_id='u2',source='qwen_realtime_current_user',user_utterance='取消排队的任务，当前任务继续')
        self.assertEqual(result['status'],'deferred_cancelled')
        self.assertIsNone(self.s.deferred_task)

    def test_plain_cancel_cannot_accidentally_cancel_waiting(self):
        self.start(); self.queue()
        with self.assertRaisesRegex(TaskError,'explicit_user_request|speech_does_not_authorize'):
            self.call('robot_cancel_deferred',deferred_id=self.s.deferred_task['deferred_id'],source='qwen_realtime_current_user',user_utterance='取消当前任务')
        self.assertIsNotNone(self.s.deferred_task)

    def test_queued_replacement_phrase_uses_new_goal(self):
        self.start(); self.queue()
        text='把排队的任务改成把碗放到炉灶上'
        self.s.record_interaction(dict(episode_id=self.s.episode,input_id='u1',text=text))
        self.call('robot_replace_deferred',deferred_id=self.s.deferred_task['deferred_id'],source='qwen_realtime_current_user',voice_input_id='u1',user_utterance=text,instruction='put the bowl on the stove')
        self.complete()
        self.assertEqual(self.s.instruction,'put the bowl on the stove')

    def test_late_cancel_cannot_cancel_started_successor(self):
        self.start();self.queue();slot=dict(self.s.deferred_task)
        self.complete(); successor=self.s.task_id
        with self.assertRaisesRegex(TaskError,'stale|expired'):
            self.call('robot_cancel_deferred',deferred_id=slot['deferred_id'])
        self.assertEqual(self.s.task_id,successor)
        self.assertEqual(self.s.mode,'running')

    def test_qa_and_negation_preserve_waiting_revision(self):
        self.start();self.queue();slot=dict(self.s.deferred_task)
        for i,text in enumerate(['排队的任务是什么？','不要取消排队的任务','如果替换等待的任务会怎么样？',"Don't cancel the queued task."]):
            self.s.record_interaction(dict(episode_id=self.s.episode,input_id='q'+str(i),text=text))
        self.assertEqual(self.s.deferred_task,slot)

    def test_temporal_memory_retains_completion_after_switch(self):
        self.start()
        old = self.s.task_id
        self.complete()
        self.call("robot_revise_task", instruction="put the bowl on the plate")
        history = self.s.task_history()
        selection = select_tasks(history, "之前完成过的抽屉任务", self.s.task_id)
        self.assertEqual(selection["resolution"], "unique")
        self.assertEqual(selection["candidates"][0]["task_id"], old)
        self.assertTrue(selection["candidates"][0]["ever_completed"])
        self.assertFalse(selection["candidates"][0]["is_current"])

    def test_wrong_temporal_memory_cannot_be_restored(self):
        first = self.start()
        self.call("robot_revise_task", instruction="put the bowl on the plate")
        with self.assertRaisesRegex(TaskError, "temporal_query"):
            self.call(
                "robot_restore_task",
                memory_id=first["memory_id"],
                source="qwen_realtime_current_user",
                user_utterance="恢复之前已经完成的抽屉任务",
            )

    def test_candidate_is_recorded_before_instruction(self):
        self.start()
        events = self.s.timeline()["events"]
        kinds = [e["kind"] for e in events]
        self.assertLess(kinds.index("task_candidate_checked"), kinds.index("task_instruction"))
        self.assertEqual(
            self.s.task_record["candidate_contract"]["instruction"], self.s.instruction
        )


if __name__ == "__main__":
    unittest.main()
