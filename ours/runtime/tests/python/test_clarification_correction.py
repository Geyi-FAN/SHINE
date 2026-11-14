"""F04: distinguish rejected noun candidates from required actions/constraints."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'runtime/freeze/voice/robot_gateway'))
from core import RobotState, TaskError
from grounding import ENTITIES, inventory_from_names, command_content, explicit_object_correction


class CorrectionAnswerTests(unittest.TestCase):
    raw = "I'd like you to put an object somewhere else."
    full = 'Not the wine bottle. Put the bowl on the plate.'

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

    def cmd(self, name, text, **args):
        self.seq += 1
        identifier = 'u' + str(self.seq)
        self.s.record_interaction(dict(episode_id=self.s.episode, input_id=identifier,
                                      text=text, task_version=self.s.version))
        return self.s.command(name, dict(episode_id=self.s.episode,
            expected_task_version=self.s.version, user_utterance=text,
            voice_input_id=identifier, source='qwen_realtime_current_user', **args), str(self.seq))

    def begin(self, text=None, question='Which object should I put where?', missing_slot='object'):
        return self.cmd('robot_begin_clarification', self.raw if text is None else text,
                        question=question, missing_slot=missing_slot)['pending_clarification']

    def answer(self, p, text=None, instruction='put the bowl on the plate', question=None, **args):
        row = self.s.dialogue_transactions.get(p['clarification_id'])
        return self.cmd('robot_answer_clarification', self.full if text is None else text,
            clarification_id=p['clarification_id'], transaction_id=p['clarification_id'],
            expected_transaction_revision=row['revision'],
            **({'question': question} if question else {'instruction': instruction}), **args)

    def test_full_correction_with_agent_selected_object(self):
        r = self.answer(self.begin(), resolved_answer='The bowl')
        self.assertEqual(r['status'], 'accepted')
        e = self.s.task_record['clarification_evidence']
        self.assertEqual([t['text'] for t in e['source_utterances']], [self.raw, self.full])
        a = e['active_source_utterances'][1]
        self.assertEqual(a['text'], 'Put the bowl on the plate.')
        self.assertEqual(a['object_correction']['rejected_entity'], 'bottle')
        b = {x['slot']: x for x in e['active_source_utterances'][0]['slot_bindings']}
        self.assertEqual((b['object']['bound_entity'], b['destination']['bound_entity']), ('bowl', 'plate'))
        self.assertEqual(b['object']['answer_input_id'], e['source_utterances'][1]['input_id'])
        self.assertEqual(self.s.action_steps, 0)

    def test_full_correction_without_normalization(self):
        self.assertEqual(self.answer(self.begin())['status'], 'accepted')

    def test_object_correction_then_nominal_destination(self):
        r = self.answer(self.begin(question='Which object?'), text='Not the wine bottle. The bowl.',
                        question='Where should I put it?', resolved_answer='The bowl')
        self.assertEqual(r['status'], 'needs_clarification')
        self.assertIsNone(self.s.task_id)
        r = self.answer(r['pending_clarification'], text='The destination is the plate.')
        self.assertEqual(r['status'], 'accepted')
        b = self.s.task_record['clarification_evidence']['active_source_utterances'][0]['slot_bindings']
        self.assertIsNone(b[1]['relation'])  # Never pretend the user explicitly said on/in.

    def test_destination_then_object_correction(self):
        p = self.begin(question='Where should I put it?', missing_slot='destination')
        r = self.answer(p, text='On the plate.', question='Which object?')
        self.assertEqual(self.answer(r['pending_clarification'], text='Not the wine bottle. The bowl.',
                                    resolved_answer='The bowl')['status'], 'accepted')

    def test_current_complete_correction_can_start_directly(self):
        self.assertEqual(self.cmd('robot_start_task', self.full,
                                 instruction='put the bowl on the plate')['status'], 'accepted')

    def test_direct_correction_keeps_raw_user_speech(self):
        self.cmd('robot_start_task', self.full, instruction='put the bowl on the plate')
        self.assertEqual(self.s.task_record['user_utterance'], self.full)

    def test_other_objects_not_hardcoded(self):
        self.assertEqual(self.answer(self.begin(), text='Not the bowl. Put the cream cheese in the bowl.',
                                    instruction='put the cream cheese in the bowl', resolved_answer='The cream cheese')['status'], 'accepted')

    def test_rejected_object_cannot_be_normalized_positive(self):
        with self.assertRaisesRegex(TaskError, 'normalized_answer_not_supported'):
            self.answer(self.begin(), resolved_answer='The wine bottle')
        self.assertIsNone(self.s.task_id)

    def test_normalization_cannot_be_generated_task(self):
        with self.assertRaises(TaskError):
            self.answer(self.begin(), resolved_answer='Put the bowl on the plate')

    def test_negation_without_positive_object_does_not_authorize_task(self):
        with self.assertRaises(TaskError):
            self.answer(self.begin(), text='Not the wine bottle.', resolved_answer='The bowl')
        self.assertIsNone(self.s.task_id)

    def test_only_object_does_not_authorize_guessed_destination(self):
        with self.assertRaises(TaskError):
            self.answer(self.begin(), text='Not the wine bottle. The bowl.', resolved_answer='The bowl')
        self.assertIsNone(self.s.task_id)

    def test_only_destination_does_not_authorize_guessed_object(self):
        with self.assertRaises(TaskError):
            self.answer(self.begin(question='Where?'), text='On the plate.')
        self.assertIsNone(self.s.task_id)

    def test_generic_first_turn_cannot_be_guessed(self):
        with self.assertRaises(TaskError):
            self.cmd('robot_start_task', self.raw, instruction='put the bowl on the plate')

    def test_corrected_task_cannot_use_rejected_object(self):
        with self.assertRaises(TaskError):
            self.answer(self.begin(), instruction='put the wine bottle on the plate', resolved_answer='The bowl')

    def test_direct_corrected_task_cannot_add_rejected_object(self):
        with self.assertRaises(TaskError):
            self.cmd('robot_start_task', self.full, instruction='put the bowl on the plate then put the wine bottle on the stove')

    def test_roles_cannot_swap(self):
        with self.assertRaises(TaskError):
            self.answer(self.begin(), instruction='put the plate on the bowl', resolved_answer='The bowl')

    def test_explicit_surface_cannot_become_containment(self):
        with self.assertRaisesRegex(TaskError, 'clarification_destination_relation_mismatch'):
            self.answer(self.begin(), instruction='put the bowl in the plate', resolved_answer='The bowl')

    def test_two_open_requests_need_further_clarification(self):
        p = self.begin(self.raw + ' Then put an object somewhere else.')
        with self.assertRaises(TaskError):
            self.answer(p, resolved_answer='The bowl')

    def test_original_constraint_cannot_be_dropped(self):
        p = self.begin(self.raw + ' Keep the stove in its current state.')
        with self.assertRaises(TaskError):
            self.answer(p, resolved_answer='The bowl')

    def test_original_confirmation_permission_cannot_be_dropped(self):
        p = self.begin(self.raw + ' But ask me before starting.')
        self.assertEqual(self.answer(p, resolved_answer='The bowl')['status'], 'needs_confirmation')
        self.assertIsNone(self.s.task_id)

    def test_action_prohibition_is_not_object_correction(self):
        text = 'Do not move the wine bottle. Put the bowl on the plate.'
        self.assertIsNone(explicit_object_correction(text))
        self.assertEqual(command_content(text), text)
        with self.assertRaises(TaskError):
            self.cmd('robot_start_task', text, instruction='put the bowl on the plate')

    def test_constraint_after_correction_is_not_discarded(self):
        with self.assertRaises(TaskError):
            self.cmd('robot_start_task', self.full + ' Do not move the wine bottle.', instruction='put the bowl on the plate')

    def test_expired_transaction_rejected(self):
        p = self.begin()
        self.s.pending_clarification['expires_at'] = 0
        with self.assertRaises(TaskError):
            self.answer(p, resolved_answer='The bowl')

    def test_wrong_transaction_revision_rejected(self):
        p = self.begin()
        with self.assertRaises(TaskError):
            self.cmd('robot_answer_clarification', self.full, clarification_id=p['clarification_id'],
                     transaction_id=p['clarification_id'], expected_transaction_revision=999,
                     instruction='put the bowl on the plate', resolved_answer='The bowl')

    def test_ambiguous_positive_choice_is_not_silently_selected(self):
        with self.assertRaises(TaskError):
            self.answer(self.begin(), text='Not the wine bottle. The bowl or the plate.', resolved_answer='The bowl')


if __name__ == '__main__':
    unittest.main()
