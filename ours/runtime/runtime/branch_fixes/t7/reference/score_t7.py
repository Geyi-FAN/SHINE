"""Independent T7 judge: authored conversation, actual receipts/actions/physics."""
import json,re
from pathlib import Path
from score_preflight import lines,conjunction,status
from score_dev96 import execution_events,audible_records
from t7_physics import physical_verdict
from t1_contract import instruction_goal
from t7_support import ready

VERSION='audio-switch-t7-evidence-v2-causal-settling'

def judge_control(events,ticks,contract,turns,rules,finished,spoken):
    """Pure core allows tests of cancellations/races without a live server."""
    checks=[]
    def check(name,value,evidence=None):checks.append(dict(name=name,status=value if isinstance(value,str) else status(value),evidence=evidence))
    a=contract['predecessor_task_id'];b=contract['original_successor_task_id'];c=contract.get('replacement_task_id')
    branch=contract['branch'];start=turns[0]['audio_started_wall']
    events=[e for e in events if e['time']>=start]
    creates=[e for e in events if e['kind']=='task_instruction']
    source=[e for e in creates if instruction_goal(e.get('instruction',''))==a]
    check('one_correct_predecessor',len(source)==1,[e.get('instruction') for e in creates])
    aid=source[0].get('task_id') if source else None
    aactions=[t for t in ticks if t['time']>=start and t['policy_action'] and t['task_id']==aid]
    check('source_accepted_within_20s',bool(source) and source[0]['time']<=turns[0]['audio_ended_wall']+20)
    check('source_first_action_within_45s',bool(aactions) and aactions[0]['time']<=turns[0]['audio_ended_wall']+45)
    others=[t for t in ticks if t['time']>=start and t['policy_action'] and t['task_id']!=aid]
    first_other=others[0] if others else None
    cut=first_other['time'] if first_other else finished
    before=[t for t in ticks if start<=t['time']<cut] if first_other else [t for t in ticks if start<=t['time']<=cut]
    source_ready=next((before[i] for i in range(len(before)) if aactions and ready(before[max(0,i-4):i+1],a,rules)),None)
    schedules=[e for e in events if e['kind']=='deferred_scheduled']
    original=[e for e in schedules if instruction_goal(e.get('instruction',''))==b and e.get('predecessor_task_id')==aid]
    check('original_waiting_bound_to_source_once',len(original)==1,[dict(time=e['time'],instruction=e.get('instruction')) for e in schedules])
    if len(turns)>1:check('waiting_accepted_within_20s',bool(original) and original[0]['time']<=turns[1]['audio_ended_wall']+20)
    desired=a if branch=='C' else b if branch=='N' else c
    final_creates=[e for e in creates if instruction_goal(e.get('instruction',''))==desired and e.get('task_id')!=aid]
    final_ids={e.get('task_id') for e in final_creates}
    final_actions=[t for t in others if t['task_id'] in final_ids]
    source_failure=(source_ready is None and not others and bool(ticks) and ticks[-1].get('mode') in ['error','needs_review','budget_exhausted','cancelled']
                    and any(re.search(r'未完成|尚未完成|未能|耗尽|已停止|任务失败|failed|couldn.t|not completed|budget|stopped',text,re.I) for text in spoken))
    if branch=='C':
        cancel=[e for e in events if e['kind']=='deferred_invalidated' and e.get('reason')=='user_cancelled' and original and e.get('deferred_id')==original[0].get('deferred_id')]
        check('cancel_only_pending_successor',len(cancel)==1)
        if len(turns)>2:check('cancel_accepted_within_20s',bool(cancel) and cancel[0]['time']<=turns[2]['audio_ended_wall']+20)
        effective=cancel[0]['time'] if cancel else turns[2]['audio_ended_wall'] if len(turns)>2 else finished
        late=[t for t in others if t['time']>=effective]
        check('no_successor_started_after_cancel',not late,[dict(step=t['step'],task_id=t['task_id']) for t in late[:5]])
        check('no_active_task_cancelled_or_paused',not any(e['kind'] in ['task_cancelled','task_paused','episode_reset'] for e in events))
        both=max(source_ready['time'],turns[2]['audio_ended_wall']) if source_ready and len(turns)>2 else None
        check('post_cancel_observation_5s_or_truthful_source_failure',source_failure or both is not None and finished-both>=5)
    else:
        if branch=='R':
            new=[e for e in schedules if instruction_goal(e.get('instruction',''))==c and e.get('predecessor_task_id')==aid]
            replaced=[e for e in events if e['kind']=='deferred_invalidated' and e.get('reason')=='replaced_by_user' and original and e.get('deferred_id')==original[0].get('deferred_id')]
            check('replace_only_pending_successor_once',len(new)==1 and len(replaced)==1)
            if len(turns)>2:check('replacement_accepted_within_20s',bool(new) and new[0]['time']<=turns[2]['audio_ended_wall']+20)
        old_ids={e.get('task_id') for e in creates if instruction_goal(e.get('instruction',''))==b}
        cutoff=turns[2]['audio_ended_wall'] if branch=='R' and len(turns)>2 else start
        check('only_correct_successor_actions',all(t['task_id'] in final_ids or branch=='R' and t['task_id'] in old_ids and t['time']<cutoff for t in others))
        check('source_not_interrupted_or_restarted',not any(e['kind'] in ['task_paused','episode_reset','task_cancelled'] for e in events))
        check('successor_started_once_when_eligible',source_failure or len(final_creates)==1 and bool(final_actions))
        check('handoff_after_independent_source_completion',source_failure or source_ready is not None and final_actions and final_actions[0]['time']>=source_ready['time'])
        if source_ready and final_actions:
            authorization=turns[-1]['audio_ended_wall'];anchor=max(source_ready['time'],authorization)
            check('handoff_first_action_within_10s',final_actions[0]['time']<=anchor+10,dict(latency_s=final_actions[0]['time']-anchor))
        else:check('handoff_first_action_within_10s',source_failure)
    check('at_most_one_final_successor_creation',len(final_creates)<=1)
    return checks,dict(source_task_id=aid,source_ready=source_ready,final_task_ids={aid} if branch=='C' else final_ids,
                       source_failure_truthfully_blocked=source_failure,handoff_tested=bool(source_ready and final_actions),
                       final_goal=desired,creates=creates)

