"""Full affirmative must consume the live corrected proposal, never bypass it."""
import tempfile
import unittest

from core import RobotState, TaskError
from grounding import ENTITIES, inventory_from_names
from semantics import confirmation_answer
from instructions import normalize_instruction


class ConfirmationIdentityAnnotationTests(unittest.TestCase):
    def test_literal_source_correction_preserves_confirmation_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            state = RobotState(folder)
            try:
                state.ready = True
                state.mode = 'idle'
                state.scene_inventory = inventory_from_names(v[0] for v in ENTITIES.values())
                raw = 'Keep the wine bottle as the object, but put it on the rack. Ask me to confirm the change.'
                for index, text in enumerate([raw, raw.replace('put it', 'put the wine bottle')]):
                    uid = 'correction-' + str(index)
                    state.record_interaction(dict(episode_id=state.episode, input_id=uid,
                                                  text=text, task_version=state.version))
                    receipt = state.command('robot_propose_task', dict(
                        episode_id=state.episode, expected_task_version=state.version,
                        source='qwen_realtime_current_user', user_utterance=text,
                        voice_input_id=uid, instruction='put the wine bottle on the rack'), uid)
                    self.assertEqual(receipt['status'], 'needs_confirmation')
                    self.assertEqual(receipt['pending_proposal']['user_utterance'], text)
                    self.assertIsNone(state.task_id)
                    self.assertEqual(state.action_steps, 0)
            finally:
                state.db.close()

    def test_matching_repeated_identity(self):
        for obj, dest in [('wine bottle', 'rack'), ('bowl', 'stove'), ('plate', 'cabinet')]:
            task = f'put the {obj} on the {dest}'
            self.assertEqual(confirmation_answer(
                'Yes, ' + task + '.', task + f', keeping the {obj} as the object'), 'confirm')

    def test_different_object_extra_action_and_physical_constraint_not_dropped(self):
        answer = 'Yes, put the wine bottle on the rack.'
        for expected in [
            'put the wine bottle on the rack, keeping the bowl as the object',
            'put the wine bottle on the rack, keeping the bowl in place',
            'put the wine bottle on the rack then open the middle drawer',
            'put the wine bottle on top of the cabinet, keeping the wine bottle as the object',
        ]:
            self.assertIsNone(confirmation_answer(answer, expected), expected)

    def test_identity_annotation_normalizes_to_complete_supported_task(self):
        value, kind = normalize_instruction(
            'put the wine bottle on the rack, keeping the wine bottle as the object')
        self.assertEqual(value, 'put the wine bottle on the rack')
        self.assertEqual(kind, 'same_source_identity_annotation')

    def test_real_constraints_and_unknown_actions_remain_intact(self):
        for task in [
            'put the wine bottle on the rack, keeping the bowl in place',
            'put the wine bottle on the rack, keeping the bowl as the object',
            'put the wine bottle on the rack then close the drawer, keeping the wine bottle as the object',
        ]:
            self.assertEqual(normalize_instruction(task)[0], task)

    def test_live_gateway_consumption_and_duplicate_cannot_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            state = RobotState(folder)
            try:
                state.ready = True
                state.mode = 'idle'
                state.scene_inventory = inventory_from_names(v[0] for v in ENTITIES.values())
                raw = 'Keep the wine bottle as the object, but put it on the rack. Ask me to confirm the change.'
                instruction = 'put the wine bottle on the rack, keeping the wine bottle as the object'
                state.record_interaction(dict(episode_id=state.episode, input_id='correction',
                                              text=raw, task_version=state.version))
                pending = state.command('robot_propose_task', dict(
                    episode_id=state.episode, expected_task_version=state.version,
                    source='qwen_realtime_current_user', user_utterance=raw,
                    voice_input_id='correction', instruction=instruction), 'proposal')['pending_proposal']
                answer = 'Yes, put the wine bottle on the rack.'
                record = state.record_interaction(dict(episode_id=state.episode, input_id='yes',
                                                       text=answer, task_version=state.version))
                self.assertEqual(record['confirmation']['proposal_id'], pending['proposal_id'])
                self.assertIsNone(state.task_id)  # Transcript alone never moves.
                revision = state.dialogue_transactions.get(pending['proposal_id'])['revision']
                receipt = state.command('robot_resolve_proposal', dict(
                    episode_id=state.episode, expected_task_version=state.version,
                    source='qwen_realtime_current_user', user_utterance=answer,
                    voice_input_id='yes', proposal_id=pending['proposal_id'], decision='confirm',
                    transaction_id=pending['proposal_id'], expected_transaction_revision=revision), 'resolve')
                self.assertEqual(receipt['confirmed_proposal_id'], pending['proposal_id'])
                self.assertEqual(state.task_record['confirmed_proposal_id'], pending['proposal_id'])
                self.assertEqual(state.instruction, 'put the wine bottle on the rack')
                self.assertEqual(state.task_record['requested_instruction'],
                                 'put the wine bottle on the rack')
                identity = (state.task_id, state.version, state.action_steps)
                duplicate = state.record_interaction(dict(episode_id=state.episode, input_id='yes-again',
                                                          text=answer, task_version=state.version))
                self.assertNotIn('confirmation', duplicate)
                self.assertEqual(identity, (state.task_id, state.version, state.action_steps))
            finally:
                state.db.close()
