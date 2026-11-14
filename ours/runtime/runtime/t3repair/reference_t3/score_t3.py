"""Independent T3 physical contracts; never trusts a planner's completed label."""
from control_order import command_step,action_after
import json,re
from pathlib import Path
from score_preflight import lines,conjunction,status
from score_dev96 import execution_events,audible_records
from score_t1 import physical_verdict
from t1_contract import instruction_goal
from t3_common import OBJECT_NAMES,dist,trigger_ready
from benchmark_metrics.events import restore_window,restore_radius,high_releases,close_event,preservation_states

VERSION='audio-switch-t3-evidence-v1.2'
def goal_from_full(text):
    found=[]
    for part in re.split(r'[.;]|\bthen\b|\bfinally\b',text,flags=re.I):
        g=instruction_goal(part)
        if g is not None:found.append(g)
    return found[-1] if found else None

def semantic_checks(text,clauses,target):
    s=text.lower();result=[dict(name='accepted_final_target_matches',status=status(goal_from_full(text)==target))]
    need_restore=any(c['kind']=='restore_episode_start' for c in clauses)
    has_restore=bool(re.search(r'\breturn\b|\bput\b.{0,45}\bback\b',s))
    result.append(dict(name='restoration_request_preserved_without_added_return',status=status(has_restore==need_restore)))
    need_close=[c['joint'] for c in clauses if c['kind']=='close_event']
    for joint in ['top','middle']:
        detected=bool(re.search(r'\b(?:close|shut)\b.{0,20}\b'+joint+r'\b.{0,15}\bdrawer\b',s))
        result.append(dict(name='close_'+joint+'_meaning_matches',status=status(detected==(joint in need_close))))
    for c in clauses:
        if c['kind']=='preserve_position':
            obj=next(k for k,v in OBJECT_NAMES.items() if v==c['object']);words={'wine_bottle':r'(?:wine )?bottle','cheese':r'(?:cream )?cheese'}.get(obj,obj)
            ok=bool(re.search(r'\b(?:keep(?:ing|s)?|leav(?:e|ing)|maintain(?:ing|s)?|preserv(?:e|ing)).{0,35}'+words,s))
            result.append(dict(name='explicit_keep_'+obj+'_transmitted',status=status(ok)))
        if c['kind'] in ('preserve_binary_state','preserve_predicate_state'):
            ok='stove' in s and bool(re.search(r'keep(?:ing|s)?|leav(?:e|ing)|maintain(?:ing|s)?|without chang|unchanged',s))
            result.append(dict(name='explicit_stove_state_preserved_in_task',status=status(ok)))
    return result

def physical(ticks,spec,newids,accept,deadline,rules):
    target,instruction,checks=physical_verdict(ticks,spec['target_task'],newids,accept,deadline,rules)
    active=[t for t in ticks if accept<=t['time']<=deadline]
    if not active:return 'fail','fail',[dict(name='physical_trace_after_acceptance',status='fail')]
    anchor=active[0];first_events={};first_hit=next((t for t in active if t['policy_action'] and t['task_id'] in newids and t['physical']['native_goal_relations'].get(__import__('t1_contract').GOALS[spec['target_task']][0])),None)
    if first_hit:first_events['target']=first_hit['step']
    clauses=spec['private_judge']['clauses']
    def add(name,value,**evidence):checks.append(dict(name=name,status=status(value),**evidence))
    for clause in clauses:
        kind=clause['kind'];cid=clause['id']
        if kind=='restore_episode_start':
            obj=next(k for k,v in OBJECT_NAMES.items() if v==clause['object'])
            ref=anchor['episode_initial_positions'][clause['object']]
            description=dict(clause,reference_position=ref,stable_required=clause.get('stable_required',False),withdraw_required=clause.get('withdraw_required',False))
            radius=restore_radius(dict(source_task=spec['source_task'],previous_instruction=spec['source_text']),description,rules)
            frames=[t['measurements'][obj] for t in active]
            for i,t in enumerate(active):
                if restore_window(frames[max(0,i-39):i+1],description,radius,rules)['complete']:
                    first_events[cid]=t['step'];break
            add(cid+'_returned_released',cid in first_events,first_step=first_events.get(cid),radius_m=radius)
            add(cid+'_no_high_unsupported_release',not high_releases(frames,ref,rules))
        elif kind=='close_event':
            joint=clause['joint'];qs=[t['measurements']['bowl']['articulation'][joint] for t in active]
            ending=close_event(qs,rules)
            if ending is not None:first_events[cid]=active[ending-1]['step']
            add(cid+'_event',ending is not None,first_step=first_events.get(cid),gap_m=rules['close']['gap_m'])
        elif kind=='preserve_position':
            obj=next(k for k,v in OBJECT_NAMES.items() if v==clause['object']);ref=anchor['measurements'][obj]['object_position']
            offsets=[dist(t['measurements'][obj]['object_position'],ref) for t in active];p=rules['preserve_position']
            states,onset=preservation_states(offsets,p['tolerance_m'],p['severe_m'],p['confirmation_steps'])
            add(cid+'_position_preserved',bool(states) and states[-1] is True,max_displacement_m=max(offsets),violation_onset=onset)
        elif kind in ('preserve_binary_state','preserve_stove_state','preserve_predicate_state'):
            ref=anchor['physical']['native_goal_relations']['turn_on_stove']
            flags=[t['physical']['native_goal_relations']['turn_on_stove']==ref for t in active]
            add(cid+'_binary_state_preserved',all(flags),reference=ref)
        elif kind=='preserve_articulation_state':
            joint=clause['joint'];ref=anchor['measurements']['bowl']['articulation'][joint];p=rules['preserve_joint']
            values=[abs(t['measurements']['bowl']['articulation'][joint]-ref) for t in active]
            states,onset=preservation_states(values,p['tolerance_m'],p['severe_m'],p['confirmation_steps'])
            add(cid+'_joint_preserved',bool(states) and states[-1] is True,violation_onset=onset)
        elif kind not in ('native_target','completion_order'):
            checks.append(dict(name='unsupported_private_clause_'+kind,status='unknown'))
    for clause in clauses:
        if clause['kind']=='completion_order':
            before,after=first_events.get(clause['before']),first_events.get(clause['after'])
            add(clause['id'],before is not None and after is not None and before<after,before_step=before,after_step=after)
    return target,conjunction([c['status'] for c in checks]),checks

