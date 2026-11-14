"""Read-only paired audit of all old cases; no old verdict is overwritten."""
import hashlib
import json
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
W = Path('/mnt/disk_2/geyi/audio_t3_f28d90_20261101')
ROOT = Path('/mnt/disk_4/geyi/audio_t3_f28d90_candidate_20261102/resume32_4gpu_20261102_1250')
sys.path.insert(0, str(B))
sys.path.insert(0, str(W/'scoring'))
import score_t3
from t1_contract import instruction_goal
from t3repair.scoring import goal_from_full, restore_radius, VERSION


def main():
    cases = json.loads((ROOT/'data/selected.private.json').read_text())
    rules = json.loads((ROOT/'data/physical_rules.json').read_text())
    rows, preserved = [], {}
    for c in cases:
        directory = ROOT/'cases'/c['case_id']
        verdict_file = directory/'verdict.json'
        preserved[str(verdict_file)] = hashlib.sha256(verdict_file.read_bytes()).hexdigest()
        v = json.loads(verdict_file.read_text())
        text = v.get('accepted_instruction', '')
        radii = []
        for clause in c['private_judge']['clauses']:
            if clause['kind'] == 'restore_episode_start':
                ctx = dict(source_task=c['source_task'], previous_instruction=c['source_text'])
                radii.append(dict(old=score_t3.restore_radius(ctx, clause, rules), new=restore_radius(ctx, clause, rules)))
        rows.append(dict(case_id=c['case_id'], text=text, expected_target=c['target_task'],
                         old_goal=score_t3.goal_from_full(text), new_goal=goal_from_full(text, instruction_goal),
                         restore_radii=radii))
    changed = [r for r in rows if r['old_goal'] != r['new_goal'] or any(a['old'] != a['new'] for a in r['restore_radii'])]
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p,h in preserved.items())
    result = dict(version=VERSION, scope='parser/radius audit only; no new robot rollout or recalculated physical success rate',
                  cases=len(rows), changed=changed, rows=rows, old_verdict_sha256=preserved, old_verdicts_unchanged=True,
                  numeric_thresholds_unchanged=True)
    path=B/'reports/SCORING_PAIRED_AUDIT.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(dict(cases=len(rows), changed=len(changed), parser_changed=sum(r['old_goal']!=r['new_goal']for r in changed), radius_changed=sum(any(a['old']!=a['new']for a in r['restore_radii'])for r in changed), old_verdicts_unchanged=True)))


if __name__ == '__main__': main()
