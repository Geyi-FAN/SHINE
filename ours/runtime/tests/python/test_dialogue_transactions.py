"""Cross-slot lifecycle regressions; no model or simulator truth injected into planning."""
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/freeze/voice/robot_gateway'))
from core import RobotState, TaskError
from grounding import ENTITIES, inventory_from_names

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = RobotState(self.tmp.name)
        self.s.ready = True
        self.s.mode = 'idle'
        self.s.scene_inventory = inventory_from_names(v[0] for v in ENTITIES.values())
        self.seq = 0
    def tearDown(self):
        self.s.db.close()
        self.tmp.cleanup()
    def call(self, name, **args):
        self.seq += 1
        return self.s.command(name, dict(episode_id=self.s.episode, expected_task_version=self.s.version, **args), str(self.seq))
    def begin(self):
        return self.call('robot_begin_clarification', user_utterance='把它放到盘子上', voice_input_id='u1', question='哪个物体？', missing_slot='object')['pending_clarification']
    def propose(self):
        return self.call('robot_propose_task', instruction='put the bowl on the plate', user_utterance='把碗放到盘子上')['pending_proposal']
    def test_followup_revision_rejects_delayed_answer(self):
        p = self.begin()
        version = self.s.version
        self.call('robot_answer_clarification', clarification_id=p['clarification_id'], transaction_id=p['transaction_id'], expected_transaction_revision=1, user_utterance='碗', voice_input_id='u2', question='确定放在盘子上吗？')
        self.assertEqual(self.s.pending_clarification['transaction_revision'], 2)
        self.assertEqual(self.s.version, version)
        with self.assertRaisesRegex(TaskError, 'stale_transaction_revision'):
            self.call('robot_answer_clarification', clarification_id=p['clarification_id'], transaction_id=p['transaction_id'], expected_transaction_revision=1, user_utterance='盘子上', voice_input_id='u3', instruction='put the bowl on the plate')
        self.assertIsNone(self.s.task_id)
    def test_proposal_qa_preserves_all_versions(self):
        p = self.propose()
        for i, text in enumerate(['现在做到哪一步了？', '现在什么状态', '谢谢']):
            self.s.record_interaction(dict(episode_id=self.s.episode, input_id='q'+str(i), text=text))
        self.assertEqual(self.s.pending_proposal['transaction_id'], p['transaction_id'])
        self.assertEqual(self.s.pending_proposal['transaction_revision'], 1)
        self.assertEqual(self.s.version, 0)
    def test_confirm_consumed_once_even_different_request_id(self):
        p = self.propose()
        args = dict(proposal_id=p['proposal_id'], transaction_id=p['transaction_id'], expected_transaction_revision=1, decision='confirm')
        result = self.call('robot_resolve_proposal', **args)
        row = self.s.dialogue_transactions.get(p['transaction_id'])
        self.assertEqual(row['status'], 'consumed')
        self.assertEqual(row['consumed_by_task_id'], result['task_id'])
        with self.assertRaises(TaskError): self.call('robot_resolve_proposal', **args)
        self.assertEqual(self.s.task_id, result['task_id'])
        self.assertEqual(self.s.task_intent_revision, 1)
    def test_explicit_transaction_requires_revision(self):
        p = self.propose()
        with self.assertRaisesRegex(TaskError, 'revision_required'):
            self.call('robot_resolve_proposal', proposal_id=p['proposal_id'], transaction_id=p['transaction_id'], decision='confirm')
    def test_foreground_conflict_not_overwritten(self):
        p = self.begin()
        with self.assertRaisesRegex(TaskError, 'existing_clarification'): self.propose()
        self.assertEqual(self.s.pending_clarification['clarification_id'], p['clarification_id'])
    def test_restart_invalidates_pending_ledger_without_replay(self):
        p = self.propose()
        self.s.db.close()
        self.s = RobotState(self.tmp.name)
        row = self.s.dialogue_transactions.get(p['transaction_id'])
        self.assertEqual(row['status'], 'cancelled')
        self.assertEqual(row['reason'], 'process_restarted')
        self.assertIsNone(self.s.task_id)
        self.assertEqual(self.s.queue, [])
    def queue(self):
        self.call('robot_start_task', instruction='put the bowl on the stove')
        return self.call('robot_schedule_task', instruction='put the cream cheese in the bowl', user_utterance='等当前任务完成后再把奶酪放进碗里', voice_input_id='w1')['deferred_task']
    def test_waiting_no_early_dispatch_then_consumed(self):
        p = self.queue()
        task = self.s.task_id
        self.assertEqual(self.s.dialogue_transactions.get(p['transaction_id'])['status'], 'queued')
        self.assertEqual(self.s.task_id, task)
        self.s.mode = 'completed'
        self.s.completion_status = 'verified'
        self.s._run_deferred()
        row = self.s.dialogue_transactions.get(p['transaction_id'])
        self.assertEqual(row['status'], 'consumed')
        self.assertNotEqual(row['consumed_by_task_id'], task)
        new = self.s.task_id
        self.s._run_deferred()
        self.assertEqual(new, self.s.task_id)
    def test_pause_invalidates_waiting_without_changing_intent(self):
        p = self.queue()
        intent = self.s.task_intent_revision
        self.call('robot_pause')
        self.assertEqual(self.s.task_intent_revision, intent)
        self.assertEqual(self.s.dialogue_transactions.get(p['transaction_id'])['status'], 'cancelled')
    def test_resolved_clarification_records_consuming_task(self):
        p = self.begin()
        r = self.call('robot_answer_clarification', clarification_id=p['clarification_id'], user_utterance='碗', voice_input_id='u2', instruction='put the bowl on the plate')
        row = self.s.dialogue_transactions.get(p['transaction_id'])
        self.assertEqual(row['status'], 'resolved')
        self.assertEqual(row['source_input_ids'], ['u1', 'u2'])
        self.assertEqual(row['resolved_instruction'], 'put the bowl on the plate')
        if r['status'] == 'accepted': self.assertEqual(row['consumed_by_task_id'], r['task_id'])
        else: self.assertEqual(row['successor_transaction_id'], r['pending_proposal']['proposal_id'])
    def test_commit_failure_rolls_back_task_ledger_and_receipt(self):
        p = self.propose()
        original = self.s._save_receipt
        def fail_after_write(*args):
            original(*args)
            raise RuntimeError('injected_receipt_failure')
        self.s._save_receipt = fail_after_write
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            self.call('robot_resolve_proposal', proposal_id=p['proposal_id'], decision='confirm')
        self.s._save_receipt = original
        self.assertIsNone(self.s.task_id)
        self.assertEqual(self.s.mode, 'idle')
        self.assertEqual(self.s.dialogue_transactions.get(p['transaction_id'])['status'], 'awaiting_confirmation')
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0], 0)
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM receipts').fetchone()[0], 1)
