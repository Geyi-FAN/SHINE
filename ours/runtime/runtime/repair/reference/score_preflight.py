"""Independent probe judging: original contract + physical ticks + real receipts.

Controller 'completed' and Agent subgoal strings never establish physical success.
Unknown semantic QA remains unknown and is not counted as a pass.
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
DOC=ROOT/'docs/evaluation/audio_switch_benchmark_v1'
sys.path.insert(0,str(Path(__file__).resolve().parent))
from benchmark_metrics.events import restore_window, high_releases, preservation_states
from aggregate import summarize


def lines(path):
    result=[]
    if path.exists():
        for line in path.read_text().splitlines():
            try:result.append(json.loads(line))
            except ValueError:pass
    return result


def conjunction(values):
    return 'fail' if 'fail' in values else 'unknown' if 'unknown' in values else 'pass'


def status(value):return 'pass' if value else 'fail'


def distance(a,b):return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))


def audible_visual_answers(voice, messages, turn, turns, finished):
    """Bind QA to actual output; turn.finished is an intermediate UI snapshot."""
    began=turn['audio_ended_wall']
    end=min([t['audio_started_wall'] for t in turns if t['audio_started_wall']>turn['audio_started_wall']]+[finished['time']])
    played=[m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and began<=m['time']<=end]
    answers=[]
    for event in voice:
        payload=event.get('payload',{})
        when=event.get('ts',0)/1000
        if event.get('type')!='transcript.assistant' or payload.get('audioSuppressed') or payload.get('purpose')!='visual_result' or not began<=when<=end:continue
        candidates=[m for m in played if abs(m['time']-when)<=2]
        if not candidates:continue
        start=min(candidates,key=lambda m:abs(m['time']-when))
        complete=next((m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_completed' and m.get('epoch')==start.get('epoch') and m.get('outputId')==start.get('outputId') and start['time']<=m['time']<=end),None)
        answers.append(dict(event=event,playback_start=start,playback_completed=complete))
    return answers


def held_during_requested_pause(ticks, pause_turn, resume_turn):
    if pause_turn is None or resume_turn is None:return False
    window=[t for t in ticks if pause_turn['audio_ended_monotonic']<=t['monotonic']<resume_turn['audio_started_monotonic']]
    return len(window)>=20 and all(t['physical'].get('held_object')=='bowl' for t in window)


def find_pause(ticks, began, deadline, require_held=True):
    # Earliest qualifying one-second physical hold, confirmed after its onset.
    for i,first in enumerate(ticks):
        if first['monotonic']<began or first['monotonic']>deadline:continue
        w=ticks[i:i+20]
        if len(w)<20:continue
        if any(t['policy_action'] or t['mode']!='paused' for t in w):continue
        p=first['proprioception']; width=sum(abs(x) for x in p['robot0_gripper_qpos'])
        good=True
        for t in w:
            q=t['proprioception']; qa=p['robot0_eef_quat'];qb=q['robot0_eef_quat']
            angle=2*math.acos(min(1,abs(sum(a*b for a,b in zip(qa,qb)))))
            if distance(p['robot0_eef_pos'],q['robot0_eef_pos'])>.005 or angle>.05 or abs(sum(abs(x) for x in q['robot0_gripper_qpos'])-width)>.003:good=False
            if require_held and t['physical']['held_object']!='bowl':good=False
        if good:return first
    return None


def evaluate(directory, spec, protocol=None):
    protocol=protocol or json.loads((DOC/'PROTOCOL.json').read_text())
    budgets=protocol['budgets']
    path=directory/'result.json'
    if not path.exists():return dict(case_id=spec['case_id'],interaction='unknown',target='unknown' if spec['private_contract']['physical_eligible'] else 'na',instruction='unknown' if spec['private_contract']['physical_eligible'] else 'na',failures=['missing_result'])
    r=json.loads(path.read_text());ticks=lines(directory/'recordings'/str(r.get('episode_id'))/'control_ticks.jsonl')
    turns=[t for t in r.get('turns',[]) if not t.get('prelude')]
    events=(r.get('timeline') or {}).get('events',[])
    msgs=r.get('messages',[])
    voice=[e for f in (directory/'voice/sessions').glob('*.jsonl') for e in lines(f)]
    checks=[]
    def check(name, value, evidence=None):checks.append(dict(name=name,status=value,evidence=evidence))
    check('precondition',status(r.get('precondition_validated',False)))
    if not ticks or not turns:
        check('required_observation','unknown')
        physical_status='fail' if ticks and not r.get('precondition_validated') else 'unknown'
        return dict(case_id=spec['case_id'],interaction=conjunction([c['status'] for c in checks]),target=physical_status if spec['private_contract']['physical_eligible'] else 'na',instruction=physical_status if spec['private_contract']['physical_eligible'] else 'na',checks=checks,failures=r.get('errors',[]),runner_errors=r.get('errors',[]),result_path=str(path),video=str(directory/'browser.webm'),environment_video=str(directory/'recordings'/str(r.get('episode_id'))/'environment.mp4'))
    main=turns[0];start=main['audio_started_monotonic']; wall_start=main['audio_started_wall']
    active=[t for t in ticks if t['monotonic']>=start]
    rules=json.loads((DOC/'physical_v2.5.0-candidate.frozen.json').read_text())
    relevant=[e for e in events if e['time']>=wall_start]
    creates=[e for e in relevant if e['kind']=='task_instruction']
    pauses=[e for e in relevant if e['kind']=='task_paused']
    def played_after(turn):return [m for m in msgs if m.get('direction')=='sent' and m['type']=='host.playback_started' and m['monotonic']>=turn['audio_ended_monotonic']]
    for t in turns:
        outputs=played_after(t)
        # Not every ASR transcript is a required spoken reply (backchannels differ).
        question_reply=(spec['category']=='T6' or (spec['script_id']=='T5_01' and t.get('after',{}).get('pending_clarification'))
                        or (spec['script_id']=='T8_03' and t['turn_id'].endswith('U01')))
        reply_budget=(budgets['clarification_question_from_audio_end_s'] if spec['script_id']=='T5_01' and question_reply else budgets['qa_first_informative_audio_from_audio_end_s']) if question_reply else budgets['ack_from_audio_end_s']
        first=next((m for m in outputs if m['monotonic']<=t['audio_ended_monotonic']+reply_budget),None)
        check('audible_reply_'+t['turn_id'],status(first is not None),dict(first_audio_monotonic=first['monotonic'] if first else None,clock='audio_end_proxy',deadline_seconds=reply_budget))
    sid=spec['script_id'];pause_evidence=None
    if sid in ['T2_01','T8_03']:
        t=turns[0] if sid=='T2_01' else next((t for t in turns if t['turn_id'].endswith('U02')),None)
        if t:
            pause_limit=budgets['pause_fallback_from_audio_end_s']
            pause_evidence=find_pause(active,t['audio_ended_monotonic'],t['audio_ended_monotonic']+pause_limit)
            check('physical_pause_within_deadline',status(pause_evidence is not None),dict(deadline_seconds=pause_limit,first_step=pause_evidence['step'] if pause_evidence else None,latency_seconds=pause_evidence['monotonic']-t['audio_ended_monotonic'] if pause_evidence else None))
        else:check('pause_turn_reached','fail')
        if sid=='T2_01':
            resume=next((t for t in turns if t['turn_id'].endswith('U02')),None)
            resumed=[e for e in relevant if e['kind']=='task_resumed']
            check('resume_original_once',status(resume is not None and len(resumed)==1 and len(creates)==0))
            if resume:
                p=next((t for t in active if t['policy_action'] and t['monotonic']>=resume['audio_ended_monotonic']),None)
                check('resume_actual_action_within_deadline',status(p is not None and p['monotonic']<=resume['audio_ended_monotonic']+budgets['first_new_action_from_audio_end_s']))
        else:
            check('actual_speech_overlap',status(bool(r.get('overlap_evidence'))))
            if pause_evidence:
                after=[t for t in active if t['monotonic']>=pause_evidence['monotonic']]
                check('remain_paused_5s',status(bool(after) and after[-1]['monotonic']-after[0]['monotonic']>=5 and not any(t['policy_action'] for t in after)))
    if sid in ['T1_01','T3_01','T4_01','T5_01']:
        if sid=='T5_01':
            branches=r.get('clarification_branches',[])
            check('clarification_requested_and_bound',status(bool(branches) and 1<=len(branches)<=3))
            last=turns[-1]
            check('no_action_before_resolution',status(not any(t['policy_action'] and start<=t['monotonic']<last['audio_started_monotonic'] for t in ticks)))
            check('complete_resolved_instruction',status(any('cheese' in e.get('instruction','').lower() and 'bowl' in e.get('instruction','').lower() for e in creates)))
        else:
            expected=('bowl','stove') if sid=='T1_01' else ('bowl','plate') if sid=='T3_01' else ('bowl','return')
            instruction=' '.join(e.get('instruction','').lower() for e in creates)
            accepted=all(x in instruction for x in expected)
            if sid=='T4_01':accepted=('bowl' in instruction and any(x in instruction for x in ['return','original','initial','episode-start','back']))
            check('correct_full_task_dispatched',status(accepted))
        check('no_duplicate_task',status(len(creates)<=1),dict(created=len(creates)))
        anchor=turns[-1] if sid=='T5_01' else main
        matching=[e for e in creates if e['time']>=anchor['audio_started_wall']]
        check('command_accepted_within_deadline',status(bool(matching) and matching[0]['time']<=anchor['audio_ended_wall']+budgets['valid_command_accept_from_audio_end_s']))
        taskids={e.get('task_id') for e in matching}
        p=next((t for t in active if t['policy_action'] and t['task_id'] in taskids),None)
        check('new_task_actual_action_within_deadline',status(p is not None and p['monotonic']<=anchor['audio_ended_monotonic']+budgets['first_new_action_from_audio_end_s']))
        if sid=='T3_01':
            newids={e.get('task_id') for e in creates}
            cutoff=main['audio_ended_monotonic']+budgets['first_new_action_from_audio_end_s']
            check('old_plan_invalidated',status(not any(t['policy_action'] and t['task_id'] not in newids and t['monotonic']>=cutoff for t in active)))
    if sid=='T6_01':
        check('qa_did_not_modify_task',status(not creates and not pauses))
        output=played_after(main)
        answers=audible_visual_answers(voice,msgs,main,turns,r['finished'])
        text=' '.join(a['event']['payload'].get('text','') for a in answers).lower()
        check('qa_informative_audio_within_deadline',status(bool(answers) and answers[0]['playback_start']['time']<=main['audio_ended_wall']+budgets['qa_first_informative_audio_from_audio_end_s']))
        check('qa_complete_audio_within_deadline',status(bool(answers) and answers[-1]['playback_completed'] is not None and answers[-1]['playback_completed']['time']<=main['audio_ended_wall']+budgets['qa_complete_answer_from_audio_end_s']))
        before=main.get('before_tick',{}).get('physical',{})
        if not output:check('qa_answer_grounded','fail',dict(reason='no_actual_audio'))
        elif before.get('held_object')=='bowl' and any(w in text for w in ['holding','gripper','held','拿着','夹着','抓着','手中']):check('qa_answer_grounded','pass',dict(text=text))
        elif any(w in text for w in ['看不清','cannot tell','uncertain']):check('qa_answer_grounded','unknown',dict(text=text,reason='requires_human_review'))
        else:check('qa_answer_grounded','unknown',dict(text=text,reason='paraphrase_or_time_alignment_requires_human_review'))
    if sid=='T7_01':
        scheduled=[e for e in relevant if e['kind']=='deferred_scheduled'];started=[e for e in relevant if e['kind']=='deferred_started']
        check('waiting_scheduled',status(len(scheduled)==1))
        check('waiting_started_once',status(len(started)==1))
        # Find actual predecessor success independently, never task_completed.
        first=None
        for i,t in enumerate(active):
            w=active[max(0,i-4):i+1]
            if len(w)==5 and all(x['physical']['native_goal_relations']['bowl_stove'] for x in w):
                if restore_window([x['measurements']['bowl'] for x in w],dict(reference_position=t['measurements']['bowl']['object_position'],stable_required=True,withdraw_required=False),1e6,rules)['complete']:
                    first=t;break
        if len(started)==1 and first:
            ev=started[0];new_id=ev.get('new_task_id');action=next((t for t in active if t['task_id']==new_id and t['policy_action']),None)
            check('waiting_physical_order_and_handoff_deadline',status(ev['time']>=first['time']-.1 and action is not None and first['monotonic']-.1<=action['monotonic']<=first['monotonic']+budgets['waiting_handoff_from_independent_predecessor_success_s']),dict(predecessor_step=first['step'],handoff_event=ev))
        else:check('waiting_physical_order_and_handoff_deadline','fail')
    # Per-case budgets from actual ticks, unaffected by controller resume resets.
    check('case_action_budget',status(sum(t['policy_action'] for t in ticks)<=budgets['case_action_steps']))
    check('case_wall_budget',status(r['finished']['monotonic']-r['started']['monotonic']<=budgets['case_wall_s']))
    eligibility=spec['private_contract']['physical_eligible'];physical_checks=[]
    target='na';instruction='na'
    if eligibility:
        goal=spec['private_contract']['target'];obj='cheese' if goal=='cheese_in_bowl' else 'bowl'
        key={'bowl_on_stove':'bowl_stove','bowl_on_plate':'bowl_plate','cheese_in_bowl':'cheese_bowl'}.get(goal)
        reference=ticks[0]['episode_initial_positions']['akita_black_bowl_1']
        def released_at(i):
            w=active[max(0,i-7):i+1]
            return restore_window([x['measurements'][obj] for x in w],dict(reference_position=reference if goal=='bowl_at_episode_start_released' else active[i]['measurements'][obj]['object_position'],stable_required=True,withdraw_required=False),rules['restore']['radius_m'] if goal=='bowl_at_episode_start_released' else 1e6,rules)['complete']
        # Target is arrival, consistent with native placement targets. Release
        # and stability belong to Instruction; hold-only confirmation must not
        # hide an arrival that happened during an actual policy action.
        flags=[(t['physical']['native_goal_relations'].get(key,False) if key else
                distance(t['measurements']['bowl']['object_position'],reference)<=rules['restore']['radius_m']) for i,t in enumerate(active)]
        # A target after actual authorized policy motion, not a passive initial snapshot.
        if sid in ['T2_01','T6_01']:
            authorized_ids={main['before'].get('task_id')}
        else:
            def matches(e):
                text=e.get('instruction','').lower()
                if goal=='bowl_at_episode_start_released':return 'bowl' in text and any(w in text for w in ['return','original','initial','episode-start','back'])
                words={'bowl_on_stove':['bowl','stove'],'bowl_on_plate':['bowl','plate'],'cheese_in_bowl':['cheese','bowl']}[goal]
                return all(w in text for w in words)
            authorized_ids={e['task_id'] for e in creates if matches(e)}
        authorized_ids.discard(None)
        policy_seen=False;hit=None
        for i,t in enumerate(active):
            policy_seen=policy_seen or (t['policy_action'] and t['task_id'] in authorized_ids)
            if policy_seen and t['policy_action'] and t['task_id'] in authorized_ids and flags[i]:hit=i;break
        target=status(hit is not None)
        physical_checks.append(dict(name='target_ever_in_policy_steps',status=target,first_step=active[hit]['step'] if hit is not None else None))
        terminal=len(active)>=40 and all(flags[-40:]) and all(released_at(i) for i in range(max(0,len(active)-40),len(active)))
        physical_checks.append(dict(name='target_release_support_and_terminal_40_steps',status=status(terminal)))
        if goal=='bowl_at_episode_start_released':
            drops=high_releases([t['measurements']['bowl'] for t in active],reference,rules)
            physical_checks.append(dict(name='no_high_unsupported_release',status=status(not drops),events=drops))
        if sid=='T2_01':
            pause_turn=next((t for t in turns if t['turn_id'].endswith('U01')),None)
            resume_turn=next((t for t in turns if t['turn_id'].endswith('U02')),None)
            # Reaction time belongs to Interaction. Physical holding must not
            # fail solely because the eventual genuine pause arrived >2s late.
            physical_checks.append(dict(name='keep_holding_during_requested_pause',status=status(held_during_requested_pause(active,pause_turn,resume_turn))))
        if sid=='T7_01':
            prior=next((t for t in active if t['physical']['native_goal_relations']['bowl_stove'] and not t['measurements']['bowl']['target_contact'] and t['measurements']['bowl']['support_contact']),None)
            cheese=next((t for t in active if t['physical']['native_goal_relations']['cheese_bowl']),None)
            ordered=prior is not None and cheese is not None and prior['step']<cheese['step']
            physical_checks.append(dict(name='bowl_stove_before_cheese',status=status(ordered)))
            ps=rules['preserve_position']
            preservation=[] if prior is None else preservation_states([distance(t['measurements']['bowl']['object_position'],prior['measurements']['bowl']['object_position']) for t in active if t['step']>=prior['step']],ps['tolerance_m'],ps['severe_m'],ps['confirmation_steps'])[0]
            preserve=bool(preservation) and preservation[-1] is True
            physical_checks.append(dict(name='keep_bowl_at_stove',status=status(preserve)))
        instruction=conjunction([c['status'] for c in physical_checks])
    return dict(case_id=spec['case_id'],category=spec['category'],interaction=conjunction([c['status'] for c in checks]),target=target,instruction=instruction,
        checks=checks,physical_checks=physical_checks,failures=[c['name'] for c in checks+physical_checks if c['status']!='pass'],
        runner_errors=r.get('errors',[]),result_path=str(path),video=str(directory/'browser.webm'),environment_video=str(directory/'recordings'/str(r.get('episode_id'))/'environment.mp4'),
        latency_clock='audio_end_proxy',independent_physical_scoring=True,controller_completion_used_as_success=False)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    specs=json.loads((a.run.parent/'dataset/selected.private.json').read_text())
    metadata=json.loads((a.run/'metadata.json').read_text());ids=set(metadata['case_ids']);specs=[s for s in specs if s['case_id'] in ids]
    verdicts=[evaluate(a.run/'cases'/s['case_id'],s) for s in specs]
    cases=[dict(case_id=s['case_id'],category=s['category'],physical_eligible=s['private_contract']['physical_eligible']) for s in specs]
    (a.run/'verdicts.json').write_text(json.dumps(verdicts,ensure_ascii=False,indent=2)+'\n')
    summary=summarize(cases,verdicts);(a.run/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary['micro'],ensure_ascii=False))


if __name__=='__main__':main()
