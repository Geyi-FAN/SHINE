import copy
import unittest
from benchmark_metrics.config import load_rules,validate,fingerprint
from benchmark_metrics.evaluator import evaluate_episode
from benchmark_metrics.predicates import region_contains
from benchmark_metrics.events import restore_window,high_releases,preservation_states
from benchmark_metrics.cli import aggregate
from benchmark_metrics.controller import grasp_handover


def frame(step,goal=False,q=-.1,phase='policy'):
    source={'object_position':[0,0,0],'all_object_poses':{'bowl':{'position':[0,0,0]}},
            'support_contact':True,'target_contact':False,'eef_position':[0,0,.1],
            'articulation':{'top':q}}
    return {'step':step,'phase':phase,'source':source,'goal_frame':{'goal':goal}}

def target():return {'id':'target','kind':'native_target','source':'case.instruction'}
def close():return {'id':'close','kind':'close_event','joint':'top','source':'case.instruction'}
def order():return {'id':'order','kind':'completion_order','before':'close','after':'target','source':'case.instruction'}
def restore():return {'id':'restore','kind':'restore_episode_start','object':'bowl','reference_position':[0,0,0],
                      'stable_required':True,'withdraw_required':False,'source':'case.instruction'}
def run(frames,clauses,case=None,extra=None):
    return evaluate_episode(dict({'measurements':frames},**(extra or {})),case or {'case_id':'test'},
                            {'case_id':'test','clauses':clauses})
