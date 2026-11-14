"""Compile actual language variants while protecting obligations and anchors."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, '/mnt/disk_2/geyi/voice_c3r_integration_20261102')
from continuation.live.objectives import compile_objective, UnsupportedObjective, OBJECTS
from t4_adapter.objectives import normalize_selected_task
from t06_goal_language import equivalent_goal_text, install, bind_logger


class GoalLanguage(unittest.TestCase):
    def setUp(self):
        self.initial = {name: [float(i), 0., .9] for i, name in enumerate(OBJECTS.values())}
        self.current = {name: [float(i) + .1, .2, .91] for i, name in enumerate(OBJECTS.values())}
        self.q = {'top': 0., 'middle': 0.}

    def make(self, text):
        return compile_objective(equivalent_goal_text(normalize_selected_task(text, {'turn_on_stove':False})),
                                 self.initial, self.current, self.q)

    def test_historical_literal_reproduces_old_rejection(self):
        with self.assertRaises(UnsupportedObjective):
            compile_objective('put the cream cheese in that bowl and leave the bowl there', self.initial, self.current, self.q)

    def test_explicit_bowl_and_preservation_compile_together(self):
        goal = self.make('put the cream cheese in that bowl and leave the bowl there')
        self.assertEqual(goal.target_task, 6)
        keep = next(c for c in goal.clauses if c['kind']=='preserve_position')
        self.assertEqual(keep['object'], OBJECTS['bowl'])
        self.assertEqual(keep['reference_position'], self.current[OBJECTS['bowl']])
        self.assertNotIn('activation_after', keep)

    def test_no_return_or_close_added(self):
        goal = self.make('put the cream cheese in that bowl and leave the bowl there')
        self.assertEqual([c['kind'] for c in goal.clauses], ['native_target','preserve_position'])

    def test_ordinary_the_bowl_is_unchanged(self):
        text = 'put the cream cheese in the bowl and leave the bowl there'
        self.assertEqual(equivalent_goal_text(text), text)

    def test_this_bowl_is_accepted(self):
        self.assertEqual(self.make('put the cream cheese in this bowl').target_task, 6)

    def test_determiner_in_keep_clause_keeps_the_obligation(self):
        g = self.make('put the cream cheese in that bowl. Leave that bowl there.')
        self.assertTrue(any(c['kind']=='preserve_position' for c in g.clauses))

    def test_determiner_in_source_keeps_object(self):
        self.assertEqual(self.make('put that bowl on this plate').target_task, 8)

    def test_source_task_temporal_words_are_not_rewritten(self):
        text = 'return that bowl to its position at the beginning of the source task'
        self.assertEqual(equivalent_goal_text(text), text.replace('that bowl','the bowl'))

    def test_episode_start_reference_not_changed_to_current(self):
        g = self.make('return that bowl to its episode-start position and release it')
        r = next(c for c in g.clauses if c['kind']=='restore_episode_start')
        self.assertEqual(r['reference_position'], self.initial[OBJECTS['bowl']])

    def test_return_then_preserve_activation_remains_after_return(self):
        g = self.make('return that bowl to its episode-start position, then put the cheese in that bowl. Keep that bowl at its returned position afterward.')
        self.assertEqual(next(c for c in g.clauses if c['kind']=='preserve_position')['activation_after'], 'restore_0')

    def test_extra_operation_not_silently_removed(self):
        with self.assertRaises(UnsupportedObjective):
            self.make('put the cheese in that bowl. Keep the bowl there and move the wine bottle under the table')

    def test_unknown_keep_requirement_not_dropped(self):
        with self.assertRaises(UnsupportedObjective):
            self.make('put the cheese in that bowl. Keep the bowl tilted')

    def test_bare_it_still_needs_resolution(self):
        with self.assertRaises(UnsupportedObjective): self.make('put it on that plate')

    def test_bare_destination_still_needs_resolution(self):
        with self.assertRaises(UnsupportedObjective): self.make('put the cream cheese in that one')

    def test_bare_there_still_needs_resolution(self):
        with self.assertRaises(UnsupportedObjective): self.make('put the cheese there')

    def test_unknown_noun_not_invented(self):
        with self.assertRaises(UnsupportedObjective): self.make('put the cheese in that mug')

    def test_plural_not_collapsed_to_single_object(self):
        with self.assertRaises(UnsupportedObjective): self.make('put the cheese in those bowls')

    def test_unknown_drawer_level_not_invented(self):
        with self.assertRaises(UnsupportedObjective): self.make('open that drawer')

    def test_negation_not_made_executable(self):
        for s in ['do not put the cheese in that bowl', "don't put the cheese in that bowl", 'never put the cheese in that bowl']:
            self.assertEqual(equivalent_goal_text(s), s)
            with self.assertRaises(UnsupportedObjective): self.make(s)

    def test_conditional_still_rejected(self):
        with self.assertRaises(UnsupportedObjective): self.make('if it is empty put the cheese in that bowl')

    def test_parser_install_and_logging_preserve_input(self):
        logs = []; bind_logger(lambda name, **fields: logs.append((name, fields)))
        module = SimpleNamespace(normalize_selected_task=lambda text, state: text)
        install(module); wrapped = module.normalize_selected_task; install(module)
        self.assertIs(wrapped, module.normalize_selected_task)
        raw = 'put the cheese in that bowl and leave the bowl there'
        out = module.normalize_selected_task(raw, None)
        self.assertEqual(out, 'put the cheese in the bowl and leave the bowl there')
        self.assertEqual(raw, logs[0][1]['original_instruction'])
        self.assertFalse(logs[0][1]['agent_task_rewritten'])
        self.assertFalse(logs[0][1]['numerical_thresholds_changed'])
        bind_logger(None)


if __name__ == '__main__': unittest.main(verbosity=2)
