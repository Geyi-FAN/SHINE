import unittest,json,copy
from planner import validate,CATALOG,ENVELOPE,LEGEND,Planner
from execution_profile import policy_template,is_smol

def fixture(operation='return_bowl'):
    op=CATALOG[operation];raw='Return the bowl to its episode-start position, then open the middle drawer.'
    inp=dict(user_message=raw,physical_state=dict(held_object='bowl',drawers={'top':{'open':False}},native_goal_relations={}),reference_availability=[dict(op['reference'],available=True)])
    out=dict(status='plan_ready',complete_task=raw,remaining_plan=[dict(operation=operation,kind=op['kind'],object=op['object'],goal='return the bowl and release it stably')],current_subgoal_template=op['template'],reference=copy.deepcopy(op['reference']),policy_prompt_template=policy_template(raw,op),rationale='input facts',request=None)
    return inp,out

class Tests(unittest.TestCase):
    def test_valid_return(self):self.assertEqual(validate(*fixture()),[])
    def test_missing_point(self):
        i,o=fixture();i['reference_availability'][0]['available']=False;self.assertTrue(validate(i,o))
    def test_time_source(self):
        i,o=fixture();o['reference']['time_source']='instruction_takeover';self.assertTrue(validate(i,o))
    def test_missing_legend(self):
        i,o=fixture();o['policy_prompt_template']=o['policy_prompt_template'].replace('Coordinates: MAIN, 256x256, <y,x> pixels.\n' if is_smol() else LEGEND,'');self.assertTrue(validate(i,o))
    def test_raw_task_preserved(self):
        i,o=fixture();o['complete_task']='Return bowl';self.assertTrue(validate(i,o))
    def test_no_script_substitution(self):
        i,o=fixture();o['reference']['keypoint']='K1';before=copy.deepcopy(o);validate(i,o);self.assertEqual(o,before)
    def test_already_held_grasp(self):self.assertTrue(validate(*fixture('grasp_bowl')))
    def test_wrong_held_placement(self):self.assertTrue(validate(*fixture('cheese_bowl')))
    def test_closed_drawer_place(self):self.assertTrue(validate(*fixture('bowl_drawer')))
    def test_blocked_has_no_actions(self):
        i,o=fixture();o['status']='need_observation';self.assertTrue(validate(i,o))
    def test_valid_missing_request(self):
        i,o=fixture();o.update(status='need_observation',reference=None,current_subgoal_template=None,policy_prompt_template=None,request='Need bowl initial point');self.assertEqual(validate(i,o),[])
    def test_unknown_operator(self):
        i,o=fixture();o['remaining_plan'][0]['operation']='oracle_next_stage';self.assertTrue(validate(i,o))
    def test_oracle_next_answer_rejected_at_boundary(self):
        p=object.__new__(Planner)
        with self.assertRaises(AssertionError):p.generate(dict(user_message='x',oracle_next_subgoal='open drawer'))
    def test_contract_rejected_at_boundary(self):
        p=object.__new__(Planner)
        with self.assertRaises(AssertionError):p.generate(dict(user_message='x',task_contract_text='hidden answer'))

if __name__=='__main__':unittest.main()
