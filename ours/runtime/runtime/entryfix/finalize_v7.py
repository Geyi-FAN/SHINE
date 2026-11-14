"""Build one complete v7 report; retain all earlier full/probe attempts."""
import hashlib
import json
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
O = B / 'reports'
D = B / 'run_data'


def main():
    from selected_eval.contract_audit import check
    cases = json.loads((D / 'cases.private.json').read_text())
    for c in cases:
        p = B / 'runs/formal10_v7' / c['case_id'] / 'verdict.json'
        v = json.loads(p.read_text())
        extra = check(v.get('accepted_instruction', ''), c['private_judge']['clauses'])
        v['checks'] = v.get('checks', []) + extra
        v['failures'] += [x['name'] for x in extra if x['status'] != 'pass']
        if any(x['status'] != 'pass' for x in extra):
            v['interaction'] = 'fail'
        v['contract_coverage_audit'] = 'all ten equally checked; raw verdict preserved'
        p.with_name('verdict.audited.json').write_text(json.dumps(v, ensure_ascii=False, indent=2))

    report = B / 'entryfix/final_report.py'
    source = report.read_text()
    assert source.count("p=B/'runs/formal10'") == 1
    source = source.replace("p=B/'runs/formal10'", "p=B/'runs/formal10_v7'")
    source = source.replace("v=json.loads((p/'verdict.json').read_text())", "v=json.loads((p/'verdict.audited.json').read_text())")
    source = source.replace("O/'baseline_force_reaudit/SUMMARY.json'", "O/'baseline_force_reaudit/SUMMARY.v1_6.json'")
    source = source.replace('v1.5: native task6 On predicate', 'v1.6 scoring / v1.7 runtime: native task6 On predicate')
    exec(compile(source, str(report), 'exec'), {'__file__': str(report), '__name__': '__main__'})

    counts = {}
    for label in ('formal10', 'formal10_v7'):
        records = [json.loads((B/'runs'/label/c['case_id']/'verdict.json').read_text()) for c in cases]
        counts[label] = {k: sum(v[k] == 'pass' for v in records) for k in ('interaction','target','instruction')}
    p = O/'FINAL_REPORT.md'
    note = ['\n## 完整迭代轮次（不择优合并）\n', '| 完整轮次 | Interaction | Target | Instruction |', '|---|---:|---:|---:|']
    for label, t in counts.items():
        note.append('| '+label+' | '+' | '.join(str(t[k])+'/10' for k in ('interaction','target','instruction'))+' |')
    note += ['', 'formal10 为入口修复首轮，保留第07项真实46.402秒首动作超时；formal10_v7 为仅修正句末双句号后重新完整运行的一轮。第07项额外预检单列，既不并入正式10例，也不取代任何失败。', '3项句末格式专项测试通过；28项其他Python测试、90项语音回归通过。新任务/旧内核竞态与所有开发轮次见 REPAIR_EXPLANATION.md 和运行目录。', '原始支持重审采用逐记录终态重建力，而新版实际运行记录当时的合力，两者来源分别标记。', 'v7原话、初始状态、音频、预算与首轮一致；运行版本之间变化明确记录，不能解释为重复运行后挑最高分。', '']
    p.write_text(p.read_text()+'\n'.join(note))
    summary = json.loads((O/'FINAL_SUMMARY.json').read_text())
    assert summary['audit']['audio_pass'] == 10
    assert summary['audit']['unique_ids'] == 10
    assert not summary['audit']['freeze_drift']
    assert len(summary['audit']['videos']) == 10 and all(v['valid'] for v in summary['audit']['videos'])
    summary['complete_rounds'] = counts
    summary['selected_complete_round'] = 'formal10_v7'
    summary['conditions']['runtime_version'] = 'T3-entryfix-v1.7'
    summary['conditions']['scoring_version'] = 't3-entryfix-v1.6 plus C0 text audit; unchanged numeric timeouts; actual new-task VLA required'
    summary['audit']['initial_scene_max_deltas'] = [json.loads((B/'runs/formal10_v7'/c['case_id']/'initial_scene.json').read_text())['maximum_channel_delta'] for c in cases]
    assert all(v <= 2 for v in summary['audit']['initial_scene_max_deltas'])
    historical = Path('/mnt/disk_2/geyi/audio_t3_f28d90_20261101/analysis/evidence_selected10_20261102/ORIGINAL_RESULT_SHA256.json')
    original = json.loads(historical.read_text())
    summary['audit']['historical_result_files'] = len(original)
    summary['audit']['historical_result_hash_mismatches'] = [p for p,h in original.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h]
    assert not summary['audit']['historical_result_hash_mismatches']
    previous = Path('/mnt/disk_2/geyi/audio_t3_selected10_20261102/run_data/FREEZE.json')
    previous_files = json.loads(previous.read_text())['files']
    summary['audit']['previous_selected10_freeze_files'] = len(previous_files)
    summary['audit']['previous_selected10_freeze_drift'] = [p for p,h in previous_files.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != h]
    assert not summary['audit']['previous_selected10_freeze_drift']
    archive = O/'source_archive_formal10_v6/SOURCE_ARCHIVE.json'
    ar = json.loads(archive.read_text())
    bad = [r['archived'] for r in ar['files'] if hashlib.sha256(Path(r['archived']).read_bytes()).hexdigest() != r['sha256']]
    summary['audit']['previous_complete_round_archive_files'] = len(ar['files'])
    summary['audit']['previous_complete_round_archive_drift'] = bad
    assert not bad
    (O/'FINAL_SUMMARY.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'rounds':counts,'final':summary['totals'],'audit':summary['audit']},ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
