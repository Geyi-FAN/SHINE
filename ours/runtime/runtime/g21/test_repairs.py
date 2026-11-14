import copy,gzip,importlib.util,json,sys,unittest
from pathlib import Path
from types import SimpleNamespace

B=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(B),str(B/'g2'),str(B/'freeze/authority_src')]
from g21.private_acceptance import CurrentContractAcceptance
from g21.observed_goal_guard import errors

def load_module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class AcceptanceTests(unittest.TestCase):
    def test_recorded_adjusted_goal_gets_current_acceptance_before_budget(self):
        root=Path('/mnt/disk_4/geyi/voice_f28d_G2_20261101/G2_natural8_v2/SW4_T04_M2_T05_SWITCH_T04_M2_S05')
        case=next(c for c in json.loads((B/'g2/fixed32.json').read_text())if c['case_id']==root.name)
        contract=json.loads((root/'natural_contract.json').read_text())
        with gzip.open(root/'gateway_trace.json.gz','rt')as f:trace=json.load(f)
        from benchmark_metrics.config import load_rules
        from metric_extensions import evaluate_episode
        protocol=load_module('g21_test_protocol',B/'freeze/authority_src/protocol.py');rules=load_rules();seen=[]
        score=lambda:evaluate_episode(dict(measurements=seen,metric_initial=trace['metric_initial']),case,contract,rules)
        controller=CurrentContractAcceptance(case,contract,rules,trace['metric_initial'],score,protocol.StopController(case,contract,rules))
        accepted=None
        for row in trace['measurements']:
            seen.append(row);accepted=controller.observe(row,('episode','task',1))
            if accepted:break
        self.assertIsNotNone(accepted);self.assertTrue(accepted['accepted']);self.assertFalse(accepted['native_goal'])
        self.assertTrue(controller.last_score['instruction_adjusted']['success'])
        self.assertLess(len(seen),len(trace['measurements']))
        old=json.loads((root/'result.json').read_text())
        self.assertLessEqual(accepted['score_step'],old['metrics']['instruction_adjusted']['first_step']+4)

    def controller(self,contract=None,score=None):
        contract=contract or {'clauses':[{'id':'target','kind':'native_target'}]}
        score=score or {'instruction_adjusted':{'success':True},'components':{}}
        return CurrentContractAcceptance({},contract,{}, {},lambda:score,SimpleNamespace(observe=lambda row:None))

    def test_past_success_does_not_accept_current_lost_target(self):
        c=self.controller();r=dict(step=1,adjusted_goal=False,goal_frame={'goal':False})
        self.assertIsNone(c.observe(r,('e','t',1)));self.assertFalse(c.finished)

    def test_unknown_current_invariant_cannot_accept(self):
        ct={'clauses':[{'id':'target','kind':'native_target'},{'id':'keep','kind':'preserve_position'}]}
        score={'instruction_adjusted':{'success':True},'components':{'keep':{'last_state':None}}}
        c=self.controller(ct,score);r=dict(step=1,adjusted_goal=True,goal_frame={'goal':False})
        self.assertIsNone(c.observe(r,('e','t',1)));self.assertFalse(c.finished)

    def test_different_task_cannot_use_old_acceptance(self):
        c=self.controller();c.subject=('e','old',1);r=dict(step=1,adjusted_goal=True,goal_frame={'goal':True})
        self.assertIsNone(c.observe(r,('e','new',1)));self.assertFalse(c.finished)

    def test_real_commit_is_once_and_version_bound(self):
        from bridge import SingleOwnerBridge
        b=object.__new__(SingleOwnerBridge);b.terminal_reason=None;b.acceptance_decision=None;events=[]
        b.state=SimpleNamespace(episode='e',task_id='t',task_intent_revision=1,version=2,mode='running')
        def hold(mode,reason):b.state.mode=mode;b.state.version+=1
        b.state._hold=hold;b.state.event=lambda kind,payload:events.append(kind);b.log=lambda *a,**kw:None
        decision=dict(subject=['e','t',1],accepted=True,reason='current_full_contract_accepted',schema='current-contract-stop-v1')
        self.assertFalse(b.commit_acceptance(dict(decision,subject=['e','old',1])))
        self.assertTrue(b.commit_acceptance(decision));self.assertFalse(b.commit_acceptance(decision))
        self.assertEqual(events,['task_completed']);self.assertEqual(b.state.mode,'completed')
        self.assertTrue(b.state.agent_execution['completion_current_verified'])

class ObservedGoalTests(unittest.TestCase):
    def recorded(self):
        root=Path('/mnt/disk_4/geyi/voice_f28d_G2_20261101/G2_natural8_v2/SW4_T02_M2_T08_SWITCH_T02_M2_S04/local_requests/planning')
        d=next(iter(sorted(root.iterdir())));req=json.loads((d/'request_original.json').read_text());body=req['messages'][1]['content']
        inp=json.loads(body)if isinstance(body,str)else json.loads(body[0]['text'])
        out=json.loads(json.loads((d/'response.json').read_text())['choices'][0]['message']['content'])
        return inp,out

    def test_actual_accepted_redundant_grasp_return_is_rejected(self):
        inp,out=self.recorded();saved=copy.deepcopy(out)
        self.assertEqual(inp['physical_state']['objects']['wine_bottle']['returned_and_released'],True)
        self.assertTrue(errors(inp,out));self.assertEqual(out,saved)

    def test_missing_false_stale_or_contradictory_evidence_is_not_completion(self):
        inp,out=self.recorded()
        for value in [None,False]:
            x=copy.deepcopy(inp);x['physical_state']['objects']['wine_bottle']['returned_and_released']=value
            self.assertFalse(errors(x,out))
        x=copy.deepcopy(inp);x['physical_state']['observed_step']-=1;self.assertFalse(errors(x,out))
        x=copy.deepcopy(inp);x['physical_state']['held_object']='wine_bottle';self.assertFalse(errors(x,out))

    def test_later_requested_transport_of_same_object_is_retained(self):
        inp,out=self.recorded();out=copy.deepcopy(out)
        out['remaining_plan']=[out['remaining_plan'][0],dict(operation='bottle_rack',kind='target',object='wine_bottle')]
        inp['user_message']='Return the wine bottle and release it, then put the wine bottle on the rack.'
        self.assertFalse(errors(inp,out))

    def test_explicit_grasp_request_is_not_silently_removed(self):
        inp,out=self.recorded();inp['user_message']='Pick up the wine bottle and return the wine bottle to its initial position.'
        self.assertFalse(errors(inp,out))

    def test_missing_point_for_satisfied_return_cannot_block_remaining_goal(self):
        inp,_=self.recorded()
        out=dict(status='need_observation',remaining_plan=[],request='Please confirm if the bottle is already at its episode_start.wine_bottle.K2 position.')
        self.assertTrue(errors(inp,out))
        out['request']='Please locate the current bowl K1 for grasping.'
        self.assertFalse(errors(inp,out))

if __name__=='__main__':unittest.main(verbosity=2)
