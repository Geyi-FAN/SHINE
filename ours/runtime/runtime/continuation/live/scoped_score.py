"""Runtime verification scope for 'keep at returned position afterward'.

Uses unchanged physical windows/tolerances. Never edits logged measurements or
feeds this private scoring information back as a plan or a point.
"""
import copy,math

def score(bridge):
    from benchmark_metrics.events import preservation_states
    clauses=bridge.contract['clauses'];scoped=[c for c in clauses if c.get('activation_after')]
    core=copy.deepcopy(bridge.contract);core['clauses']=[c for c in core['clauses']if not c.get('activation_after')]
    result=bridge.authority.extensions.evaluate_episode(dict(measurements=bridge.measurements,metric_initial=bridge.initial),bridge.case,core,bridge.rules)
    for c in scoped:
        onset=result.get('completion_events',{}).get(c['activation_after'])
        values=[]
        if onset is not None:
            for row in bridge.measurements[max(0,onset-1):]:
                p=row['source'].get('all_object_poses',{}).get(c['object'],{}).get('position')
                values.append(None if p is None else math.dist(p,c['reference_position']))
        r=bridge.rules['preserve_position'];states,violation=preservation_states(values,r['tolerance_m'],r['severe_m'],r['confirmation_steps'])
        current=states[-1]if states else None
        result.setdefault('components',{})[c['id']]=dict(last_state=current,success=current is True,activation_event=c['activation_after'],activation_step=onset,violation_onset=violation)
        for metric in ['instruction_native','instruction_adjusted']:
            entry=result[metric];entry.setdefault('clauses_at_evaluation_step',{})[c['id']]={'value':current}
            if current is not True:entry['success']=False;entry['status']='fail'if current is False else'unknown'
    from unified.final_release import evidence
    result['final_release_evidence']=evidence(bridge)
    result['runtime_contract_source']='selected_public_instruction_not_evaluation_case';return result
