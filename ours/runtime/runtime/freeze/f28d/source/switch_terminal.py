"""Causal Switch v2.5 final feedback. Simulator contract stays outside Agent."""
from benchmark_metrics import evaluate_episode
from benchmark_metrics.config import fingerprint
from terminal_gate import TARGET_OPERATORS

class SwitchTerminal:
    def __init__(self,case,contract,rules,initial):
        self.case,self.contract,self.rules,self.initial=case,contract,rules,initial
        self.expected=TARGET_OPERATORS[case['target_task']]
    def check(self,measurements,decision):
        plan=(decision or {}).get('remaining_plan',[])
        final=(len(plan)==1 and plan[0]['operation']==self.expected) or ((decision or {}).get('status')=='hold' and not plan)
        out=dict(frame=measurements[-1]['step'] if measurements else 0,passed=False,
                 source='switch_v25_instruction_adjusted_causal_prefix',final_agent_stage=final,
                 rules_sha256=fingerprint(self.rules),contract_sha256=fingerprint(self.contract))
        if not final or not measurements:return out
        current_target=measurements[-1].get('adjusted_goal',measurements[-1]['goal_frame']['goal'])
        if current_target is not True:
            out['current_target']=current_target
            return out
        # Evaluate the observed prefix only, never future evidence or next-stage answers.
        score=evaluate_episode(dict(measurements=measurements,metric_initial=self.initial),self.case,self.contract,self.rules)
        current_target=measurements[-1].get('adjusted_goal',measurements[-1]['goal_frame']['goal'])
        last={k:v['last_state'] for k,v in score['components'].items()
              if next(c['kind'] for c in self.contract['clauses'] if c['id']==k)!='native_target'}
        # `success` is EVER; require current target and current continuing constraints too.
        out.update(current_target=current_target,continuing_constraints=last,
                   instruction_adjusted=score['instruction_adjusted'],
                   passed=score['instruction_adjusted']['success'] is True and current_target is True and all(v is True for v in last.values()))
        return out
