"""Read-only re-score, with explicit old/new waiting deadlines.

Never overwrite a run's raw verdicts. The runtime R6 score accidentally required
an explicit pause in every T2 case, including 'do not stop'; applicability is
fixed independently here. No geometry or latency window is relaxed silently.
"""
import argparse, hashlib, json, os, sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
POSITIVE_PAUSE = {'T2_01', 'T2_02', 'T7_04', 'T8_03'}

def early_control_replies(result, voice, messages, turn, next_wall):
    """Allow a completed, receipt-bound pause reply during trailing input PCM.

    A preceding task's ordinary answer or a merely proposed pause cannot count.
    The exact output receipt key must bind to an accepted/executed pause and its
    independent final ASR received within this very input waveform.
    """
    allowed=[]
    for event in voice:
        e=event.get('payload',{});receipt=e.get('receipt',{});at=event.get('ts',0)/1000
        if event.get('type')!='realtime.protocol' or e.get('type')!='robot.fast_stop' or e.get('phase')!='receipt':continue
        if not(turn['audio_started_wall']<=at<turn['audio_ended_wall']):continue
        if receipt.get('status')!='accepted' or receipt.get('executed') is not True or receipt.get('state')!='paused':continue
        if receipt.get('episode_id')!=result.get('episode_id'):continue
        if not(turn['audio_started_wall']<=e.get('asr',{}).get('receivedAt',0)/1000<=at):continue
        for m in messages:
            if m.get('direction')!='sent' or m.get('type')!='host.playback_started' or m.get('bindingUpdate'):continue
            if not(at<=m.get('time',0)<min(turn['audio_ended_wall'],next_wall)):continue
            try:key=json.loads(m.get('receiptKey',''))
            except(ValueError,TypeError):continue
            if key==[e.get('inputId'),receipt.get('episode_id'),receipt.get('task_id'),receipt.get('task_version'),'robot_pause']:
                allowed.append(m)
    return allowed

def pause_evidence(result, ticks):
    explicit = result.get('true_pause')
    if explicit is not None:
        return dict(explicit, method='client_same_subject_2s_freeze')
    samples = [t for t in ticks if t.get('mode') == 'paused']
    # No physics, simulator clock, or full-state hash may change during pause.
    signatures = {(t.get('step'), t.get('simulation_time'), t.get('state_hash')) for t in samples}
    duration = max((t['time'] for t in samples), default=0)-min((t['time'] for t in samples), default=0)
    complete = bool(samples) and all(all(t.get(k) is not None for k in ('step','simulation_time','state_hash')) for t in samples)
    return dict(passed=complete and duration >= 1.5 and len(signatures) == 1,
                samples=len(samples), duration_s=duration, signatures=len(signatures),
                method='actual_private_samples_zero_env_step_clock_and_state_change')

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--label',required=True);p.add_argument('--waiting',type=int,choices=[10,45],required=True);p.add_argument('--final',action='store_true');a=p.parse_args()
    root=a.root; run=root/a.label
    os.environ['AUDIO_REPAIR_OUT']=str(root)
    source=(B/'repair6/score.py').read_text()
    assert source.count("if case['category']=='T2':")==1
    source=source.replace("if case['category']=='T2':", "if case['script_id'] in POSITIVE_PAUSE:")
    source=source.replace("passed=r.get('true_pause',{}).get('passed',False);", "pause=pause_evidence(r,ticks);passed=pause['passed'];")
    source=source.replace("evidence=r.get('true_pause')", "evidence=pause")
    source=source.replace("report=OUT/args.label/'reports';", "report=OUT/args.label/'reports_audited'/('v1.8_wait'+str(WAITING));")
    source=source.replace("verdicts=[];report=", "protocol['budgets']['waiting_handoff_from_independent_predecessor_success_s']=WAITING;verdicts=[];report=")
    old="  (directory/'verdict.json').write_text(json.dumps(v,ensure_ascii=False,indent=2));verdicts.append(v)"
    assert source.count(old)==1
    source=source.replace(old,"  (report/'cases').mkdir(exist_ok=True);(report/'cases'/(v['case_id']+'.json')).write_text(json.dumps(v,ensure_ascii=False,indent=2));verdicts.append(v)")
    source=source.replace("{d/'verdict.json'}", "{report/'cases'/(v['case_id']+'.json')}")
    source=source.replace("summary.update(valid_for_audio_benchmark=", "summary.update(audit_revision='v1.8-exact-snapshot-qa-and-bound-control-receipts',waiting_handoff_budget_s=WAITING,raw_verdicts_preserved=True,score_source_sha256=AUDIT_HASH,valid_for_audio_benchmark=")
    # Patch the independent judge in memory only; frozen raw scorer unchanged.
    sys.path.insert(0,str(B/'repair6/reference'))
    import score_preflight
    score_preflight.DOC=root/'dataset'
    import score_dev96
    judge=(B/'repair6/reference/score_dev96.py').read_text()
    old="return [m for m in messages if m.get('direction')=='sent' and m.get('type')=='host.playback_started' and t['audio_ended_wall']<=m['time']<=next_wall]"
    assert judge.count(old)==1
    judge=judge.replace(old,old+" + early_control_replies(r,voice,messages,t,next_wall)")
    from continuation.qa_snapshot_audit import score as snapshot_score
    needle="        check('qa_semantics_'+turn['turn_id'],verdict,dict(actual_spoken_text=text,method='bounded_physical_or_task_evidence; otherwise human review'))"
    assert judge.count(needle)==1
    judge=judge.replace(needle,"        snapshot_evidence=None\n        if sid=='T6_01' and answer:\n            verdict,snapshot_evidence=snapshot_score(directory,r,voice,ticks,turn,text,max(p['time']for _,p in answer))\n        check('qa_semantics_'+turn['turn_id'],verdict,snapshot_evidence or dict(actual_spoken_text=text,method='bounded_physical_or_task_evidence; otherwise human review'))")
    score_dev96.__dict__['snapshot_score']=snapshot_score
    score_dev96.__dict__['early_control_replies']=early_control_replies
    exec(compile(judge,str(B/'continuation/generated_audited_judge.py'),'exec'),score_dev96.__dict__)
    argv=sys.argv;sys.argv=['audited_score.py','--label',a.label,'--final'if a.final else'--partial']
    try:
        exec(compile(source,str(B/'continuation/generated_audited_score.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/score.py'),POSITIVE_PAUSE=POSITIVE_PAUSE,pause_evidence=pause_evidence,WAITING=a.waiting,AUDIT_HASH=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    finally:sys.argv=argv

if __name__=='__main__':main()
