import unittest
from unified.terminal_feedback import CompletionReceiptWindow


class CompletionReceiptTests(unittest.TestCase):
    def test_polling_does_not_replace_physical_observations(self):
        guard=CompletionReceiptWindow()
        for _ in range(100):result=guard.observe(('episode','task',1,4),100,True)
        self.assertFalse(result['ready'])
        self.assertEqual(result['consecutive_verified_physics_frames'],1)

    def test_forty_real_current_verified_observations_required(self):
        guard=CompletionReceiptWindow()
        for frame in range(100,139):self.assertFalse(guard.observe(('e','t',1,4),frame,True)['ready'])
        self.assertTrue(guard.observe(('e','t',1,4),139,True)['ready'])
        self.assertFalse(guard.observe(('e','new-task',1,5),140,True)['ready'])

    def test_lost_verification_and_missing_frames_restart_window(self):
        guard=CompletionReceiptWindow()
        for frame in range(40):guard.observe(('e','t'),frame,True)
        self.assertFalse(guard.observe(('e','t'),40,False)['ready'])
        self.assertEqual(guard.observe(('e','t'),41,True)['consecutive_verified_physics_frames'],1)
        self.assertEqual(guard.observe(('e','t'),43,True)['consecutive_verified_physics_frames'],1)
