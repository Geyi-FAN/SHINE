"""Independent T5 scoring: audited user branches, events, and physical ticks."""
import json
import re
from pathlib import Path
from score_preflight import lines, conjunction, status
from score_dev96 import execution_events, audible_records
from score_t1 import physical_verdict
from t5_contract import instruction_goal

VERSION='audio-switch-t5-evidence-v3-pcm-f28d'

def question_kind(text):
    obj=bool(re.search(r'(?:which|what)\s+(?:object|item|one)|what.{0,35}(?:move|pick up|put)|哪(?:个|件)(?:物体|物品|东西|对象)|什么(?:物体|物品|东西)|哪一个|指的是(?:哪个|什么)|(?:指|移动|操作|拿|放).{0,12}哪(?:个|件)',text,re.I))
    dest=bool(re.search(r'\bwhere\b|\bdestination\b|放(?:到|在|进)?(?:哪|什么地方)|哪里|哪儿|目的地',text,re.I))
    if obj and dest:return 'both'
    if dest:return 'destination'
    if obj:return 'object'
    if re.search(r'what (?:would|do) you (?:like|want) me to do|what.{0,12}(?:complete|full) (?:task|request)|具体.{0,12}(?:做什么|任务)|完整.{0,8}(?:指令|任务)',text,re.I):return 'both'
    if re.search(r'确认|是否.{0,12}(?:执行|开始)|可以.{0,15}(?:执行|开始).{0,5}[吗？?]|\bconfirm|\b(?:shall|should|may|can) I\b|\b(?:do|would) you (?:want|like) me to|\b(?:approve|approval)\b',text,re.I):return 'confirmation'
    return None

def authorization_turn(spec,turns):
    family=spec['family_id']
    if family=='F10':return None
    if family in {'F01','F02','F03','F04'}:
        needed=set(spec['private_contract']['missing_slots']);latest=None
        for t in turns:
            key=t.get('answer_branch')
            if key in {'object','destination','both'}:
                needed-=({'object','destination'} if key=='both' else {key})
                if not needed:latest=t;break
        if latest is None:return None
        optional=next((t for t in turns if t.get('optional_confirmation') and t['audio_started_wall']>=latest['audio_started_wall']),None)
        return optional or latest
    suffix='_U02' if family in {'F07','F08'} else '_U03'
    return next((t for t in turns if t['turn_id'].endswith(suffix)),None)

def allowed_audio(spec):
    choices={t['utterance_id']:t['text'] for t in spec['turns']}
    choices.update({v['utterance_id']:v['text'] for v in spec.get('answer_branches',{}).values()})
    if spec.get('optional_confirmation'):
        v=spec['optional_confirmation'];choices[v['utterance_id']]=v['text']
    return choices

