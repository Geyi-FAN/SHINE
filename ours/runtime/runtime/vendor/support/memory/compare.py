"""Paired-case checks and success transitions, never combine mismatched protocols."""
import argparse,itertools,json
from pathlib import Path
from common import write_json

def main():
 p=argparse.ArgumentParser();p.add_argument('--evaluation-root',type=Path,required=True);p.add_argument('--variants',default='ABCD');a=p.parse_args();models={}
 for v in a.variants:
  root=a.evaluation_root/v;assert (root/'COMPLETED.json').is_file();models[v]={x['case_id']:x for f in (root/'results').glob('*.json') for x in [json.loads(f.read_text())]}
 ref=models[a.variants[0]]
 for v,rows in models.items():
  assert rows.keys()==ref.keys()
  for cid,r in rows.items():
   for k in ['protocol_id','context_sha256','start_state_identity','first_common_input_sha256','budget','diagnostic_budget_override']:assert r[k]==ref[cid][k],(v,cid,k)
   assert r['status']!='runtime_error'
 report={}
 for x,y in itertools.combinations(a.variants,2):
  rows=[]
  for cid in ref:
   u=models[x][cid];v=models[y][cid];rows.append(dict(case_id=cid,group=u['group'],first=u['complete'],second=v['complete']))
  def counts(rs):return dict(total=len(rs),both_success=sum(r['first'] and r['second'] for r in rs),first_only=sum(r['first'] and not r['second'] for r in rs),second_only=sum(not r['first'] and r['second'] for r in rs),both_fail=sum(not r['first'] and not r['second'] for r in rs))
  report[x+'_'+y]=dict(**counts(rows),groups={g:counts([r for r in rows if r['group']==g]) for g in sorted({r['group'] for r in rows})},cases=rows)
 write_json(a.evaluation_root/'paired_comparison.json',report)
if __name__=='__main__':main()
