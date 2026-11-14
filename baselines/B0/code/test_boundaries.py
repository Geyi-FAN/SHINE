"""Counterfactual secret-field isolation and fixed-catalog integrity checks."""
import io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import raw_gateway as g
R=Path(__file__).resolve().parents[1]

class Boundaries(unittest.TestCase):
 def test_catalog_counts_and_seeds(self):
  items=json.loads((R/'data/FORMAL810.private.json').read_text());self.assertEqual(len(items),810);self.assertEqual(len({x['trial_uid']for x in items}),810)
  cases={}
  for x in items:cases.setdefault(x['case_uid'],[]).append(x)
  self.assertEqual(len(cases),330)
  for xs in cases.values():self.assertEqual(sorted(x['policy_seed']for x in xs),[7]if xs[0]['branch']=='T6'else[7,8,9])
 def test_policy_request_excludes_counterfactual_secrets(self):
  obs=dict(agentview_image=np.zeros((256,256,3),np.uint8),robot0_eye_in_hand_image=np.zeros((256,256,3),np.uint8),robot0_eef_pos=np.zeros(3),robot0_eef_quat=np.array([0.,0.,0.,1.]),robot0_gripper_qpos=np.zeros(2),oracle_next_subgoal='SECRET_CLOSE_THEN_RETURN',hidden_positions=np.ones(3)*987,private_target_task_id=6)
  class Reply:
   def __enter__(self):return io.BytesIO(json.dumps(dict(prompt='Stop.',actions=np.zeros((10,7)).tolist())).encode())
   def __exit__(self,*args):pass
  class Opener:
   def open(inner,request,timeout):
    with np.load(io.BytesIO(request.data),allow_pickle=False)as z:
     self.assertEqual(set(z.files),{'image','wrist','state','metadata'});m=json.loads(str(z['metadata']));self.assertEqual(m,dict(prompt='Stop.',evaluation_case_id='opaque_episode',evaluation_call_index=0,evaluation_seed=7));self.assertEqual(z['state'].shape,(8,));self.assertNotIn(b'SECRET',request.data);self.assertNotIn(b'oracle',request.data)
    return Reply()
  with patch('urllib.request.build_opener',return_value=Opener()):g.call_policy('http://127.0.0.1:1',obs,'Stop.','opaque_episode',0,7)
 def test_no_semantic_tools_in_actor(self):
  import ast
  module=ast.parse((R/'code/raw_gateway.py').read_text());imports=[n.module for n in ast.walk(module)if isinstance(n,ast.ImportFrom)and n.module]
  self.assertFalse(any(x.split('.')[0]in ['planner','oracle_kernel','oracle_points','voice_profile','grounding']for x in imports))
 def test_t6_never_retries_a_committed_question(self):
  import run_branches as runner
  with tempfile.TemporaryDirectory()as td:
   run=Path(td);calls=[]
   def attempt(item,run,port,index):
    calls.append(index);p=run/'cases'/'opaque_trial'/'preparation_attempts'/f'A{index:02d}';p.mkdir(parents=True)
    return dict(trial_uid='opaque_trial',directory=str(p),elapsed_seconds=1,status='client_finished',score=dict(asked=True,qa_success=False))
   with patch.object(runner,'run_attempt',side_effect=attempt):result=runner.run_case(dict(branch='T6'),run,1)
   self.assertEqual(calls,[1]);self.assertFalse(result['score']['qa_success'])
 def test_t6_retries_only_before_question_up_to_three(self):
  import run_branches as runner
  with tempfile.TemporaryDirectory()as td:
   run=Path(td);calls=[]
   def attempt(item,run,port,index):
    calls.append(index);p=run/'cases'/'opaque_trial'/'preparation_attempts'/f'A{index:02d}';p.mkdir(parents=True)
    return dict(trial_uid='opaque_trial',directory=str(p),elapsed_seconds=1,status='setup_unavailable',score=dict(asked=False,qa_success=None))
   with patch.object(runner,'run_attempt',side_effect=attempt):result=runner.run_case(dict(branch='T6'),run,1)
   self.assertEqual(calls,[1,2,3]);self.assertIsNone(result['score']['qa_success']);self.assertEqual(len(result['preparation_attempts']),3)

if __name__=='__main__':unittest.main(verbosity=2)
