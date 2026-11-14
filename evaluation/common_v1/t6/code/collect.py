"""Method-neutral evidence from actual frames, PCM, clock and control logs."""
import copy,hashlib,json,wave
from pathlib import Path

def read(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(x)for x in Path(p).read_text().splitlines()if x.strip()]if Path(p).exists()else[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')

def facts(t,when):
    if not t:return dict(time=when,offset_seconds=0,mode='unavailable')
    p=t['physical']
    return dict(time=t['time'],offset_seconds=t['time']-when,simulation_time=t['simulation_time'],
        mode=t['mode'],held=p.get('held_object'),objects=p.get('objects'),drawers=p.get('drawers'),
        relations=p.get('native_goal_relations'),articulation=t['measurements'].get('bowl',{}).get('articulation'),
        extra=t.get('evaluator_extra'))

def extract(case,registered,index):
    case=Path(case);trial=read(case/'client/TRIAL.json')if(case/'client/TRIAL.json').exists()else{}
    events=lines(case/'client/events.jsonl');ticks=lines(case/'physical.jsonl')
    start=trial.get('audio_started');end=trial.get('audio_ended')
    task_events=lines(case/'task_events.jsonl');gateway=lines(case/'gateway.jsonl')
    status=[x for x in lines(case/'client/system_events.jsonl')if x.get('type')=='system.status']
    gate=trial.get('gate')or{};identity=gate.get('identity',{})
    def nearest(when):return min(ticks,key=lambda t:abs(t['time']-when))if ticks else None
    outputs=[];speech_frames=[]
    for event in events:
        if event['type']!='host.output_audio_receipt':continue
        if not start or event['time']>end+45:continue
        epoch=event['epoch'];sid=event['outputId'];key=lambda x:x.get('epoch')==epoch and x.get('outputId')==sid
        matching=[x for x in events if key(x)]
        first=next((x for x in matching if x['type']=='client.output_clocked_start'),None)
        last=next((x for x in matching if x['type']=='client.output_clocked_complete'),None)
        # A receipt can precede actual playback; pre-question speech is not a QA reply.
        if first and first['time']<start:continue
        if not first and event['time']<start:continue
        recv=next((x for x in matching if x['type']=='client.output_pcm_received'),None)
        wav=case/'client'/('output_%s_%s.wav'%(epoch,sid));generated=case/'speech'/('%03d.wav'%sid)
        samples=None;raw=None;genraw=None
        if wav.exists():
            with wave.open(str(wav))as f:samples=f.getnframes();raw=f.readframes(samples)
        if generated.exists():
            with wave.open(str(generated))as f:genraw=f.readframes(f.getnframes())
        same=raw is not None and genraw==raw and recv and recv.get('pcm_sha256')==hashlib.sha256(raw).hexdigest()
        complete=bool(last and first and same and samples==event.get('expectedSamples') and last.get('samples')==samples)
        outputs.append(dict(output_id=sid,epoch=epoch,text=event['text'],audio_file=str(wav),
            wav_samples=samples,first_pcm_latency_s=first['time']-end if first else None,
            completion_latency_s=last['time']-end if last else None,valid_clocked_complete=complete,
            audibility_evidence=dict(kind='generated_and_received_and_receipt_PCM_sha256',
                receipt_key=json.dumps(['actual_TTS',epoch,sid,event.get('replyKind','unknown')]),
                sha256=hashlib.sha256(raw).hexdigest()if raw else None,all_three_match=bool(same))))
        spoken_time=first['time']if first else event['time']
        speech_frames.append(dict(epoch=epoch,output_id=sid,facts=facts(nearest(spoken_time),spoken_time)))
    inputs=lines(case/'QA_INPUTS.private.jsonl')
    frames=[]
    for x in inputs:
        if start and start<=x['request_time']<=end+45:
            frames.append(dict(image=x['image'],sha256=x['sha256'],first_request_time=x['image_time'],provider_dispatch_time=x['request_time'],
                facts=x['facts'],stage='single_Agent',model='Qwen3.8-27B'))
    coverage=[x for x in status if start and start<=x['time']<=end+45]
    changes=[x for x in task_events if start and start<=x['time']<=end+45 and x['kind']in
        ['task_instruction','task_updated','task_paused','task_resumed','task_cancelled',
         'deferred_scheduled','deferred_invalidated','deferred_consumed']]
    bad_status=[x for x in coverage if any(x['status'].get(k)!=identity.get(k)for k in
        ['episode_id','task_id','task_intent_revision'])or x['status'].get('mode')=='paused']
    times=[x['time']for x in coverage]
    covered=bool(times and times[0]-start<.5 and end+45-times[-1]<.5 and
                 max([b-a for a,b in zip(times,times[1:])]+[0])<=1)
    no_error=bool(start and end and covered and not bad_status and not changes)
    control=dict(case_id=registered['case_id'],no_qa_control_error=no_error,
        sample_count=len(coverage),coverage_passed=covered,identity=identity,
        unexpected_tools=changes,identity_or_pause_violations=len(bad_status),
        first_sample=times[0]if times else None,last_sample=times[-1]if times else None,
        interval=dict(start=start,end=end+45 if end else None),
        source='independent_received_status_samples_and_actual_task_event_log; no_Agent_self_claim')
    actual_asr=[dict(text=x['text'],time=x['time'])for x in events if x['type']=='asr.transcript'and start and start<=x['time']<=end+45]
    evidence=dict(case_id=registered['case_id'],index=index,question=registered['question_text'],
        outputs=outputs,actual_user_transcripts=actual_asr,frames=frames,speech_frames=speech_frames,
        facts_at_audio_end=facts(nearest(end),end)if end else{},
        gate_instruction=gate.get('evidence',{}).get('instruction',''),gate_state=gate.get('evidence',{}).get('state','unavailable'),
        audio_start=start,audio_end=end,window_end=end+45 if end else None)
    sent=[x for x in events if x['type']=='client.input_frame']
    input_audio=bool(start and end and sent)
    if input_audio:
        duration=end-start;wanted=len(sent)*.02
        gaps=[b['time']-a['time']for a,b in zip(sent,sent[1:])]
        input_audio=.95<=duration/wanted<=1.05 and max(gaps+[0])<=.1
    audit=dict(audio_admitted=bool(input_audio),output_count=len(outputs),
        output_PCM_integrity_passed=all(x['audibility_evidence']['all_three_match']for x in outputs),
        no_qa_control_error=no_error,frames=len(frames),
        frame_offsets_passed=all(abs(f['facts']['offset_seconds'])<=.1 for f in frames),
        trial_status=trial.get('status'),asked=start is not None,reference_answers_given_to_actor=False)
    save(case/'EVIDENCE.json',evidence);save(case/'CONTROL_AUDIT.json',control);save(case/'DELIVERY_AUDIT.json',audit)
    return evidence,control,audit