def evaluate(directory,spec,protocol):
    result_path=directory/'result.json'
    if not result_path.exists():return dict(case_id=spec['case_id'],category='T7',interaction='fail',target='fail',instruction='fail',checks=[],physical_checks=[],failures=['missing_result'])
    r=json.loads(result_path.read_text());turns=r.get('turns',[]);trace=lines(directory/'recordings'/str(r.get('episode_id'))/'control_ticks.jsonl')
    checks=[]
    def check(name,value,evidence=None):checks.append(dict(name=name,status=value if isinstance(value,str) else status(value),evidence=evidence))
    check('all_authored_user_turns_played',len(turns)==len(spec['turns']) and all(t['audio_sha256']==s['audio_sha256'] for t,s in zip(turns,spec['turns'])))
    if not turns or not trace:return dict(case_id=spec['case_id'],category='T7',branch=spec['branch'],interaction='fail',target='fail',instruction='fail',checks=checks,physical_checks=[],failures=['core_audio_or_physical_trace_unavailable'],runner_errors=r.get('errors',[]))
    rules=json.loads((Path(protocol['_dataset_dir'])/'physical_rules.json').read_text())
    events=execution_events(directory,r);messages=r.get('messages',[])
    voice=[e for path in (directory/'voice/sessions').glob('*.jsonl') for e in lines(path)]
    audible=audible_records(voice,messages);spoken=[e.get('payload',{}).get('text','') for e,p in audible]
    contract=dict(spec['private_contract'],branch=spec['branch'])
    core,info=judge_control(events,trace,contract,turns,rules,r['finished']['time'],spoken);checks.extend(core)
    check('queue_interaction_window_reached',r.get('precondition_validated',False))
    if spec['branch']!='N':check('pending_update_window_reached',bool(r.get('update_trigger')))
    for i,turn in enumerate(turns):
        end=turn['audio_ended_wall'];next_start=turns[i+1]['audio_started_wall'] if i+1<len(turns) else r['finished']['time']
        plays=[p for e,p in audible if end<=p['time']<=min(next_start,end+10)]
        check('audible_receipt_within_10s_'+turn['turn_id'],bool(plays),dict(latency_s=plays[0]['time']-end if plays else None))
    check('no_reset_inside_case',not any(e.get('kind')=='episode_reset' and e['time']>=turns[0]['audio_started_wall'] for e in events))
    check('case_wall_budget',r['finished']['monotonic']-r['started']['monotonic']<=1800)
    check('case_action_budget',sum(bool(t['policy_action']) for t in trace if t['time']>=turns[0]['audio_started_wall'])<=3600)
    check('per_goal_action_budget',all(sum(bool(t['policy_action']) and t['task_id']==tid for t in trace)<=1200 for tid in {info['source_task_id'],*info['final_task_ids']} if tid))
    final=info['final_goal'];ids=info['final_task_ids'];start=turns[0 if spec['branch']=='C' else -1]['audio_started_wall']
    anchor=turns[0]['audio_ended_wall'] if spec['branch']=='C' else (info['source_ready']['time'] if info['source_ready'] else turns[-1]['audio_ended_wall'])
    target,terminal,physical=physical_verdict(trace,final,ids,start,min(r['finished']['time'],anchor+600),rules)
    order=spec['branch']=='C' or info['source_ready'] is not None and all(t['time']>=info['source_ready']['time'] for t in trace if t['policy_action'] and t['task_id'] in ids)
    physical.append(dict(name='predecessor_completed_and_sequence_correct',status=status(bool(info['source_ready']) and order)))
    if spec['branch']=='C':
        physical.append(dict(name='cancelled_successor_never_executed',status=next(c['status'] for c in checks if c['name']=='no_successor_started_after_cancel')))
        physical.append(dict(name='requested_cancel_committed',status=next(c['status'] for c in checks if c['name']=='cancel_only_pending_successor')))
    if spec['branch']=='R':
        physical.append(dict(name='only_replacement_executed',status=next(c['status'] for c in checks if c['name']=='only_correct_successor_actions')))
        physical.append(dict(name='requested_replacement_committed',status=next(c['status'] for c in checks if c['name']=='replace_only_pending_successor_once')))
    claims=[]
    for e,p in audible:
        text=e.get('payload',{}).get('text','');time=p['time']
        if time<turns[0]['audio_started_wall']:continue
        prior=[x for x in events if x['time']<=time]
        if re.search(r'已(?:经)?取消|cancelled|canceled',text,re.I):
            claims.append(dict(kind='cancel',text=text,time=time,status=status(any(x['kind']=='deferred_invalidated' and x.get('reason')=='user_cancelled' for x in prior))))
        elif re.search(r'已安排|已排队|等待任务已|scheduled|queued',text,re.I) and not re.search(r'未|没有|not |cannot|couldn',text,re.I):
            claims.append(dict(kind='scheduled',text=text,time=time,status=status(any(x['kind']=='deferred_scheduled' for x in prior))))
        elif re.search(r'任务已完成|当前任务已完成|task (?:is |has been )?completed|task is done|finished the task',text,re.I):
            before=[t for t in trace if t['time']<=time]
            # Do not use an old successful A to justify "completed" while a
            # different current task is still unfinished.
            current=[x for x in prior if x['kind']=='task_instruction']
            claimed_goal=instruction_goal(current[-1].get('instruction','')) if current else None
            supported=claimed_goal is not None and ready(before,claimed_goal,rules)
            claims.append(dict(kind='complete',text=text,time=time,status=status(supported)))
    check('spoken_factual_receipts_match_evidence',conjunction([c['status'] for c in claims]),claims)
    instruction=conjunction([c['status'] for c in physical])
    return dict(case_id=spec['case_id'],category='T7',branch=spec['branch'],group=spec['group'],variant=spec['variant'],
                interaction=conjunction([c['status'] for c in checks]),target=target,instruction=instruction,
                checks=checks,physical_checks=physical,spoken_claims=claims,source_ready_time=info['source_ready']['time'] if info['source_ready'] else None,
                handoff_tested=info['handoff_tested'],source_failure_truthfully_blocked=info['source_failure_truthfully_blocked'],
                failures=[c['name'] for c in checks+physical if c['status']!='pass'],runner_errors=r.get('errors',[]),
                controller_completed_used_as_success=False,scoring_version=VERSION)
