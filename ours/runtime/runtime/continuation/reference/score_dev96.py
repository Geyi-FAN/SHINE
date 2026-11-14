"""Independent full development judge: original contracts, not Harness plans."""
import json,re,sqlite3
from pathlib import Path
from score_preflight import lines,distance,conjunction,status,find_pause,held_during_requested_pause,DOC
from benchmark_metrics.events import restore_window,high_releases,preservation_states

SCORING_EVIDENCE_VERSION="audio-switch-evidence-v1.4-receipt-phase"

def execution_events(directory,result):
    """Recover the same durable event stream if its HTTP export was missing."""
    timeline=result.get('timeline')
    if isinstance(timeline,dict) and 'events' in timeline and not timeline.get('has_more'):
        return timeline['events']
    path=directory/'gateway/episodes.sqlite'
    if not path.exists() or not result.get('episode_id'):return []
    try:
        with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True) as db:
            rows=db.execute('SELECT rowid,id,time,kind,version,payload FROM events WHERE episode=? AND time<=? ORDER BY rowid',
                (result['episode_id'],result.get('finished',{}).get('time',float('inf')))).fetchall()
        return [{**json.loads(r[5]),'sequence':r[0],'event_id':r[1],'time':r[2],'kind':r[3],'version':r[4]} for r in rows]
    except (sqlite3.Error,ValueError):return []

def audible_records(voice,messages):
    outputs=[m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and m.get('outputId') is not None and not m.get('bindingUpdate')]
    transcripts=[e for e in voice if e.get('type')=='transcript.assistant']
    proposed=[]
    for event in transcripts:
        p=event.get('payload',{});ts=event.get('ts',0)/1000;release=None
        if not p.get('audioSuppressed'):
            near=[m for m in outputs if abs(m['time']-ts)<=2]
            if not near:continue
            chosen=min(near,key=lambda m:abs(m['time']-ts));kind='direct_transcript_with_host_playback'
        else:
            rid=p.get('responseId')
            if not rid:continue
            done=[e for e in voice if e.get('type')=='response.done' and e.get('payload',{}).get('responseId')==rid and e.get('ts',0)/1000>=ts-.01]
            if len(done)!=1:continue
            ended=done[0]['ts']/1000
            boundary=min([e['ts']/1000 for e in voice if e.get('ts',0)/1000>ended and e.get('type') in {'response.created','transcript.assistant'} and e.get('payload',{}).get('responseId')!=rid]+[float('inf')])
            verified=[e for e in voice if e.get('type')=='realtime.protocol' and e.get('payload',{}).get('type')=='robot.reply_verified' and e.get('payload',{}).get('decision') in {'original','matched_receipt_audio'} and ended<=e.get('ts',0)/1000<boundary]
            if len(verified)!=1:continue
            release=verified[0]
            near=[m for m in outputs if -.1<=m['time']-release['ts']/1000<=2 and m['time']<boundary+.1]
            if len(near)!=1:continue
            chosen=near[0];kind='buffered_transcript_verified_release_and_host_playback'
        complete=next((m for m in messages if m.get('direction')=='sent'and m.get('type')=='host.playback_completed'and m.get('epoch')==chosen.get('epoch')and m.get('outputId')==chosen.get('outputId')and m.get('time',0)>=chosen['time']and isinstance(m.get('samples'),int)and m['samples']>0 and m['samples']==m.get('expectedSamples')),None)
        if complete is None:continue
        chosen=dict(chosen,completed_time=complete['time'])
        augmented=dict(event,audibility_evidence=dict(kind=kind,output_id=chosen['outputId'],release_timestamp_ms=None if release is None else release['ts']))
        proposed.append((augmented,chosen))
    # One physical output cannot prove two different transcripts. Fail closed.
    grouped={}
    for event,play in proposed:grouped.setdefault((play.get('epoch'),play['outputId']),[]).append((event,play))
    result=[]
    for matches in grouped.values():
        texts={e['payload'].get('text','').strip() for e,_ in matches}
        if len(texts)==1:result.append(matches[0])
    return sorted(result,key=lambda pair:pair[1]['time'])


