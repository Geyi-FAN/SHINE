"""Portable CLI. Outputs are new artifacts, never historical result rewrites."""
import argparse
import gzip
import json
from pathlib import Path
from .config import load_rules, fingerprint
from .contracts import validate_contract
from .evaluator import evaluate_episode

def read_json(path):
    path=Path(path)
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt') as stream:return json.load(stream)

def aggregate(results):
    out={}
    for metric in ['target_native','target_adjusted','instruction_native','instruction_adjusted']:
        values=[r[metric]['success'] for r in results];n=len(values)
        passed=sum(v is True for v in values);unknown=sum(v is None for v in values)
        out[metric]={'total':n,'pass':passed,'fail':sum(v is False for v in values),'unknown':unknown,
                     'success_rate':passed/n if n and not unknown else None,
                     'lower_bound':passed/n if n else None,'upper_bound':(passed+unknown)/n if n else None}
    return out

def main():
    p=argparse.ArgumentParser(description='Small722 versioned benchmark metrics')
    p.add_argument('--rules',type=Path)
    sub=p.add_subparsers(dest='command',required=True)
    v=sub.add_parser('validate');v.add_argument('--contracts',type=Path,required=True)
    e=sub.add_parser('evaluate');e.add_argument('--contracts',type=Path,required=True)
    e.add_argument('--cases',type=Path,required=True,help='Canonical cases.jsonl')
    e.add_argument('--manifest',type=Path,required=True,help='JSON list of {case_id,trace}; paths relative to manifest')
    e.add_argument('--output',type=Path,required=True)
    args=p.parse_args();rules=load_rules(args.rules);contracts=read_json(args.contracts)
    ids=[c['case_id'] for c in contracts]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate contracts')
    for c in contracts:validate_contract(c)
    if args.command=='validate':
        print(json.dumps({'contracts':len(contracts),'rules_version':rules['version'],'rules_sha256':fingerprint(rules)},indent=2));return
    if args.output.exists():raise FileExistsError('Choose a new output path; original reports are immutable')
    case_list=[json.loads(line) for line in args.cases.read_text().splitlines() if line.strip()]
    cases={c['case_id']:c for c in case_list};contracts={c['case_id']:c for c in contracts}
    if len(cases)!=len(case_list):raise ValueError('Duplicate cases')
    jobs=read_json(args.manifest);seen=set();rows=[]
    for job in jobs:
        cid=job['case_id']
        if cid in seen:raise ValueError('Duplicate manifest cases')
        seen.add(cid);path=Path(job['trace'])
        if not path.is_absolute():path=args.manifest.parent/path
        row=evaluate_episode(read_json(path),cases[cid],contracts[cid],rules)
        row['trace_sha256']=__import__('hashlib').sha256(path.read_bytes()).hexdigest();rows.append(row)
    report={'rules':rules,'rules_sha256':fingerprint(rules),'summary':aggregate(rows),'cases':rows}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # Exclusive create prevents accidentally replacing a report after a race.
    with args.output.open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2))
