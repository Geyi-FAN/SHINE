import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import shutil

W = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('voice_profile_tested', W/'tools/voice_profile.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class VoiceProfileTests(unittest.TestCase):
    def test_missing_waiting_receipt_refuses_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'candidate'
            shutil.copytree(W / 'config', root / 'config')
            for path in (root / 'config/receipt_seed').glob('*.json'):
                if json.loads(path.read_text()).get('transcript') == '已排队。':
                    path.unlink()
            with self.assertRaisesRegex(ValueError, 'Required verified receipt audio missing'):
                module.activate(root, Path(tmp) / 'output')

    def test_shared_activation_and_immutable_receipt_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'voice_run'
            env = module.activate(W, out)
            self.assertEqual(env['ROBOT_FAST_STOP'], '1')
            self.assertEqual(env['ROBOT_BOUNDED_RESULT_SPEECH'], '1')
            self.assertEqual(env['ROBOT_AUDIO_RELISTEN'], '1')
            self.assertEqual(env['ROBOT_AUDIO_GROUNDING_STREAM'], '1')
            self.assertTrue(Path(env['ROBOT_INSTRUCTION_PROMPT_FILE']).is_file())
            self.assertEqual(Path(env['ROBOT_RECEIPT_AUDIO_DIR']).parent, out)
            identity = json.loads((out/'VOICE_PROFILE.json').read_text())
            self.assertFalse(identity['asr_reference_text_sent'])
            self.assertFalse(identity['asr_scene_sent'])
            with self.assertRaises(FileExistsError):
                module.activate(W, out)
