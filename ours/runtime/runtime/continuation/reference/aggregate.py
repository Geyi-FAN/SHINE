"""Aggregate independently judged verdicts against a FIXED case manifest.

Not a trajectory judge: no Harness completion flag is accepted as evidence.
Expected verdict fields: case_id, interaction, target, instruction (pass/fail/unknown/na).
"""
import argparse
import json
from pathlib import Path


def summarize(cases, verdicts):
    ids = [c['case_id'] for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate planned case')
    result = {}
    for v in verdicts:
        cid = v['case_id']
        if cid not in ids or cid in result:
            raise ValueError('Unexpected or duplicate verdict: '+cid)
        result[cid] = v
    scored = []
    for c in cases:
        v = result.get(c['case_id'], dict(interaction='unknown', target='unknown', instruction='unknown'))
        if any(v.get(k) not in {'pass','fail','unknown','na'} for k in ['interaction','target','instruction']):
            raise ValueError('Invalid or missing metric status')
        if v['interaction'] == 'na' or (c['physical_eligible'] and (v['target']=='na' or v['instruction']=='na')):
            raise ValueError('Eligible metric cannot be NA')
        if c['physical_eligible'] and v['instruction']=='pass' and v['target']!='pass':
            raise ValueError('Instruction pass requires Target pass')
        scored.append(dict(c, verdict=v))

    def rate(rows, metric):
        eligible = rows if metric in {'interaction','joint'} else [r for r in rows if r['physical_eligible']]
        passed = sum((r['verdict']['interaction']=='pass' and (not r['physical_eligible'] or r['verdict']['instruction']=='pass'))
                     if metric=='joint' else r['verdict'][metric]=='pass' for r in eligible)
        return dict(passed=passed, denominator=len(eligible), rate=passed/len(eligible) if eligible else None)
    groups = {g:{k:rate([r for r in scored if r['category']==g],k) for k in ['interaction','target','instruction','joint']}
              for g in sorted({c['category'] for c in cases})}
    macro = {}
    for k in ['interaction','target','instruction','joint']:
        values = [g[k]['rate'] for g in groups.values() if g[k]['rate'] is not None]
        macro[k] = sum(values)/len(values) if values else None
    return dict(planned=len(cases), received=len(result), missing=len(cases)-len(result),
                unknown={k:sum(r['verdict'][k]=='unknown' for r in scored if k=='interaction' or r['physical_eligible']) for k in ['interaction','target','instruction']},
                micro={k:rate(scored,k) for k in ['interaction','target','instruction','joint']},
                macro=macro, groups=groups, note='Unknown/missing are not passes and remain in denominators; no trajectory judging performed here.')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=Path,required=True)
    p.add_argument('--verdicts',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    a.out.write_text(json.dumps(summarize(json.loads(a.cases.read_text()),json.loads(a.verdicts.read_text())),ensure_ascii=False,indent=2)+'\n')
