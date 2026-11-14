import unittest
from continuation.qa_snapshot_audit import answer_status
class SnapshotMeaning(unittest.TestCase):
 def test_held_above_stove_is_not_placed(self):self.assertEqual(answer_status('碗仍在夹爪中，悬于炉灶上方。',True,False,True),'pass')
 def test_placed_claim_when_held_is_failure(self):self.assertEqual(answer_status('碗在炉灶加热盘上，未见夹爪夹持。',True,False,True),'fail')
 def test_supported_released_placement(self):self.assertEqual(answer_status('碗已放在炉灶上。',False,True,False),'pass')
 def test_unreleased_object_is_not_confirmed_placed(self):self.assertNotEqual(answer_status('碗已经放在炉灶上。',True,True,True),'pass')
 def test_unknown_does_not_count_as_pass(self):self.assertEqual(answer_status('可能是抓取，也可能是放下。',True,False,True),'unknown')
if __name__=='__main__':unittest.main()
