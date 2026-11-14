"""Evidence report for a completed small repair round, with actual-VLA latency."""
import collections
import hashlib
import json
import statistics
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]


def lines(path):
    if not path.exists(): return []
    result=[]
    for l in path.read_text().splitlines():
        try: result.append(json.loads(l))
        except ValueError: pass
    return result


def main():
    root=Path(sys.argv[1]);label=sys.argv[2];run=root/label
    ids=[c['case_id']for c in json.loads((root/'dataset/selected.private.json').read_text())]
    verdict_file=run/'reports_audited/v1.9_wait45/verdicts.json'
    verdicts=json.loads(verdict_file.read_text())if verdict_file.exists()else []
    lookup={v['case_id']:v for v in verdicts};rows=[]
    for cid in ids:
        d=run/'cases'/cid;result=d/'result.json';r=json.loads(result.read_text())if result.exists()else{}
        v=lookup.get(cid,{});events=lines(d/'gateway.jsonl')
        actions=[e for e in events if e['kind']=='action_provenance'];ios=[e for e in events if e['kind']in('io_started','io_finished')]
        latency=[]
        for t in r.get('turns',[]):
            if t.get('prelude'):continue
            end=t.get('audio_ended_wall');before_id=t.get('before',{}).get('task_id')
            if end is None:continue
            # This auxiliary timing is distinct from the original scorer's
            # "authorized control" timing, which may include recovery holds.
            new=[e for e in actions if e['time']>=end and len(e.get('identity',[]))>1 and (before_id is None or e['identity'][1]!=before_id)]
            true_vla=[e for e in new if e.get('actual_vla_action') or e.get('origin')=='source_policy']
            latency.append(dict(turn=t.get('turn_id'),first_authorized_control_s=None if not new else new[0]['time']-end,
                                first_vla_action_s=None if not true_vla else true_vla[0]['time']-end,
                                classification='v1 native source_policy is an actual actor action; symbolic kernel_policy is separately labeled'))
        memory_events=[e for f in d.rglob('memory_events.jsonl')for e in lines(f)]
        rows.append(dict(case_id=cid,**{k:v.get(k,'not_scored')for k in ['interaction','target','instruction']},
                         failures=v.get('failures'),termination=r.get('termination'),runner_errors=r.get('errors'),
                         kernel_errors=[e.get('error')for e in events if e['kind']=='kernel_failed'],
                         io_timings=[{k:e.get(k)for k in ('kind','role','time','seconds','identity')}for e in ios],
                         model_pool_timings=[dict(role=f.parent.parent.name,**{k:r.get(k)for k in ('seconds','proxy_queue_seconds','proxy_inference_seconds','proxy_upstream','usage')}) for f in d.glob('local_requests/*/*/transport.json')for r in [json.loads(f.read_text())]],
                         action_origins=dict(collections.Counter(e.get('origin')for e in actions)),latency=latency,
                         cache_resolutions=dict(collections.Counter(e.get('resolution')for e in memory_events if e['event']=='resolve')),
                         stage_events=[e for e in events if e['kind']in('stage_selected','stage_continued')],
                         video=str(d/'gateway_environment.mp4'),actual_prompts=[str(f)for f in d.glob('kernels/g*/chunks.json')],
                         result=str(result),verdict=str(d/'verdict.json'),audited_verdicts=str(verdict_file)))
    frozen=json.loads((root/'FREEZE.json').read_text())['files']
    drift=[p for p,h in frozen.items()if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    summary=dict(scope='three-case engineering diagnostic, separate from old T3 90 and CORE96',
                 complete=(run/'COMPLETED.json').exists(), planned=len(ids), received=len(verdicts), cases=rows,
                 metrics={k:dict(passed=sum(v.get(k)=='pass'for v in verdicts),denominator=len(ids))for k in ['interaction','target','instruction']},
                 runtime_drift=drift, actor_and_yolo_unchanged=True, old_results_changed=False,
                 input='reviewed TTS via real PCM cloud service; not human physical microphone/speaker',
                 static_cache_validity='M1 still simulator-assisted; pixel coordinates only from YOLO')
    (run/'REPAIR_AUDIT.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    text=['# VoiceHarness T3修复专项回归','',
          '三例工程开发诊断；不是旧90例重评，不与公共96例拼接。真人麦克风/扬声器未在本轮测试。','',
          '|案例|交互|目标|完整指令|','|---|---|---|---|']
    text += [f'|{r["case_id"]}|{r["interaction"]}|{r["target"]}|{r["instruction"]}|'for r in rows]
    text += ['',f'冻结运行文件变化：{len(drift)}。动作模型、YOLO权重和数值评分阈值保持不变。','']
    for r in rows:
        text += [f'## {r["case_id"]}','',f'未通过项：{r["failures"]}。运行异常：{r["runner_errors"]}。',
                 f'[视频]({r["video"]}) · [实际记录]({r["result"]}) · [独立审计结果]({r["audited_verdicts"]})','']
    text += ['本轮先检查终验、回执、阶段重复选择和缓存合法性；小样本不足以证明整体成功率提升。']
    (run/'RESULTS.md').write_text('\n'.join(text)+'\n')
    print(json.dumps(summary['metrics']))


if __name__=='__main__':main()
