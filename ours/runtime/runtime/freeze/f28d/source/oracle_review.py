"""Shadow reference on the SAME actual trajectory; never returns data to Planner.

This is not an independent Oracle-policy rollout and never substitutes an Agent
decision. Canonical plan-only/rewritten clauses can differ from raw user words.
"""
import json,os
from pathlib import Path
from benchmark_execution.no_timeouts import ExecutionController
from sym_geometry import Grounder
from sym_contract import fill,prompt

class ShadowOracle:
    def __init__(self,env,case,contract,rules,initial,budget):
        p=Path(os.environ.get('HYBRID_PLANS_FILE','/mnt/disk_2/geyi/pi05_small722_20261016/storage/data/mini_plans.json'))
        self.plan=json.loads(p.read_text())[case['case_id']]
        self.grounder=Grounder(env,self.plan)
        guards=self.grounder.measure()[0]
        self.executor=ExecutionController(case,contract,self.plan,rules,initial['articulation'],guards,budget)
    def observe(self,row):self.executor.observe(row,self.grounder.measure()[0])
    def stage(self):
        i=self.executor.index
        return dict(index=i,stage=self.plan['stages'][i])
    def snapshot(self,step):
        points,valid,_,_=self.grounder.points();i=self.executor.index
        return dict(step=step,mode='read-only shadow oracle on Agent trajectory',
                    index=i,stage=self.plan['stages'][i],
                    oracle_subgoal=fill(self.plan['stages'][i]['grounded'],points,valid),
                    oracle_prompt=prompt(self.plan,'V3R',i,points,valid),
                    full_oracle_plan=self.plan['stages'],oracle_full_task=self.plan['task'])
