import unittest,numpy as np
from response_memo import fingerprint,ResponseMemo
class Tests(unittest.TestCase):
 def test_dict_order_does_not_change_key(self):self.assertEqual(fingerprint({'x':1,'y':2}),fingerprint({'y':2,'x':1}))
 def test_wrist_or_state_or_rng_changes_key(self):
  a=dict(main=np.zeros((2,2,3),np.uint8),wrist=np.zeros((2,2,3),np.uint8),state=np.zeros(8,np.float32),rng=np.array([0,1],np.uint32))
  for field in ['wrist','state','rng']:
   b={k:v.copy() for k,v in a.items()};b[field].flat[0]=1
   self.assertNotEqual(fingerprint(a),fingerprint(b))
 def test_array_dtype_is_not_ignored(self):self.assertNotEqual(fingerprint(np.array([1],np.float32)),fingerprint(np.array([1],np.float64)))
 def test_returned_arrays_do_not_mutate_saved_output(self):
  m=ResponseMemo();m.put('x',{'actions':np.ones((10,7))});m.get('x')['actions'][0,0]=99;self.assertEqual(m.get('x')['actions'][0,0],1)
 def test_different_request_has_no_response(self):
  m=ResponseMemo();m.put('old',{'actions':[1]});self.assertIsNone(m.get('new'))
if __name__=='__main__':unittest.main()
