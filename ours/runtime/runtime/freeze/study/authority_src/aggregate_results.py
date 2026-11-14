"""Summarize complete/partial benchmark results without hiding unknown cases."""
import argparse,collections,hashlib,json
from pathlib import Path
B=Path(__file__).resolve().parents[1]
KEYS=['target_native','target_adjusted','instruction_native','instruction_adjusted']
def summarize(results,cases):
 known={c['case_id']:c for c in cases};seen={};signatures=set()
 for r in results:
  cid=r['case_id']
  if cid not in known:raise ValueError('Unknown case: '+cid)
  if cid in seen:raise ValueError('Duplicate result: '+cid)
  if r.get('smoke_only'):raise ValueError('Smoke runs are not benchmark model results')
  if known[cid].get('benchmark_id'):
   if r.get('benchmark_id')!=known[cid]['benchmark_id'] or r.get('case_contract_sha256')!=known[cid]['contract_sha256']:raise ValueError('Benchmark version or contract mismatch: '+cid)
  seen[cid]=r
  signature={k:r.get(k) for k in ['policy_label','policy_metadata','observation_profile','observation_protocol','instruction_protocol','execute_steps','budget','method','execution_protocol','privileged_inputs','benchmark_id','prompt_order']}
  signatures.add(json.dumps(signature,sort_keys=True))
 if len(signatures)>1:raise ValueError('Mixed model/protocol signatures; summarize separately')
 def group_summary(ids):
  rows=[seen[cid] for cid in ids if cid in seen];completed=[r for r in rows if r.get('status')=='completed'];counts={}
  for key in KEYS:
   vals=[r.get('metrics',{}).get(key,{}).get('success') for r in completed]
   passed=sum(v is True for v in vals);failed=sum(v is False for v in vals);unknown=len(vals)-passed-failed
   counts[key]=dict(pass_count=passed,fail_count=failed,unknown_count=unknown,completed_denominator=len(vals),observed_success_fraction=passed/len(vals) if vals else None,formal_success_fraction=passed/len(ids) if len(completed)==len(ids) else None)
  counts['target_sr']=counts['target_adjusted'];counts['instruction_sr']=counts['instruction_adjusted']
  return dict(expected=len(ids),completed=len(completed),runtime_errors=len(rows)-len(completed),missing=len(ids)-len(rows),metrics=counts)
 groups={}
 for name,fn in [('evaluation_split',lambda c:c.get('evaluation_split','switch')),('source_task',lambda c:f"T{c['source_task']:02d}"),('source_phase',lambda c:f"T{c['source_task']:02d}_{c['source_phase']}"),('config',lambda c:c['config']),('intent',lambda c:c['branch']),('execution_order_category',lambda c:c.get('category','unspecified'))]:
  buckets=collections.defaultdict(list)
  for c in cases:buckets[fn(c)].append(c['case_id'])
  groups[name]={key:group_summary(ids) for key,ids in sorted(buckets.items())}
 return dict(overall=group_summary(list(known)),groups=groups,unknown_policy='Unknown stays in completed denominator and is reported separately; full benchmark rate withheld while cases are missing/errors',run_signature=json.loads(next(iter(signatures))) if signatures else None)
def main():
 p=argparse.ArgumentParser();p.add_argument('--results',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--suite',choices=['switch','memory','all'],default='switch');a=p.parse_args()
 prefixes={'switch':[''],'memory':['memory_'],'all':['','memory_']}[a.suite]
 cases=[json.loads(l) for prefix in prefixes for l in (B/(prefix+'cases.jsonl')).read_text().splitlines()];results=[json.loads(p.read_text()) for p in a.results.rglob('result.json')]
 report=summarize(results,cases);report['cases_sha256']=hashlib.sha256((B/'cases.jsonl').read_bytes()).hexdigest();a.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report['overall'],ensure_ascii=False))
if __name__=='__main__':main()
