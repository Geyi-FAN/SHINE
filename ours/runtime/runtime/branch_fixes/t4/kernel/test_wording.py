"""Generic catalog examples, including negative hidden-requirement cases."""
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

B = Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
sys.path.insert(0, str(B))
from t03_wording import exact_intrinsic_task, install
from t3repair.wording import exact_authorized_task, reused_task

TASK = 'open the box and put the can inside'
PRE = ['open the box']
CATALOG = [dict(canonical_task=TASK, intrinsic_preconditions=PRE)]


def state():
    base = dict(structure_source='training_template_contract', preconditions=PRE.copy(),
                persistent_constraints=[], reference_memory_ids=['dialogue-object-reference'],
                semantic_check=dict(decision='checked'))
    record = dict(copy.deepcopy(base), complete_instruction=TASK)
    record['candidate_contract'] = dict(copy.deepcopy(base), instruction=TASK, unresolved=[])
    return SimpleNamespace(instruction=TASK, normalization='exact_training_template', task_record=record)


class IntrinsicReuse(unittest.TestCase):
    def test_explicit_intrinsic_condition_can_reuse(self):
        s = state(); self.assertFalse(exact_authorized_task(s, TASK, CATALOG))
        self.assertTrue(exact_intrinsic_task(s, TASK, CATALOG))

    def test_no_rewrite_or_stage_is_generated(self):
        r = reused_task(TASK)
        self.assertEqual(r['output']['execution_task'], TASK)
        self.assertFalse(r['wording_agent_called']); self.assertNotIn('remaining_plan', r['output'])

    def test_missing_exact_normalization_rejected(self):
        s = state(); s.normalization = None
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_different_active_task_rejected(self):
        s = state(); s.instruction = 'different task'
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_unknown_training_sentence_rejected(self):
        self.assertFalse(exact_intrinsic_task(state(), TASK, []))

    def test_ambiguous_catalog_rejected(self):
        self.assertFalse(exact_intrinsic_task(state(), TASK, CATALOG + CATALOG))

    def test_extra_precondition_rejected(self):
        for name in ['record', 'candidate']:
            s = state(); target = s.task_record if name == 'record' else s.task_record['candidate_contract']
            target['preconditions'].append('close another box')
            self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_extra_persistent_requirement_rejected(self):
        for name in ['record', 'candidate']:
            s = state(); target = s.task_record if name == 'record' else s.task_record['candidate_contract']
            target['persistent_constraints'] = ['keep the bottle unmoved']
            self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_missing_intrinsic_precondition_rejected(self):
        s = state(); s.task_record['preconditions'] = []
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_duplicate_precondition_rejected(self):
        s = state(); s.task_record['preconditions'] += PRE
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_unresolved_reference_rejected(self):
        s = state(); s.task_record['candidate_contract']['unresolved'] = ['which can']
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_semantic_checks_required_on_both(self):
        for name in ['record', 'candidate']:
            s = state(); target = s.task_record if name == 'record' else s.task_record['candidate_contract']
            target['semantic_check']['decision'] = 'uncertain'
            self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_complete_text_must_match_on_both(self):
        for name, field in [('record', 'complete_instruction'), ('candidate', 'instruction')]:
            s = state(); target = s.task_record if name == 'record' else s.task_record['candidate_contract']
            target[field] += ' then close the box'
            self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_template_provenance_required_on_both(self):
        for name in ['record', 'candidate']:
            s = state(); target = s.task_record if name == 'record' else s.task_record['candidate_contract']
            target['structure_source'] = 'model_guess'
            self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_mismatched_reference_bindings_rejected(self):
        s = state(); s.task_record['candidate_contract']['reference_memory_ids'] = ['different-reference']
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_malformed_reference_binding_rejected(self):
        s = state(); s.task_record['reference_memory_ids'] = 'not-a-list'
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_malformed_semantic_check_rejected(self):
        for value in [None, [], 'checked']:
            s = state(); s.task_record['semantic_check'] = value
            self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_malformed_task_record_rejected(self):
        s = state(); s.task_record = ['unexpected']
        self.assertFalse(exact_intrinsic_task(s, TASK, CATALOG))

    def test_install_is_idempotent_and_preserves_original(self):
        calls = []
        module = SimpleNamespace(exact_authorized_task=lambda *args: calls.append(args) or False)
        install(module); wrapped = module.exact_authorized_task; install(module)
        self.assertIs(module.exact_authorized_task, wrapped)
        self.assertTrue(module.exact_authorized_task(state(), TASK, CATALOG)); self.assertEqual(len(calls), 1)

    def test_original_simple_tasks_remain_unchanged(self):
        module = SimpleNamespace(exact_authorized_task=exact_authorized_task); install(module)
        s = SimpleNamespace(instruction='move the box', normalization='exact_training_template', task_record={})
        self.assertTrue(module.exact_authorized_task(s, s.instruction, [dict(canonical_task=s.instruction)]))


if __name__ == '__main__': unittest.main(verbosity=2)
