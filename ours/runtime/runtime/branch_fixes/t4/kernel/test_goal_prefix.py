"""Verify the actual composed parser, preserving all obligations/anchors."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0,'/mnt/disk_2/geyi/voice_c3r_integration_20261102')
from continuation.live import objectives
from t4_adapter import objectives as grammar
from t06_goal_language import install as install_t06
from t09_goal_prefix import install,leading_explicit_noun,bind_logger

class PrefixGrammar(unittest.TestCase):
    def setUp(self):
        self.initial={name:[float(i),0.,.9]for i,name in enumerate(objectives.OBJECTS.values())}
        self.current={name:[float(i)+.2,.1,.91]for i,name in enumerate(objectives.OBJECTS.values())}
        self.state={'turn_on_stove':False}
        self.q={'top':0.,'middle':0.}
    def normalize(self,text,fixed=True):
        module=SimpleNamespace(normalize_selected_task=grammar.normalize_selected_task)
        install_t06(module)
        if fixed:install(module)
        return module.normalize_selected_task(text,self.state)
    def make(self,text,fixed=True):
        return objectives.compile_objective(self.normalize(text,fixed),self.initial,self.current,self.q)
    def test_prior_composed_parser_reproduces_operation_inside_keep(self):
        with self.assertRaisesRegex(objectives.UnsupportedObjective,'extra_operation_in_keep_clause'):
            self.make('Leave that bowl where it is and put the wine bottle on the rack instead.',False)
    def test_explicit_leading_bowl_clause_and_final_goal(self):
        g=self.make('Leave that bowl where it is and put the wine bottle on the rack instead.')
        self.assertEqual(g.target_task,9)
        keep=next(c for c in g.clauses if c['kind']=='preserve_position')
        self.assertEqual(keep['object'],objectives.OBJECTS['bowl'])
        self.assertEqual(keep['reference_position'],self.current[objectives.OBJECTS['bowl']])
        self.assertNotIn('activation_after',keep)
        self.assertEqual([c['kind']for c in g.clauses],['native_target','preserve_position'])
    def test_explicit_this_bowl(self):
        self.assertEqual(self.make('Leave this bowl where it is and put the wine bottle on the rack.').target_task,9)
    def test_different_explicit_object(self):
        g=self.make('Keep that plate in place and turn on the stove.')
        self.assertEqual(g.target_task,7)
        self.assertEqual(next(c['object']for c in g.clauses if c['kind']=='preserve_position'),objectives.OBJECTS['plate'])
    def test_existing_the_prefix_unchanged(self):
        text='Leave the bowl where it is and put the wine bottle on the rack.'
        self.assertEqual(leading_explicit_noun(text),text)
        self.assertEqual(self.make(text).target_task,9)
    def test_other_command_unaffected(self):
        text='Put the cheese in that bowl and leave the bowl there.'
        self.assertEqual(leading_explicit_noun(text),text)
        self.assertEqual(self.make(text).target_task,6)
    def test_bare_it_not_guessed(self):
        text='Leave it where it is and put the wine bottle on the rack.'
        self.assertEqual(leading_explicit_noun(text),text)
        with self.assertRaises(objectives.UnsupportedObjective):self.make(text)
    def test_bare_that_one_not_guessed(self):
        with self.assertRaises(objectives.UnsupportedObjective):self.make('Leave that one there and put the wine bottle on the rack.')
    def test_unknown_object_not_guessed(self):
        with self.assertRaises(objectives.UnsupportedObjective):self.make('Leave that mug there and put the wine bottle on the rack.')
    def test_plural_not_collapsed(self):
        text='Leave those bowls there and put the wine bottle on the rack.'
        self.assertEqual(leading_explicit_noun(text),text)
        with self.assertRaises(objectives.UnsupportedObjective):self.make(text)
    def test_unknown_constraint_is_not_deleted(self):
        with self.assertRaises(objectives.UnsupportedObjective):self.make('Leave that bowl tilted and put the wine bottle on the rack.')
    def test_extra_unsupported_operation_not_deleted(self):
        with self.assertRaises(objectives.UnsupportedObjective):self.make('Leave that bowl where it is and put the wine bottle on the rack, then push the mug under the table.')
    def test_extra_distinct_final_goal_not_deleted(self):
        with self.assertRaises(objectives.UnsupportedObjective):self.make('Leave that bowl where it is and put the wine bottle on the rack, then put the cheese in the bowl.')
    def test_negation_not_broadened(self):
        for text in ['Do not leave that bowl there and put the bottle on the rack.', 'Never leave that bowl there and put the bottle on the rack.']:
            self.assertEqual(leading_explicit_noun(text),text)
            with self.assertRaises(objectives.UnsupportedObjective):self.make(text)
    def test_condition_not_broadened(self):
        with self.assertRaises(objectives.UnsupportedObjective):self.make('If the bottle is empty leave that bowl there and put the bottle on the rack.')
    def test_return_anchor_still_episode_start(self):
        g=self.make('Return that bowl to its episode-start position and release it.')
        self.assertEqual(next(c['reference_position']for c in g.clauses if c['kind']=='restore_episode_start'),self.initial[objectives.OBJECTS['bowl']])
    def test_return_then_keep_still_activates_after_restore(self):
        g=self.make('Return that bowl to its episode-start position, then put the cheese in that bowl. Keep that bowl at its returned position afterward.')
        self.assertEqual(next(c['activation_after']for c in g.clauses if c['kind']=='preserve_position'),'restore_0')
    def test_module_install_logging_and_idempotence(self):
        module=SimpleNamespace(normalize_selected_task=grammar.normalize_selected_task);install_t06(module);install(module)
        old=module.normalize_selected_task;install(module);self.assertIs(old,module.normalize_selected_task)
        self.assertTrue(module.normalize_selected_task._t06_explicit_noun_determiner)
        events=[];bind_logger(lambda k,**kw:events.append((k,kw)))
        text='Leave that bowl where it is and put the wine bottle on the rack.'
        result=module.normalize_selected_task(text,self.state);bind_logger(None)
        self.assertIn(';',result)
        self.assertEqual(events[0][1]['original_instruction'],text)
        self.assertFalse(events[0][1]['agent_task_rewritten'])
        self.assertFalse(events[0][1]['numerical_thresholds_changed'])

if __name__=='__main__':unittest.main(verbosity=2)