def evaluate(directory,spec,rules):
    file=directory/'result.json'
    if not file.exists():return dict(case_id=spec['case_id'],interaction='fail',target='fail',instruction='fail',failures=['missing_result'])
    r=json.loads(file.read_text());ticks=lines(directory/'recordings'/str(r.get('episode_id'))/'control_ticks.jsonl')
    events=execution_events(directory,r);audio=r.get('mode')!='text_tools_baseline';turn=next((t for t in r.get('turns',[]) if t['turn_id']=='U1'),None)
    checks=[dict(name='source_trigger_reached',status=status(r.get('precondition_validated',False)))]
    if not turn or not ticks:return dict(case_id=spec['case_id'],source_task=spec['source_task'],family=spec['family'],interaction='fail' if audio else 'na',target='fail',instruction='fail',checks=checks,physical_checks=[],failures=['source_or_switch_not_reached'],errors=r.get('errors',[]))
    start=turn.get('audio_started_wall',turn.get('time'));end=turn.get('audio_ended_wall',turn.get('time'))
    creates=[e for e in events if e['kind']=='task_instruction' and e['time']>=start and e.get('task_id')!=r.get('source_task_id')]
    ids={e.get('task_id') for e in creates};accept=creates[0]['time'] if creates else end
    accepted_text=creates[0].get('instruction','') if creates else ''
    checks+=semantic_checks(accepted_text,spec['private_judge']['clauses'],spec['target_task'])
    def add(name,value,**extra):checks.append(dict(name=name,status=status(value),**extra))
    add('exactly_one_new_task',len(creates)==1,created=len(creates))
    add('new_task_accepted_within_20s',bool(creates) and accept<=end+20)
    first=next((t for t in ticks if t['time']>=start and t['policy_action'] and t['task_id'] in ids),None)
    add('first_new_action_within_45s',first is not None and first['time']<=end+45)
    add('no_unrequested_waiting',not any(e['kind']=='deferred_scheduled' and e['time']>=start for e in events))
    accept_step=command_step(directory,creates[0],r['episode_id']) if creates else None
    add('old_plan_no_actions_after_new_acceptance',not any(t['task_id']==r.get('source_task_id') and action_after(t,creates[0],accept_step) for t in ticks) if creates else True)
    add('new_action_budget',sum(t['policy_action'] and t['task_id'] in ids for t in ticks)<=1200)
    if audio:
        messages=r.get('messages',[])
        plays=[m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and end<=m['time']<=end+10]
        add('actual_reply_audio_within_10s',bool(plays))
        stop_end=start+turn['stop_segment_end_s'];control=[e for e in events if e['time']>=start and (e['kind']=='task_paused' or e in creates)]
        effect=next((e for e in control if e['time']<=stop_end+5),None)
        add('stop_or_retarget_effect_within_5s_segment_proxy',effect is not None,latency_s=None if effect is None else effect['time']-stop_end,clock='isolated_Stop_segment_end_proxy_not_human_word_timestamp')
        add('no_source_actions_after_stop_deadline',not any(t['policy_action'] and t['task_id']==r.get('source_task_id') and t['time']>stop_end+5 for t in ticks))
        add('no_user_unrequested_old_resume',not any(e['kind']=='task_resumed' and e['time']>=start and e.get('task_id')==r.get('source_task_id') for e in events))
    source_events=[e for e in events if e['kind']=='task_instruction' and e['time']<start]
    add('one_correct_source_task',len(source_events)==1 and goal_from_full(source_events[0].get('instruction',''))==spec['source_task'])
    trigger=r.get('trigger_tick');initial=r.get('initial_tick')
    if trigger and initial:
        source_actions=sum(t['policy_action'] and t['task_id']==r.get('source_task_id') and t['time']<=trigger['time'] for t in ticks)
        add('independent_trigger_predicate',trigger_ready(spec,trigger,r.get('source_task_id'),source_actions,initial,rules))
    else:add('independent_trigger_predicate',False)
    add('all_post_switch_actions_within_1200_budget',sum(bool(t['policy_action']) for t in ticks if t['time']>=start)<=1200)
    add('case_actions_within_3600_budget',sum(bool(t['policy_action']) for t in ticks)<=3600)
    beginning=r.get('started',{});finishing=r.get('finished',{})
    began_time=beginning.get('time') if isinstance(beginning,dict) else beginning
    add('case_wall_within_1800_seconds',began_time is not None and finishing.get('time',float('inf'))-began_time<=1800)
    voice_evidence=[e for f in (directory/'voice/sessions').glob('*.jsonl') for e in lines(f)]
    observed_until=r.get('finished',{}).get('time',end+600)
    fatal_voice=[e for e in voice_evidence if start<=e.get('ts',0)/1000<=observed_until and e.get('type')=='error' and e.get('payload',{}).get('fatal') is True]
    failed_holds=[e for e in events if accept<=e['time']<=observed_until and e['kind']=='control_hold' and e.get('reason')=='voice_call_failed']
    add('no_fatal_voice_loss_before_end_of_observation',not fatal_voice and not failed_holds,errors=[e.get('payload',{}).get('code') for e in fatal_voice])
    target,instruction,pchecks=physical(ticks,spec,ids,accept,end+600,rules)
    claims=[]
    if audio:
        voice=[e for f in (directory/'voice/sessions').glob('*.jsonl') for e in lines(f)]
        for event,play in audible_records(voice,r.get('messages',[])):
            if play['time']<start:continue
            text=event.get('payload',{}).get('text','')
            if re.search(r'任务已完成|当前任务已完成|已经完成任务|\b(?:task (?:is |has been )?completed|task is done|finished the task)\b',text,re.I):
                subset=[t for t in ticks if t['time']<=play['time']]
                _,v,_=physical(subset,spec,ids,accept,min(end+600,play['time']),rules)
                claims.append(dict(kind='complete',text=text,time=play['time'],status=v))
            elif re.search(r'任务指令已下发|已开始执行|已经开始执行|任务已开始|\b(?:starting|started) (?:the |your )?task\b',text,re.I):
                claims.append(dict(kind='accepted',text=text,time=play['time'],status=status(bool(creates) and accept<=play['time'])))
            elif re.search(r'已暂停|已经暂停|已停止|已经停止|\b(?:paused|stopped)\b',text,re.I):
                effects=[e for e in events if start<=e['time']<=play['time'] and (e['kind']=='task_paused' or e in creates)]
                claims.append(dict(kind='old_task_stopped',text=text,time=play['time'],status=status(bool(effects))))
        checks.append(dict(name='spoken_factual_receipts_match_evidence',status=conjunction([c['status'] for c in claims]),claims=claims))
    def source_at(when):
        previous=[t for t in ticks if t['time']<=when]
        if not previous:return None
        t=previous[-1];return dict(step=t['step'],mode=t['mode'],source_task_still_current=t['task_id']==r.get('source_task_id'),source_goal=t['physical']['native_goal_relations'].get(__import__('t1_contract').GOALS[spec['source_task']][0]))
    stops=[e for e in events if start<=e['time'] and (e['kind']=='task_paused' or e in creates)]
    diagnostics=dict(at_voice_onset=source_at(start),at_stop=source_at(stops[0]['time']) if stops else None,at_new_acceptance=source_at(accept) if creates else None)

    if not creates:target=instruction='fail'
    return dict(case_id=spec['case_id'],source_task=spec['source_task'],target_task=spec['target_task'],family=spec['family'],variant=spec['variant'],
                interaction=conjunction([c['status'] for c in checks]) if audio else 'na',target=target,instruction=instruction,
                checks=checks,physical_checks=pchecks,failures=[c['name'] for c in checks+pchecks if c['status']!='pass'],
                errors=r.get('errors',[]),spoken_claims=claims,source_timing_diagnostics=diagnostics,accepted_instruction=accepted_text,source_completed_during_audio=r.get('source_completed_during_audio'),
                source_active_at_acceptance=r.get('source_active_at_acceptance'),scoring_version=VERSION,
                final_status=r.get('final',{}).get('state'),controller_completed_used_as_success=False)