GOALS={'bowl_on_stove':('bowl_stove','bowl'),'bowl_on_plate':('bowl_plate','bowl'),
       'cheese_in_bowl':('cheese_bowl','cheese'),'wine_on_cabinet':('bottle_cabinet','wine_bottle'),
       'cheese_on_stove':('cheese_stove','cheese'),'bowl_at_episode_start_released':('return','bowl')}
READONLY={'T1_04','T4_03','T6_01','T6_02','T6_03','T6_04','T8_01','T8_02','T8_04'}
NO_NEW=READONLY|{'T2_01','T2_02','T2_03','T2_04','T7_02','T8_03'}
NEGATIVE_IDLE={'T1_04','T4_03','T5_04'}
NEW_TARGETS={'T1_01':('bowl','stove'),'T1_02':('cheese','bowl'),'T1_03':('bottle','cabinet'),
             'T3_01':('bowl','plate'),'T3_02':('cheese','bowl','return'),'T3_03':('bowl','plate'),
             'T3_04':('cheese','bowl'),'T4_01':('bowl','return'),'T4_02':('cheese','bowl'),
             'T4_04':('cheese','stove'),'T5_01':('cheese','bowl'),'T5_02':('bowl','stove'),'T5_03':('cheese','bowl')}

def evaluate(directory,spec,protocol):
    path=directory/'result.json';sid=spec['script_id'];eligible=spec['private_contract']['physical_eligible'];budgets=protocol['budgets']
    if not path.exists():return dict(case_id=spec['case_id'],interaction='fail',target='fail' if eligible else 'na',instruction='fail' if eligible else 'na',failures=['runner_result_missing'],checks=[],physical_checks=[])
    r=json.loads(path.read_text());ticks=[t for t in lines(directory/'recordings'/str(r.get('episode_id'))/'control_ticks.jsonl') if t['time']<=r.get('finished',{}).get('time',float('inf'))]
    turns=[t for t in r.get('turns',[]) if not t.get('prelude')];messages=r.get('messages',[])
    voice=[e for f in (directory/'voice/sessions').glob('*.jsonl') for e in lines(f)]
    checks=[];physical=[]
    def check(name,ok,evidence=None):checks.append(dict(name=name,status=ok if isinstance(ok,str) else status(ok),evidence=evidence))
    def phys(name,ok,evidence=None):physical.append(dict(name=name,status=ok if isinstance(ok,str) else status(ok),evidence=evidence))
    check('precondition_actually_reached',r.get('precondition_validated',False))
    if not turns or not ticks:
        check('scored_audio_and_physical_trace_present',False)
        return dict(case_id=spec['case_id'],interaction='fail',target='fail' if eligible else 'na',instruction='fail' if eligible else 'na',checks=checks,physical_checks=[],failures=['precondition_or_trace_unavailable'],runner_errors=r.get('errors',[]))
    start=turns[0]['audio_started_wall'];main=turns[0];active=[t for t in ticks if t['time']>=start]
    events=[e for e in execution_events(directory,r) if e['time']>=start]
    creates=[e for e in events if e['kind']=='task_instruction'];pauses=[e for e in events if e['kind']=='task_paused'];resumes=[e for e in events if e['kind']=='task_resumed']
    rules=json.loads((DOC/'physical_v2.5.0-candidate.frozen.json').read_text())
    def find_turn(suffix):return next((t for t in turns if t['turn_id'].endswith(suffix)),None)
    def after(t):return [x for x in active if x['time']>=t['audio_ended_wall']]
    def playback(t):
        next_wall=min([x['audio_started_wall'] for x in turns if x['audio_started_wall']>t['audio_started_wall']]+[r['finished']['time']])
        return [m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and t['audio_ended_wall']<=m['time']<=next_wall]
    def spoken(t,visual_only=False):
        outputs={(m.get('epoch'),m.get('outputId')) for m in playback(t)}
        return [(v,m) for v,m in audible_records(voice,messages)
                if (m.get('epoch'),m.get('outputId')) in outputs
                and (not visual_only or v.get('payload',{}).get('purpose')=='visual_result')]
    # Every authored turn must really be played. Only clarification answers may
    # vary with the question actually heard.
    authored={t['turn_id'] for t in spec['turns']}
    check('all_authored_turns_played',authored<={t['turn_id'] for t in turns})
    optional_reply={'T8_01':{'U01','U02'},'T2_02':{'U02'}}
    for t in turns:
        suffix=t['turn_id'][-3:]
        if suffix in optional_reply.get(sid,set()) or (sid in {'T6_04','T8_03'} and suffix=='U01'):continue
        qa=spec['category']=='T6' or sid in {'T1_04','T4_03','T8_02','T8_04','T5_01'}
        budget=budgets['qa_first_informative_audio_from_audio_end_s'] if qa else budgets['ack_from_audio_end_s']
        plays=playback(t)
        check('audible_reply_'+t['turn_id'],bool(plays) and plays[0]['time']<=t['audio_ended_wall']+budget,
              dict(latency_s=plays[0]['time']-t['audio_ended_wall'] if plays else None,deadline_s=budget))
    check('case_wall_budget',r['finished']['monotonic']-r['started']['monotonic']<=budgets['case_wall_s'])
    check('case_action_budget',sum(bool(t['policy_action']) for t in active)<=budgets['case_action_steps'])
    if sid in NO_NEW:check('no_unrequested_new_task',not creates)
    if sid in READONLY:check('qa_or_backchannel_did_not_pause',not pauses)
    if sid in NEGATIVE_IDLE:check('no_unauthorized_policy_action',not any(t['policy_action'] for t in active))
    if sid not in {'T7_01','T7_02','T7_03','T7_04'}:check('no_unrequested_waiting',not any(e['kind']=='deferred_scheduled' for e in events))
    if sid in NEW_TARGETS:
        expected=NEW_TARGETS[sid];candidate=' '.join(e.get('instruction','').lower() for e in creates)
        check('complete_correct_goal_dispatched',len(creates)==1 and all((bool(re.search(r'return|back|episode[- ]start|original|initial (?:position|location)',candidate)) if w=='return' else w in candidate) for w in expected),dict(instructions=[e.get('instruction') for e in creates]))
        anchor=turns[-1] if sid in {'T5_01','T5_02','T5_03'} else main
        check('command_acceptance_deadline',bool(creates) and creates[0]['time']<=anchor['audio_ended_wall']+budgets['valid_command_accept_from_audio_end_s'])
        if creates:
            ids={e.get('task_id') for e in creates};first=next((t for t in active if t['policy_action'] and t['task_id'] in ids),None)
            check('first_new_action_deadline',first is not None and first['time']<=anchor['audio_ended_wall']+budgets['first_new_action_from_audio_end_s'])
    if sid in {'T3_01','T3_02','T3_03','T3_04'}:
        ids={e.get('task_id') for e in creates}
        check('obsolete_plan_no_late_actions',not any(t['policy_action'] and t['task_id'] not in ids and t['time']>=main['audio_ended_wall']+budgets['first_new_action_from_audio_end_s'] for t in active))
    if sid in {'T2_01','T2_02','T7_04','T8_03'}:
        pause=find_turn('U02') if sid in {'T7_04','T8_03'} else main
        found=None if pause is None else find_pause(active,pause['audio_ended_monotonic'],pause['audio_ended_monotonic']+budgets['pause_fallback_from_audio_end_s'])
        check('physical_pause_deadline',found is not None,dict(latency_s=None if found is None else found['monotonic']-pause['audio_ended_monotonic']))
        if sid in {'T2_02','T8_03'}:
            window=[] if found is None else [t for t in active if t['monotonic']>=found['monotonic']]
            check('remain_paused_and_hold_for_5s',bool(window) and window[-1]['monotonic']-window[0]['monotonic']>=5 and all(not t['policy_action'] and t['physical']['held_object']=='bowl' for t in window))
        if sid=='T2_01':
            resume=find_turn('U02');check('resume_original_exactly_once',len(resumes)==1)
            phys('hold_bowl_until_resume',held_during_requested_pause(active,pause,resume))
    if sid=='T2_03':check('duplicate_resume_does_not_restart',len(resumes)==1 and not creates)
    if sid=='T2_04':check('negated_stop_does_not_pause',not pauses and not creates)
    if sid=='T5_01':
        check('clarification_registered_and_answered',bool(r.get('clarification_branches')) and not r.get('final',{}).get('pending_clarification'))
        last=turns[-1];check('no_action_before_slots_resolved',not any(t['policy_action'] and t['time']<last['audio_started_wall'] for t in active))
    if sid in {'T5_02','T5_03'}:
        confirm=turns[1] if sid=='T5_02' and len(turns)>1 else find_turn('U03')
        check('no_action_before_correct_confirmation',confirm is not None and not any(t['policy_action'] and t['time']<confirm['audio_started_wall'] for t in active))
        check('confirmed_task_dispatched_once',len(creates)==1)
        if sid=='T5_03':check('superseded_bowl_proposal_never_executed',all('cheese' in e.get('instruction','').lower() for e in creates))
    if sid=='T5_04':
        check('cancelled_proposal_not_resurrected',not creates and not r.get('final',{}).get('pending_proposal'))
    if sid.startswith('T7'):
        schedules=[e for e in events if e['kind']=='deferred_scheduled'];starts=[e for e in events if e['kind']=='deferred_started']
        check('waiting_registered',bool(schedules))
        if sid=='T7_02':
            check('waiting_cancelled_only',any(e['kind'] in {'deferred_cleared','deferred_invalidated'} and e.get('reason')=='user_cancelled' for e in events) and not starts and not creates and not any(e['kind']=='task_cancelled' for e in events))
        else:
            check('waiting_handoff_exactly_once',len(starts)==1 and len(creates)==1)
            if sid=='T7_03':check('only_latest_waiting_goal_executed',bool(creates) and all('bottle' in e.get('instruction','').lower() for e in creates))
            predecessor=None
            physical_active=[t for t in active if t.get('physics_tick',True)]
            for i,t in enumerate(physical_active):
                w=physical_active[max(0,i-4):i+1]
                if len(w)==5 and all(x['physical']['native_goal_relations']['bowl_stove'] for x in w) and restore_window([x['measurements']['bowl'] for x in w],dict(reference_position=w[-1]['measurements']['bowl']['object_position'],stable_required=True,withdraw_required=False),1e6,rules)['complete']:
                    predecessor=t;break
            newids={e.get('new_task_id') for e in starts};first=next((t for t in active if t['policy_action'] and t['task_id'] in newids),None)
            check('handoff_after_independent_predecessor_success',predecessor is not None and first is not None and predecessor['time']-.1<=first['time']<=predecessor['time']+budgets['waiting_handoff_from_independent_predecessor_success_s'],dict(predecessor_time=None if predecessor is None else predecessor['time'],first_action_time=None if first is None else first['time']))
        if sid=='T7_04':
            resume=find_turn('U03');check('waiting_retained_while_paused',any(e['kind']=='deferred_retained_during_pause' for e in events) and resume is not None and all(e['time']>=resume['audio_started_wall'] for e in starts) and len(resumes)==1)
    if sid in {'T6_04','T8_03'}:check('actual_speech_overlap',bool(r.get('overlap_evidence')))
    # QA semantics: accept only bounded statements supported throughout the
    # answer's evidence window. Longer/ambiguous claims remain human-review.
    qa_turns=turns if sid in {'T1_04','T6_01','T6_02','T6_03','T8_02','T8_04'} else [turns[-1]] if sid=='T6_04' else []
    for turn in qa_turns:
        replies=spoken(turn);text=' '.join(v['payload'].get('text','') for v,_ in replies)
        answer=[(v,p) for v,p in replies if not re.match(r'^(?:正在(?:查看|确认)|我先|任务指令已下发)',v['payload'].get('text','')) and v.get('payload',{}).get('purpose')!='task_result']
        if not answer and replies:answer=[(v,p) for v,p in replies if any(w in v['payload'].get('text','') for w in ['炉灶','碗','stove','bowl']) and '已完成' not in v['payload'].get('text','')]
        check('qa_answer_audible_'+turn['turn_id'],bool(answer))
        check('qa_complete_audio_deadline_'+turn['turn_id'],bool(answer)and max(p['completed_time']for _,p in answer)<=turn['audio_ended_wall']+budgets['qa_complete_answer_from_audio_end_s'])
        verdict='unknown'
        if answer:
            text=' '.join(v['payload'].get('text','') for v,_ in answer)
            end=max(p['time'] for _,p in answer);window=[t for t in active if turn['audio_started_wall']<=t['time']<=end]
            if sid=='T6_02' and all(t['physical']['native_goal_relations']['cheese_bowl'] for t in window) and window:
                if re.search(r'奶酪|cheese',text,re.I) and not re.search(r'没有|空的|empty|no cheese|not cheese',text,re.I):verdict='pass'
                elif re.search(r'空的|empty|没有东西',text,re.I):verdict='fail'
            destination_only=('destination' in turn['text'].lower() or 'going' in turn['text'].lower())
            if sid in {'T6_03','T6_04','T8_04'} and (destination_only or re.search(r'碗|bowl',text,re.I)) and re.search(r'炉灶|炉子|stove',text,re.I) and not re.search(r'已经完成|已完成|盘子|plate',text,re.I):verdict='pass'
            if sid=='T6_01' and window and all(t['physical']['held_object']=='bowl' for t in window):
                simple=not re.search(r'炉灶|炉子|盘子|抽屉|stove|plate|drawer|不在|没有|not',text,re.I)
                if simple and re.search(r'夹爪中|夹爪里|手中|拿着|夹着|holding|held|gripper',text,re.I):verdict='pass'
            if sid=='T8_02':
                if re.search(r'stop|停止|停下',text,re.I) and re.search(r'暂停|pause',text,re.I) and not re.search(r'不是暂停|不表示暂停|does not mean.{0,15}pause|doesn.t.{0,15}pause',text,re.I):verdict='pass'
            if sid=='T1_04' and window:
                on=all(t['physical']['native_goal_relations']['turn_on_stove'] for t in window);off=all(not t['physical']['native_goal_relations']['turn_on_stove'] for t in window)
                says_off=bool(re.search(r'没(?:有)?(?:打)?开|未(?:打)?开|关着|关闭|是关|off|not on',text,re.I))
                positive_text=re.sub(r'(?:未|没有|没)\s*(?:打)?开(?:启|着)?|not\s+(?:turned\s+)?on','',text,flags=re.I)
                says_on=bool(re.search(r'开着|是开|开启|turned on|is on',positive_text,re.I))
                if says_off and not says_on:verdict='pass' if off else 'fail' if on else 'unknown'
                elif says_on and not says_off:verdict='pass' if on else 'fail' if off else 'unknown'
        check('qa_semantics_'+turn['turn_id'],verdict,dict(actual_spoken_text=text,method='bounded_physical_or_task_evidence; otherwise human review'))
    if sid=='T4_03':check('no_history_requests_task_clarification',any(re.search(r'哪个任务|什么任务|哪项任务|具体任务|which task|what task',v['payload'].get('text',''),re.I) for v,_ in spoken(main)))
    target='na';instruction='na'
    if eligible:
        # Passive wall samples establish pause only; temporal physics windows use actual env.step.
        active=[t for t in active if t.get('physics_tick',True)]
        goal,obj=GOALS[spec['private_contract']['target']];ref=ticks[0]['episode_initial_positions']['akita_black_bowl_1']
        def flag(t):
            if goal=='return':return distance(t['measurements']['bowl']['object_position'],ref)<=rules['restore']['radius_m']
            if goal=='cheese_stove':return t.get('evaluator_extra',{}).get(goal)
            return t['physical']['native_goal_relations'].get(goal)
        flags=[flag(t) for t in active];ids={e.get('task_id') for e in creates}
        if sid in NO_NEW:ids.add(main['before'].get('task_id'))
        from causal_target import first_authorized_hit
        legacy_hit=next((i for i,t in enumerate(active) if t['policy_action'] and t['task_id'] in ids and flags[i] is True),None)
        hit=first_authorized_hit(active,flags,ids)
        target='unknown' if flags and all(x is None for x in flags) else status(hit is not None)
        phys('target_after_authorized_motion_real_physics',target,dict(first_step=None if hit is None else active[hit]['step'],legacy_action_only_hit=None if legacy_hit is None else active[legacy_hit]['step'],evidence_version=SCORING_EVIDENCE_VERSION))
        def released(i):
            w=[x['measurements'][obj] for x in active[max(0,i-7):i+1]]
            return bool(w and restore_window(w,dict(reference_position=w[-1]['object_position'],stable_required=True,withdraw_required=False),1e6,rules)['complete'])
        phys('target_released_supported_and_held_40_ticks',len(active)>=40 and all(x is True for x in flags[-40:]) and all(released(i) for i in range(max(0,len(active)-40),len(active))))
        clauses=spec['private_contract']['instruction_clauses']
        if 'restore_bowl_episode_start' in clauses:
            returned=[]
            for i,t in enumerate(active):
                w=[x['measurements']['bowl'] for x in active[max(0,i-7):i+1]]
                if restore_window(w,dict(reference_position=ref,stable_required=True,withdraw_required=False),rules['restore']['radius_m'],rules)['complete']:returned.append(t)
            phys('bowl_returned_and_released',bool(returned))
            phys('no_high_unsupported_return_release',not high_releases([t['measurements']['bowl'] for t in active],ref,rules))
            if 'restore_before_cheese_placement' in clauses:phys('return_before_cheese_goal',bool(returned) and hit is not None and returned[0]['step']<active[hit]['step'])
        for clause in ['preserve_returned_bowl','preserve_bowl_takeover_position','preserve_bowl_on_stove']:
            if clause not in clauses:continue
            if clause=='preserve_returned_bowl':
                reference=ref;onset=returned[0]['step'] if returned else None
            elif clause=='preserve_bowl_takeover_position':reference=main['before_tick']['measurements']['bowl']['object_position'];onset=active[0]['step'] if active else None
            else:
                first=next((t for t in active if t['physical']['native_goal_relations']['bowl_stove'] and not t['measurements']['bowl']['target_contact'] and t['measurements']['bowl']['support_contact']),None)
                reference=None if first is None else first['measurements']['bowl']['object_position'];onset=None if first is None else first['step']
            p=rules['preserve_position'];values=[] if reference is None or onset is None else [distance(t['measurements']['bowl']['object_position'],reference) for t in active if t['step']>=onset]
            states=preservation_states(values,p['tolerance_m'],p['severe_m'],p['confirmation_steps'])[0]
            phys(clause,bool(states) and states[-1] is True)
        if any(c.startswith('bowl_stove_released_before_') for c in clauses):
            first=next((t for t in active if t['physical']['native_goal_relations']['bowl_stove'] and not t['measurements']['bowl']['target_contact'] and t['measurements']['bowl']['support_contact']),None)
            phys('predecessor_released_before_successor_goal',first is not None and hit is not None and first['step']<active[hit]['step'])
        if 'preserve_drawer_takeover_state' in clauses:
            q=main['before_tick']['measurements']['bowl']['articulation']['middle'];p=rules['preserve_joint'];states=preservation_states([abs(t['measurements']['bowl']['articulation']['middle']-q) for t in active],p['tolerance_m'],p['severe_m'],p['confirmation_steps'])[0]
            phys('drawer_takeover_state_preserved',bool(states) and states[-1] is True)
        instruction=conjunction([p['status'] for p in physical])
    # Actual played factual receipts are audited against current physical ticks.
    claims=[]
    for turn in turns:
        for event,play in spoken(turn):
            text=event['payload'].get('text','');current=next((t for t in reversed(ticks) if t['time']<=play['time']),None)
            kind=None;ok=None
            if re.search(r'任务已完成|当前任务已完成|已经完成任务',text):
                kind='completed'
                requested=next((e.get('instruction','').lower() for e in reversed(execution_events(directory,r)) if current and e['kind']=='task_instruction' and e.get('task_id')==current['task_id'] and e['time']<=play['time']),'')
                claim_goal=None;claim_obj=None
                if not re.search(r'\bthen\b|先|然后',requested):
                    if 'cheese' in requested and 'bowl' in requested:claim_goal,claim_obj='cheese_bowl','cheese'
                    elif 'bottle' in requested and 'cabinet' in requested:claim_goal,claim_obj='bottle_cabinet','wine_bottle'
                    elif 'bowl' in requested and 'stove' in requested:claim_goal,claim_obj='bowl_stove','bowl'
                    elif 'bowl' in requested and 'plate' in requested:claim_goal,claim_obj='bowl_plate','bowl'
                    elif requested.startswith('return the bowl'):claim_goal,claim_obj='return','bowl'
                if claim_goal and current:
                    w=[t for t in ticks if t['time']<=play['time']][-8:]
                    ref=(ticks[0]['episode_initial_positions']['akita_black_bowl_1'] if claim_goal=='return' else w[-1]['measurements'][claim_obj]['object_position'])
                    relation=(all(distance(t['measurements']['bowl']['object_position'],ref)<=rules['restore']['radius_m'] for t in w[-5:]) if claim_goal=='return' else all(t['physical']['native_goal_relations'][claim_goal] for t in w[-5:]))
                    ok=bool(len(w)>=5 and relation and restore_window([t['measurements'][claim_obj] for t in w],dict(reference_position=ref,stable_required=True,withdraw_required=False),rules['restore']['radius_m'] if claim_goal=='return' else 1e6,rules)['complete'])
            elif re.search(r'已暂停|已经暂停',text):kind='paused';ok=bool(current and current['mode']=='paused' and not current['policy_action'])
            elif re.search(r'已恢复|已经恢复',text):
                from receipt_phase import resume_receipt_consistent
                kind='resumed';gateway_events=lines(directory/'gateway.jsonl')
                ok=bool(current and resume_receipt_consistent(play['time'],current['task_id'],gateway_events,execution_events(directory,r),ticks))
            elif re.search(r'已记录等待|已安排后续',text):kind='queued';ok=any(e['kind']=='deferred_scheduled' and e['time']<=play['time'] for e in events)
            elif re.search(r'任务指令已下发|已开始执行|已经开始执行|任务已开始|任务已经在执行|当前任务.*仍在执行',text):
                kind='accepted';ok=bool(current and current['task_id'] and current['mode'] in {'running','verifying','completed'} and any(e['kind']=='task_instruction' and e.get('task_id')==current['task_id'] and e['time']<=play['time'] for e in execution_events(directory,r)))
                # A historical dispatch receipt is established by the durable
                # successful tool event, even if it precedes the next physics
                # sample. This exception never establishes physical completion.
                if '任务指令已下发' in text:
                    dispatched=[e for e in execution_events(directory,r) if e['kind']=='task_instruction' and e['time']<=play['time']]
                    ok=bool(dispatched and dispatched[-1].get('task_id'))
            if kind:claims.append(dict(kind=kind,text=text,time=play['time'],status='unknown' if ok is None else status(ok)))
    if claims:check('actually_spoken_receipts_match_evidence',conjunction([c['status'] for c in claims]),claims)
    wrong=len(creates) if sid in NO_NEW or sid in NEGATIVE_IDLE else max(0,len(creates)-1)
    return dict(case_id=spec['case_id'],category=spec['category'],interaction=conjunction([c['status'] for c in checks]),target=target,instruction=instruction,
        checks=checks,physical_checks=physical,spoken_claims=claims,failures=[c['name'] for c in checks+physical if c['status']!='pass'],
        runner_errors=r.get('errors',[]),auxiliary_counts=dict(unrequested_dispatch=wrong,duplicate_dispatch=max(0,len(creates)-1)),
        result_path=str(path),video=str(directory/'browser.webm'),environment_video=str(directory/'recordings'/str(r.get('episode_id'))/'environment.mp4'),
        latency_clock='audio_end_proxy',controller_completion_used_as_success=False,evidence_version=SCORING_EVIDENCE_VERSION,target_legacy_action_only=('pass'if legacy_hit is not None else'fail')if eligible else'na')