class Metrics(unittest.TestCase):
    def setUp(self):self.rules=load_rules()
    def test_target_transient_not_revoked(self):
        r=run([frame(1,True),frame(2)], [target()]);self.assertTrue(r['target_native']['success']);self.assertTrue(r['instruction_native']['success'])
    def test_hold_ignored(self):
        r=run([frame(1),frame(2,True,phase='hold')],[target()]);self.assertFalse(r['target_native']['success'])
    def test_missing_region_is_unknown(self):
        r=run([frame(1)],[target()],{'case_id':'test','target_task':9});self.assertIsNone(r['target_adjusted']['success'])
    def test_native_success_survives_expansion(self):
        r=run([frame(1,True)],[target()],{'case_id':'test','target_task':9});self.assertTrue(r['target_adjusted']['success'])
    def test_region_boundaries_and_contact(self):
        e={'local_position':[0,.026,.01],'lower':[-.1,-.022,-.002],'upper':[.1,.022,.1],'parent_contact_required':True,'parent_contact':True}
        self.assertTrue(region_contains(e,[0,.005,0]));e['parent_contact']=False;self.assertFalse(region_contains(e,[0,.005,0]))
        e['parent_contact']=True;e['local_position'][1]=.027;self.assertFalse(region_contains(e,[0,.005,0]))
    def test_close_order(self):
        fs=[frame(i,q=0,goal=i==6) for i in range(1,7)];r=run(fs,[target(),close(),order()]);self.assertTrue(r['instruction_native']['success'])
    def test_initial_close_evidence(self):
        r=run([frame(1,True,q=0)],[target(),close(),order()],extra={'metric_initial':{'articulation':{'top':0}}})
        self.assertTrue(r['instruction_native']['success'])
    def test_initial_close_missing_not_false_failure(self):
        fs=[frame(i,goal=i==1,q=0) for i in range(1,7)];r=run(fs,[target(),close(),order()]);self.assertIsNone(r['instruction_native']['success'])
    def test_reopened_close_not_added_keep(self):
        fs=[frame(i,q=0 if i<=5 else -.1,goal=i==10) for i in range(1,11)];r=run(fs,[target(),close(),order()]);self.assertTrue(r['instruction_native']['success']);self.assertIsNotNone(r['diagnostics']['close']['reopen_onset'])
    def test_missing_containment_unknown(self):
        r=run([frame(1,True)],[target(),{'id':'keep','kind':'preserve_containment','source':'case.instruction'}]);self.assertIsNone(r['instruction_native']['success'])
    def test_preserve_pending_blocks(self):
        s,_=preservation_states([0,.026,.027,.028],.025,.05,3);self.assertEqual(s,[True,None,None,False])
    def test_preserve_unknown_is_not_erased(self):
        s,_=preservation_states([None,0,0],.025,.05,3);self.assertEqual(s,[None]*3)
    def test_after_success_diagnostics_not_revoke(self):
        keep={'id':'keep','kind':'preserve_position','object':'bowl','reference_position':[0,0,0],'source':'case.instruction'}
        fs=[frame(1,True),frame(2)];fs[1]['source']['all_object_poses']['bowl']['position']=[1,0,0]
        self.assertTrue(run(fs,[target(),keep])['instruction_native']['success'])
    def test_high_drop_not_rescued_by_landing(self):
        fs=[frame(i,goal=i==10) for i in range(1,11)]
        for i in [0,1]:fs[i]['source']['object_position']=[0,0,.1];fs[i]['source']['all_object_poses']['bowl']['position']=[0,0,.1];fs[i]['source']['support_contact']=False
        fs[0]['source']['target_contact']=True
        r=run(fs,[target(),restore()]);self.assertFalse(r['instruction_native']['success']);self.assertTrue(r['target_native']['success'])
    def test_low_release_not_high_drop(self):
        f=[frame(i)['source'] for i in range(1,5)];f[0]['target_contact']=True;f[0]['support_contact']=False;f[1]['support_contact']=False;f[0]['object_position']=[0,0,.019]
        self.assertEqual(high_releases(f,[0,0,0],self.rules),[])
    def test_contact_does_not_count_as_release(self):
        f=[frame(i)['source'] for i in range(1,6)];f[-1]['target_contact']=True
        self.assertFalse(restore_window(f,restore(),.035,self.rules)['complete'])
    def test_wrong_monitor_rejected(self):
        fs=[frame(1,True)];fs[0]['source']['all_object_poses']['bowl']['position']=[1,0,0]
        with self.assertRaises(ValueError):run(fs,[target(),restore()])
    def test_missing_contract_clause_not_ignored(self):
        r=run([frame(1,True)],[target(),{'id':'extra','kind':'future_clause','source':'case.instruction'}]);self.assertIsNone(r['instruction_native']['success'])
    def test_noncontiguous_rejected(self):
        with self.assertRaises(ValueError):run([frame(2)],[target()])
    def test_config_fingerprint_changes(self):
        other=copy.deepcopy(self.rules);other['close']['gap_m']=.009;self.assertNotEqual(fingerprint(other),fingerprint(self.rules))
    def test_invalid_windows(self):
        self.rules['restore']['support_min_true']=6
        with self.assertRaises(ValueError):validate(self.rules)
    def test_controller_not_latched(self):self.assertEqual(grasp_handover([True]*5+[False]*3,False,self.rules),'pause_and_reassess_grasp')
    def test_unknown_denominator_not_hidden(self):
        r=run([frame(1)],[target()],{'case_id':'test','target_task':9});s=aggregate([r])['target_adjusted'];self.assertIsNone(s['success_rate']);self.assertEqual(s['upper_bound'],1)
    def test_close_ten_mm_confirmed(self):
        fs=[frame(i,q=-.010,goal=i==6) for i in range(1,7)]
        self.assertTrue(run(fs,[target(),close(),order()])['instruction_native']['success'])
        fs=[frame(i,q=-.01001,goal=i==6) for i in range(1,7)]
        self.assertFalse(run(fs,[target(),close(),order()])['instruction_native']['success'])
    def test_contact_string_rejected(self):
        fs=[frame(1,True)];fs[0]['source']['support_contact']='false'
        with self.assertRaises(ValueError):run(fs,[target(),restore()])
    def test_joint_nan_rejected(self):
        keep={'id':'keep','kind':'preserve_articulation_state','joint':'top','reference_q':0,'source':'case.instruction'}
        with self.assertRaises(ValueError):run([frame(1,True,q=float('nan'))],[target(),keep])
    def test_contract_plan_clause_rejected(self):
        c=close();c['source']='plan.task'
        with self.assertRaises(ValueError):run([frame(1,True)],[target(),c])
if __name__=='__main__':unittest.main()
