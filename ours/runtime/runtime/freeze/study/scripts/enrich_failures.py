"""Add human-readable Agent/phase/metric evidence without touching raw results."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parents[1]


def load(p):return json.loads(p.read_text())if p.exists()else None
def last_lines(p,count=3):
    if not p.exists():return[]
    with p.open('rb')as stream:
        stream.seek(max(0,p.stat().st_size-32768));data=stream.read().decode(errors='replace').splitlines()[-count:]
    out=[]
    for line in data:
        try:out.append(json.loads(line))
        except ValueError:pass
    return out


def enrich():
    details=[]
    for p in(ROOT/'runs/agent').glob('*/result.json'):
        d=load(p);score=(d.get('metrics')or{}).get('instruction_adjusted',{}).get('success')
        normal=score is True and d['status']=='switch_oracle_contract_completed'
        if normal:continue
        calls=load(p.parent/'agent_calls.json')or[]
        latest=calls[-1]if calls else{}
        answer=(latest.get('result')or{}).get('output')or{}
        first=(answer.get('remaining_plan')or[{}])[0]
        inputs=latest.get('input')or{}
        prompts=[]
        t=p.parent/'trace.json.gz'
        if t.exists():
            with gzip.open(t,'rt')as stream:trace=json.load(stream)
            prompts=[dict(start_step=x.get('start_step',x.get('step')),prompt=x.get('prompt'),prompt_token_length=x.get('prompt_token_length'))for x in trace.get('chunks',[])if x.get('prompt')]
        clauses=(d.get('metrics')or{}).get('instruction_adjusted',{}).get('clauses_at_evaluation_step',{})
        bad={k:v for k,v in clauses.items()if v.get('value')is False}
        pending=(d.get('selected_stages')or[{}])[-1]
        operation=pending.get('operation')or first.get('operation')
        reason='完整成功但未正常收尾：'+d['status']if score is True else'Agent请求澄清'if d['status']=='need_clarification'else'当前观测／位置证据不足'if d['status']=='need_observation'else'Agent输出未通过校验'if d['status']=='agent_validation_failed'else'原协议收尾时完整契约未通过'if d['status']=='benchmark_terminated'else'预算耗尽于'+str(operation)if d['status']=='budget_exhausted'else d['status']
        details.append(dict(case_id=d['case_id'],group=d.get('group'),full_instruction=d['public_full_instruction'],
            score=score,normal=normal,status=d['status'],reason=reason,actions=d.get('actions'),policy_calls=d.get('policy_calls'),
            agent_request=answer.get('request'),agent_rationale=answer.get('rationale'),last_agent_errors=[a.get('errors')for a in(latest.get('result')or{}).get('attempts',[])],
            selected_operation=operation,last_remaining_plan=answer.get('remaining_plan'),reference=answer.get('reference'),
            current_subgoal_template=answer.get('current_subgoal_template'),policy_prompt_template=answer.get('policy_prompt_template'),
            actual_first_policy_prompt=prompts[0]if prompts else None,actual_last_policy_prompt=prompts[-1]if prompts else None,
            current_observed_facts=inputs.get('physical_state'),reference_availability=inputs.get('reference_availability'),
            confirmed_events=d.get('execution_events'),stage_timeline=d.get('selected_stages'),
            failed_metric_clauses=bad,metric_diagnostics=(d.get('metrics')or{}).get('diagnostics'),
            oracle_events_for_audit_only=d.get('oracle_completion_events_for_scoring_only'),
            last_completion_observations=last_lines(p.parent/'completion_observations.jsonl',2),
            last_memory_events=last_lines(p.parent/'points/memory_events.jsonl',3),
            video=str(p.parent/'policy_input.mp4')if(p.parent/'policy_input.mp4').exists()else'',initial_main=str(p.parent/'points/0_current.png'),
            result=str(p),trace=str(t),agent_io=str(p.parent/'agent_calls.json'),oracle_reference=str(p.parent/'oracle_comparison.json')if(p.parent/'oracle_comparison.json').exists()else'',
            evidence_limit='日志说明失败环节；控制根因仍需结合视频。Oracle/metric evidence is offline audit only, never a runtime Agent input.'))
    (ROOT/'reports/FAILURE_DETAILS.json').write_text(json.dumps(dict(updated_unix=time.time(),cases=details),ensure_ascii=False,indent=2))
    if details:
        rows=[]
        for d in details:
            rows.append({k:json.dumps(v,ensure_ascii=False)if isinstance(v,(list,dict))else v for k,v in d.items()if k not in ['last_completion_observations','last_memory_events','current_observed_facts','reference_availability','oracle_events_for_audit_only']})
        with(ROOT/'reports/failure_details.csv').open('w',newline='')as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return len(details)


def main():
    p=argparse.ArgumentParser();p.add_argument('--watch',action='store_true');a=p.parse_args();last=None
    while True:
        progress=load(ROOT/'PROGRESS.json')or{}
        stamp=progress.get('updated_unix')
        if stamp!=last:
            print(json.dumps(dict(enriched_non_success_cases=enrich()),ensure_ascii=False),flush=True);last=stamp
        if not a.watch or progress.get('arms',{}).get('agent',{}).get('valid')==308:break
        time.sleep(45)


if __name__=='__main__':main()
