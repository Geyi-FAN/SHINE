"""Keep all outcomes; compare the exact selected IDs with frozen references."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/mnt/disk_4/geyi/F1_switch308_20261031')
HIST=BASE.parent/'switch_v25_taskcoverage_20261030'


def score(d):return(d.get('metrics')or{}).get('instruction_adjusted',{}).get('success')
def read(p):return json.loads(p.read_text())if p.exists()else None
def main():
    jobs=read(ROOT/'data/jobs.json');spec=read(ROOT/'METHOD.json');n=len(jobs)
    sources=dict(candidate=ROOT/'runs/agent',F1=BASE/'runs/agent',mixed=HIST/'runs/agent',full_oracle=HIST/'runs/full_oracle')
    if spec.get('dataset','development308')!='development308':sources=dict(candidate=ROOT/'runs/agent')
    if spec.get('full_oracle_arm'):sources['full_oracle']=ROOT/'runs/full_oracle'
    if spec.get('oracle_only'):sources.pop('candidate',None)
    if spec.get('parent_version'):sources['parent']=ROOT/'runs/parent'
    if spec.get('reference_study'):sources['historical_candidate']=ROOT.parent/spec['reference_study']/'runs/agent'
    stats={};records={};rows=[];groups=defaultdict(dict)
    for arm,source in sources.items():
        counts=Counter(expected=n);grouped=defaultdict(Counter)
        for job in jobs:
            case=job['case'];p=source/case['case_id']/'result.json';d=read(p)
            if d is None:continue
            if d.get('status')in[None,'runtime_error','blocked_external_api']:
                counts['runtime_error']+=1;continue
            value=score(d);normal=value is True and d['status']=='switch_oracle_contract_completed'
            counts['valid']+=1;counts['success']+=value is True;counts['normal']+=normal;counts['unknown']+=value is None
            records[arm,case['case_id']]=d
            for c in [grouped[case['group']]]:
                c['valid']+=1;c['success']+=value is True;c['normal']+=normal;c['unknown']+=value is None
            metrics=d.get('metrics')or{}
            clauses=metrics.get('instruction_adjusted',{}).get('clauses_at_evaluation_step',{})
            rows.append(dict(arm=arm,case_id=case['case_id'],group=case['group'],
                full_instruction=case['public_user_instruction'],complete=value,normal=normal,status=d['status'],
                steps=d.get('actions'),selected_stages=json.dumps(d.get('selected_stages'),ensure_ascii=False),
                completed_events=json.dumps(d.get('execution_events'),ensure_ascii=False),
                blocked_reason=d.get('blocked_reason'),failed_clauses=json.dumps({k:v for k,v in clauses.items()if v.get('value')is False},ensure_ascii=False),
                video=str(p.parent/'policy_input.mp4')if(p.parent/'policy_input.mp4').exists()else'',
                initial_main=str(p.parent/'points/0_current.png'),agent_io=str(p.parent/'agent_calls.json'),result=str(p)))
        stats[arm]=dict(counts)
        for key,data in grouped.items():groups[key][arm]=dict(data)
    comparisons={};mismatches=[]
    for ref in [name for name in sources if name!='candidate']:
        c=Counter()
        for job in jobs:
            cid=job['case']['case_id'];a=records.get(('candidate',cid));b=records.get((ref,cid))
            if a is None or b is None:continue
            for key in ['start_state_identity','rules_sha256','budget','source_snapshot_sha256','policy_seed','public_full_instruction','published_stop_policy']:
                if a.get(key)!=b.get(key):mismatches.append(dict(case_id=cid,reference=ref,field=key))
            x,y=score(a),score(b)
            kind='unknown'if x is None or y is None else'both_success'if x is True and y is True else'candidate_only'if x is True else'reference_only'if y is True else'both_failed'
            c[kind]+=1
        comparisons[ref]=dict(c)
    summary=dict(study=spec['study'],version=spec['version'],scope=spec['scope'],expected=n,
        arms=stats,groups=dict(groups),paired=comparisons,control_mismatches=mismatches,
        paid_calls=0,updated_unix=time.time(),state='completed'if all(stats[arm].get('valid')==n for arm in ([]if spec.get('oracle_only')else['candidate'])+(['parent']if spec.get('parent_version')else[])+(['full_oracle']if spec.get('full_oracle_arm')else[]))else'running')
    for path in [ROOT/'PROGRESS.json',ROOT/'reports/summary.json']:
        tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(summary,ensure_ascii=False,indent=2));tmp.replace(path)
    with(ROOT/'reports/all_cases.csv').open('w',newline='')as f:
        if rows:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    lines=['# '+spec['study'],'',spec['scope'],'','|方案|完成|明确完整成功|成功且正常收尾|未评分|','|---|---:|---:|---:|---:|']
    for arm,c in stats.items():lines.append('|'+arm+'|'+str(c.get('valid',0))+'/'+str(n)+'|'+str(c.get('success',0))+'|'+str(c.get('normal',0))+'|'+str(c.get('unknown',0))+'|')
    lines+=['','配对：'+json.dumps(comparisons,ensure_ascii=False),'','控制条件不一致：'+json.dumps(mismatches,ensure_ascii=False),'',
        '无按case标签分支，无Oracle答案输入规划，无最佳重试选择；原版评分、执行器与预算保持冻结。集合属性见上方scope。']
    (ROOT/'reports/RESULTS.md').write_text('\n'.join(lines)+'\n')
    subprocess.run([sys.executable,str(ROOT/'scripts/enrich_failures.py')],check=True,stdout=subprocess.DEVNULL)
    print(json.dumps(summary['arms'],ensure_ascii=False))


if __name__=='__main__':main()
