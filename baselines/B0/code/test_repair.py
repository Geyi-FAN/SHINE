"""Engineering regressions independent of physical model success."""
import ast,json,unittest
from pathlib import Path
from repair_runner import normalize_budgets,N
OLD=Path('/mnt/disk_4/geyi/audio_switch_benchmark/experiments/asr_direct_pi05_formal_20261108')
class Repair(unittest.TestCase):
 def test_protocol_aliases_preserve_existing_numeric_limits(self):
  original=json.loads((N/'data/T8/data/PROTOCOL.json').read_text())['budgets'];b=normalize_budgets(original)
  self.assertEqual(b['precondition_wall_s'],180);self.assertEqual(b['per_physical_goal_wall_s'],600);self.assertEqual(b['qa_complete_answer_from_audio_end_s'],40)
  for k,v in original.items():self.assertEqual(b[k],v)
 def test_missing_nonfinite_and_conflicting_budgets_rejected(self):
  for value in [None,float('nan'),float('inf'),0,-1,True]:
   with self.assertRaises(ValueError):normalize_budgets(dict(setup_wall_s=value,source_wall_s=600,qa_complete_audio_s=40))
  with self.assertRaises(ValueError):normalize_budgets(dict(setup_wall_s=180,precondition_wall_s=181,source_wall_s=600,qa_complete_audio_s=40))
 def test_decoder_neural_function_unchanged(self):
  def get(path):return next(n for n in ast.walk(ast.parse(path.read_text()))if isinstance(n,ast.FunctionDef)and n.name=='decode')
  self.assertEqual(ast.dump(get(OLD/'code/asr_server.py'),include_attributes=False),ast.dump(get(N/'code/asr_server.py'),include_attributes=False))
 def test_no_synchronous_disk_io_in_audio_clock(self):
  worker=(N/'code/raw_audio_worker.mjs').read_text();self.assertNotIn('appendFileSync',worker);self.assertNotIn('writeFileSync',worker)
  self.assertIn('records.push(e)',worker)
 def test_supplement_registration_no_success_based_selection(self):
  cases=json.loads((N/'config/REPAIR_REGISTERED.json').read_text());self.assertEqual(len(cases),193);self.assertEqual(len({x['trial_uid']for x in cases}),193);self.assertNotIn('T6',{x['branch']for x in cases})
  self.assertEqual(sum(x['branch']=='T8'for x in cases),72)
  excluded=json.loads((N/'config/T8_NOT_SUPPORTED.json').read_text());self.assertEqual(len(excluded),48);self.assertTrue(all(x['case']['private_contract']['require_overlap']for x in excluded))
  self.assertTrue(all(set(x['repair_reasons'])<={'original_PCM_admission_failed','original_technical_error','entire_supported_T8_cohort_protocol_key_fix'}for x in cases))
if __name__=='__main__':unittest.main(verbosity=2)