def evaluate_trace(r,spec,protocol,ticks,events,voice,rules):
    eligible=spec['private_contract']['physical_eligible'];goal=spec['private_contract']['target_task_id']
    turns=r.get('turns',[]);messages=r.get('messages',[]);checks=[];physical=[]
    def check(name,value,evidence=None):checks.append(dict(name=name,status=value if isinstance(value,str) else status(value),evidence=evidence))
    check('fresh_idle_precondition',r.get('precondition_validated',False))
    if not turns or not ticks:
        return dict(case_id=spec['case_id'],category='T5',interaction='fail',target='fail' if eligible else 'na',instruction='fail' if eligible else 'na',checks=checks,physical_checks=[],failures=['precondition_or_trace_unavailable'])
    b=protocol['budgets'];start=turns[0]['audio_started_wall'];end=r['finished']['time']
    ev=[e for e in events if start<=e['time']<=end]
    creates=[e for e in ev if e['kind']=='task_instruction']
    choices=allowed_audio(spec)
    check('only_authored_audio_and_matching_hashes',all(t.get('audio_id') in choices and t.get('text')==choices[t['audio_id']] and t.get('audio_sha256')==spec['audio_hashes'].get(t['audio_id']) for t in turns))
    check('all_required_user_turns_played',{t['turn_id'] for t in spec['turns']}<={t['turn_id'] for t in turns})
    check('all_dialogue_triggers_completed',not r.get('dialogue_error'),r.get('dialogue_error'))
    # Recompute actual audibility from raw logs, not from the runner's summary.
    spoken=audible_records(voice,messages)
    played=[m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started']
    for i,t in enumerate(turns):
        until=turns[i+1]['audio_started_wall'] if i+1<len(turns) else end
        responses=[m for m in messages if m.get('type')=='client.output_first_pcm' and t['audio_ended_wall']<=m['time']<=until]
        resolved=authorization_turn(spec,turns)
        authored_index=next((j for j,x in enumerate(spec['turns']) if x['turn_id']==t['turn_id']),None)
        next_trigger=spec['turns'][authored_index+1]['trigger'] if authored_index is not None and authored_index+1<len(spec['turns']) else ''
        needs_question=(bool(spec.get('answer_branches')) and (resolved is None or t['audio_started_wall']<resolved['audio_started_wall'])) or 'confirmation_question_actually_played' in next_trigger
        limit=b['clarification_question_from_audio_end_s'] if needs_question else b['ack_from_audio_end_s']
        check('actual_reply_'+t['turn_id'],bool(responses) and responses[0]['time']<=t['audio_ended_wall']+limit,
              dict(deadline_s=limit,latency_s=responses[0]['time']-t['audio_ended_wall'] if responses else None))
    for index,t in enumerate(turns[1:],1):
        proof=t.get('trigger_evidence',{})
        if t.get('answer_branch') or t.get('optional_confirmation') or t.get('confirmation') or t.get('requires_question'):
            play=next((m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_completed' and m.get('outputId')==proof.get('output_id') and m.get('epoch')==proof.get('epoch') and m['time']<=t['audio_started_wall']),None)
            check('answer_after_actual_question_'+t['turn_id'],bool(play and proof.get('question')),proof)
            previous=turns[index-1]
            onset=next((m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and m.get('outputId')==proof.get('output_id') and m.get('epoch')==proof.get('epoch')),None)
            check('useful_question_within_deadline_'+t['turn_id'],bool(onset and play and onset['time']<=previous['audio_ended_wall']+b['clarification_question_from_audio_end_s'] and play['time']<=previous['audio_ended_wall']+b['qa_complete_answer_from_audio_end_s']))
            text_matches=[e.get('payload',{}).get('text','') for e,m in spoken if m.get('outputId')==proof.get('output_id') and m.get('epoch')==proof.get('epoch')]
            kind=question_kind(proof.get('question',''))
            check('question_text_independently_bound_'+t['turn_id'],
                  'unknown' if not text_matches else status(any(re.sub(r'\W','',s.casefold())==re.sub(r'\W','',proof.get('question','').casefold()) for s in text_matches)))
            expected=t.get('answer_branch') or 'confirmation'
            check('answer_matches_question_kind_'+t['turn_id'],kind==expected,dict(actual_question_kind=kind,selected=expected))
    auth=authorization_turn(spec,turns)
    floor=auth['audio_started_wall'] if auth else float('inf')
    # No word-level timing exists: the whole confirmation must not be treated as
    # unavailable until its last sample. Bind to the actual accepted input/event.
    accepted=[e for e in creates if eligible and e['time']>=floor and instruction_goal(e.get('instruction',''))==goal]
    ids={e.get('task_id') for e in accepted}
    action=[t for t in ticks if start<=t['time']<=end and t['policy_action']]
    check('no_task_acceptance_before_information_and_consent',all(e['time']>=floor for e in creates))
    check('no_physical_action_before_information_and_consent',all(t['time']>=floor for t in action))
    check('no_unrequested_waiting',not any(e['kind']=='deferred_scheduled' for e in ev))
    check('no_reset_in_dialogue',not any(e['kind']=='episode_reset' for e in ev))
    check('case_action_budget',len(action)<=b['case_action_steps'])
    check('case_wall_budget',r['finished']['monotonic']-r['started']['monotonic']<=b['case_wall_s'])
    check('at_most_three_clarification_questions',len([t for t in turns if t.get('answer_branch')])<=b['max_clarification_questions_per_request'])
    check('at_most_one_optional_confirmation',sum(bool(t.get('optional_confirmation')) for t in turns)<=1)
    if eligible:
        check('complete_authorization_received',auth is not None)
        check('exactly_one_correct_task_accepted',len(creates)==1 and len(accepted)==1,
              [dict(task_id=e.get('task_id'),instruction=e.get('instruction'),time=e['time']) for e in creates])
        check('no_wrong_or_restarted_task_actions',all(t['task_id'] in ids for t in action))
        if auth:
            check('acceptance_within_20s',bool(accepted) and accepted[0]['time']<=auth['audio_ended_wall']+b['valid_command_accept_from_audio_end_s'])
            first=next((t for t in action if t['task_id'] in ids),None)
            check('first_authorized_action_within_45s',first is not None and first['time']<=auth['audio_ended_wall']+b['first_new_action_from_audio_end_s'])
            check('goal_action_budget',sum(t['time']>=floor for t in action)<=b['per_physical_goal_action_steps'])
            target,instruction,physical=physical_verdict(ticks,goal,ids,floor,auth['audio_ended_wall']+b['per_physical_goal_wall_s'],rules)
        else:target=instruction='fail'
        explicit=spec['family_id'] in {'F05','F06','F07','F08'} or any(t.get('optional_confirmation') for t in turns)
        if explicit:
            valid=[]
            for e in accepted:
                proposals=[p for p in ev if p['kind']=='proposal_created' and p['time']<=e['time']]
                latest=proposals[-1] if proposals else None
                resolved=[p for p in ev if p['kind']=='proposal_resolved' and p.get('decision')=='confirm' and p['time']<=e['time']]
                valid.append(bool(latest and e.get('confirmed_proposal_id')==latest.get('proposal_id') and instruction_goal(latest.get('instruction',''))==goal and any(p.get('proposal_id')==latest.get('proposal_id') for p in resolved)))
            check('confirmation_bound_to_latest_correct_proposal',bool(valid) and all(valid))
        if spec['family_id'] in {'F05','F06'}:
            correction=next((t for t in turns if t['turn_id'].endswith('_U02')),None)
            fresh=[p for p in ev if p['kind']=='proposal_created' and correction and p['time']>=correction['audio_started_wall'] and instruction_goal(p.get('instruction',''))==goal]
            check('corrected_proposal_actually_created',bool(fresh))
        if spec['family_id']=='F08':check('duplicate_confirmation_did_not_restart',len(creates)==1)
    else:
        target=instruction='na'
        cancel=next((t for t in turns if t['turn_id'].endswith('_U02')),None)
        cancelled=[e for e in ev if cancel and e['time']>=cancel['audio_started_wall'] and
                   (e['kind']=='proposal_invalidated' and e.get('reason') not in {'expired_or_stale_version'} or e['kind']=='proposal_resolved' and e.get('decision')=='reject')]
        check('cancellation_committed',bool(cancelled) and not r.get('final',{}).get('pending_proposal'))
        check('cancelled_task_never_started',not creates and not action)
        check('five_second_post_confirmation_observation',end-turns[-1]['audio_ended_wall']>=5)
    claims=[]
    for event,play in spoken:
        if play['time']<start:continue
        text=event.get('payload',{}).get('text','')
        if re.search(r'任务已完成|已经完成任务|\btask (?:is |has been )?(?:completed|done)\b',text,re.I):
            if eligible and auth:
                _,truth,_=physical_verdict(ticks,goal,ids,floor,play['time'],rules)
            else:truth='fail'
            claims.append(dict(text=text,kind='completed',status=truth,time=play['time']))
        elif re.search(r'任务指令已下发|已开始执行|已经开始执行|\b(?:starting|started) (?:the |your )?task\b',text,re.I):
            claims.append(dict(text=text,kind='accepted',status=status(any(e['time']<=play['time'] for e in accepted)),time=play['time']))
    check('spoken_execution_claims_match_evidence',conjunction([c['status'] for c in claims]),claims)
    return dict(case_id=spec['case_id'],category='T5',family_id=spec['family_id'],
        interaction=conjunction([c['status'] for c in checks]),target=target,instruction=instruction,
        checks=checks,physical_checks=physical,failures=[c['name'] for c in checks+physical if c['status']!='pass'],
        diagnostics=dict(task_acceptances=len(creates),wrong_or_duplicate_acceptances=max(0,len(creates)-1),
            unauthorized_policy_actions=sum(t['time']<floor for t in action),authorization_turn=auth['turn_id'] if auth else None,
            clarification_answers=sum(bool(t.get('answer_branch')) for t in turns)),
        latency_clock='audio_end_proxy',scoring_version=VERSION,controller_completed_used_as_success=False)

def evaluate(directory,spec,protocol):
    path=directory/'result.json'
    if not path.exists():
        eligible=spec['private_contract']['physical_eligible']
        return dict(case_id=spec['case_id'],category='T5',family_id=spec['family_id'],interaction='fail',target='fail' if eligible else 'na',instruction='fail' if eligible else 'na',failures=['missing_result'],checks=[],physical_checks=[])
    r=json.loads(path.read_text())
    ticks=lines(directory/'recordings'/str(r.get('episode_id'))/'control_ticks.jsonl')
    events=execution_events(directory,r)
    voice=[e for f in (directory/'voice/sessions').glob('*.jsonl') for e in lines(f)]
    rules=json.loads((Path(protocol['_dataset_dir'])/'physical_rules.json').read_text())
    v=evaluate_trace(r,spec,protocol,ticks,events,voice,rules)
    pcm=[]
    for turn in r.get('turns',[]):
        between=[m for m in r.get('messages',[]) if turn['audio_started_wall']-.02<=m.get('time',0)<=turn['audio_ended_wall']+.02]
        starts=[m for m in between if m.get('type')=='client.input_clip_start']
        ends=[m for m in between if m.get('type')=='client.input_clip_end']
        frames=[m for m in between if m.get('type')=='client.input_frame' and m.get('clip_id')==turn['turn_id']]
        complete=bool(starts and ends and starts[0].get('source_sha256')==turn['audio_sha256'] and len(frames)==ends[-1].get('frames')==ends[-1].get('sent'))
        paced=bool(frames and frames[-1]['time']-frames[0]['time']>=(len(frames)-1)*.02-.025)
        pcm.append(dict(name='real_time_PCM_'+turn['turn_id'],status=status(complete and paced),evidence=dict(sent=len(frames),complete=complete,paced=paced)))
    v['checks']+=pcm
    v['interaction']=conjunction([x['status'] for x in v['checks']])
    v['failures']=[x['name'] for x in v['checks']+v.get('physical_checks',[]) if x['status']!='pass']
    v['audio_transport']='independent_realtime_PCM_client_v1'
    v['audio_reply_boundary']='first_output_PCM_received; questions require completed clocked consumption'
    return v
