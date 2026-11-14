"""Independent ten-goal T1 judging: private contract + physical/event evidence."""
import json,re
from pathlib import Path
from score_preflight import lines,conjunction,status
from score_dev96 import execution_events,audible_records
from benchmark_metrics.events import restore_window
from t1_contract import GOALS,instruction_goal,goal_flag

VERSION='audio-switch-t1-evidence-v1'


def physical_verdict(ticks,goal,authorized_ids,began,deadline,rules):
    active=[t for t in ticks if began<=t['time']<=deadline]
    flags=[goal_flag(t,goal) for t in active]
    hit=next((t for t,f in zip(active,flags) if f is True and t['policy_action'] and t['task_id'] in authorized_ids),None)
    target='unknown' if not flags or all(f is None for f in flags) else status(hit is not None)
    checks=[dict(name='target_in_authorized_policy_steps',status=target,first_step=hit['step'] if hit else None)]
    terminal=active[-40:]
    checks.append(dict(name='native_target_terminal_40_ticks',status=status(len(terminal)==40 and all(goal_flag(t,goal) is True for t in terminal))))
    obj=GOALS[goal][2]
    if obj:
        releases=[]
        for i in range(max(0,len(active)-40),len(active)):
            w=[t['measurements'][obj] for t in active[max(0,i-7):i+1] if obj in t.get('measurements',{})]
            releases.append(bool(w and restore_window(w,dict(reference_position=w[-1]['object_position'],stable_required=True,withdraw_required=False),1e6,rules)['complete']))
        checks.append(dict(name='released_supported_stable_terminal_40_ticks',status=status(len(releases)==40 and all(releases))))
    if goal==3:
        opened=next((t for t in active if t['physical']['drawers']['top']['open']),None)
        checks.append(dict(name='top_drawer_open_before_containment',status=status(bool(opened and hit and opened['step']<hit['step'])),
                           first_open_step=opened['step'] if opened else None))
    return target,conjunction([c['status'] for c in checks]),checks


def evaluate(directory,spec,protocol):
    p=directory/'result.json';goal=spec['private_contract']['target_task_id'];budgets=protocol['budgets']
    if not p.exists():return dict(case_id=spec['case_id'],interaction='fail',target='fail',instruction='fail',failures=['missing_result'],checks=[],physical_checks=[])
    r=json.loads(p.read_text());ticks=lines(directory/'recordings'/str(r.get('episode_id'))/'control_ticks.jsonl')
    turns=r.get('turns',[]);events=execution_events(directory,r);messages=r.get('messages',[])
    voice=[e for f in (directory/'voice/sessions').glob('*.jsonl') for e in lines(f)]
    checks=[]
    def check(name,value,evidence=None):checks.append(dict(name=name,status=value if isinstance(value,str) else status(value),evidence=evidence))
    check('precondition_validated',r.get('precondition_validated',False))
    check('exactly_one_user_audio_played',len(turns)==1 and turns[0].get('audio_sha256')==spec['audio_sha256'])
    if not turns or not ticks:
        return dict(case_id=spec['case_id'],interaction='fail',target='fail',instruction='fail',checks=checks,physical_checks=[],failures=['precondition_or_trace_unavailable'],runner_errors=r.get('errors',[]))
    turn=turns[0];start=turn['audio_started_wall'];end=turn['audio_ended_wall'];deadline=end+budgets['per_physical_goal_wall_s']
    relevant=[e for e in events if e['time']>=start]
    creates=[e for e in relevant if e['kind']=='task_instruction']
    accepted=[e for e in creates if instruction_goal(e.get('instruction',''))==goal]
    ids={e.get('task_id') for e in accepted}
    check('one_correct_full_task',len(creates)==1 and len(accepted)==1,[dict(task_id=e.get('task_id'),instruction=e.get('instruction'),time=e['time']) for e in creates])
    check('command_accepted_within_20s',bool(accepted) and accepted[0]['time']<=end+budgets['valid_command_accept_from_audio_end_s'])
    first=next((t for t in ticks if t['time']>=start and t['policy_action'] and t['task_id'] in ids),None)
    check('first_correct_action_within_45s',first is not None and first['time']<=end+budgets['first_new_action_from_audio_end_s'])
    check('no_unrequested_waiting',not any(e['kind']=='deferred_scheduled' for e in relevant))
    check('no_unrequested_pause_or_reset',not any(e['kind'] in {'task_paused','episode_reset'} for e in relevant))
    check('no_wrong_task_actions',not any(t['time']>=start and t['policy_action'] and t['task_id'] not in ids for t in ticks))
    check('goal_action_budget',sum(bool(t['policy_action']) for t in ticks if t['time']>=start)<=budgets['per_physical_goal_action_steps'])
    check('case_wall_budget',r['finished']['monotonic']-r['started']['monotonic']<=budgets['case_wall_s'])
    plays=[m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and end<=m['time']<=end+budgets['ack_from_audio_end_s']]
    check('actual_reply_audio_within_10s',bool(plays),dict(first_audio_latency_s=plays[0]['time']-end if plays else None))
    rules=json.loads((Path(protocol['_dataset_dir'])/'physical_rules.json').read_text())
    target,instruction,physical=physical_verdict(ticks,goal,ids,start,deadline,rules)
    # A printed completed flag is never proof. Check played claims at their real time.
    claims=[]
    for event,play in audible_records(voice,messages):
        if play['time']<start:continue
        text=event.get('payload',{}).get('text','');latest=[t for t in ticks if start<=t['time']<=play['time']]
        if re.search(r'任务已完成|当前任务已完成|已经完成任务|\b(?:task (?:is |has been )?completed|task is done|finished the task)\b',text,re.I):
            if latest:
                _,verdict,_=physical_verdict(latest,goal,ids,start,play['time'],rules)
                claims.append(dict(kind='complete',text=text,time=play['time'],status=verdict))
            else:claims.append(dict(kind='complete',text=text,status='unknown'))
        elif re.search(r'任务指令已下发|已开始执行|已经开始执行|任务已开始|\b(?:starting|started) (?:the |your )?task\b',text,re.I):
            okay=any(e['time']<=play['time'] for e in accepted)
            claims.append(dict(kind='accepted',text=text,time=play['time'],status=status(okay)))
    check('spoken_factual_receipts_match_evidence',conjunction([c['status'] for c in claims]),claims)
    return dict(case_id=spec['case_id'],category='T1',target_task_id=goal,goal=GOALS[goal][0],
                interaction=conjunction([c['status'] for c in checks]),target=target,instruction=instruction,
                checks=checks,physical_checks=physical,spoken_claims=claims,
                failures=[c['name'] for c in checks+physical if c['status']!='pass'],runner_errors=r.get('errors',[]),
                latency_clock='audio_end_proxy',controller_completed_used_as_success=False,scoring_version=VERSION)
