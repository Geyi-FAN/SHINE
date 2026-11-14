"""Apply one fixed logical gate to all90 model judgments, not selected cases."""
import hashlib,json,time
from pathlib import Path
from reference_guards import check
R=Path(__file__).resolve().parent;V=R/'v3'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 source=V/'final90';assert(source/'COMPLETED.json').exists()
 out=R/'fixed_v4';out.mkdir(exist_ok=False)
 proto=dict(version='T6-fixed-hybrid-judge-v4-20261109',semantic_model='GLM-4.6V',
   underlying_model_protocol=read(source/'PROTOCOL.json'),underlying_model_summary_sha256=sha(source/'SUMMARY.json'),
   deterministic_guards='explicit referent substitution => fail; occupant/empty uncertainty conflict => independent review',
   guard_source_sha256=sha(R/'reference_guards.py'),script_sha256=sha(R/'apply_fixed_guards.py'),
   old_assistant_labels_read=False,all90_uniformly_processed=True,semantic_API_calls_added=0,
   human_independent_review_completed=False,frozen_at=time.time(),
   policy='Never use Codex to silently replace model semantic labels. Pending remains in denominator; no score-based retries.')
 (out/'PROTOCOL.json').write_text(json.dumps(proto,ensure_ascii=False,indent=2)+'\n')
 rows=[]
 for row in read(source/'SUMMARY.json')['rows']:
  folder=source/row['packet_id'];label=read(folder/'JUDGMENT.json')
  packet=read(V/'packets'/(row['packet_id']+'.json'))
  result=check(packet,label);item=dict(row,reference_guard=result,model_interaction=row['interaction'])
  if result['status']=='fail':item.update(interaction='fail',qualified_QA='fail',status='referent_failure')
  elif result['status']=='review_required':item.update(interaction='unknown',qualified_QA='unknown',status='independent_review_required')
  rows.append(item)
 summary=dict(version=proto['version'],planned=90,adjudicated=90,confirmed_pass=sum(r['interaction']=='pass'for r in rows),
   failed=sum(r['interaction']=='fail'for r in rows),pending_independent_review=sum(r['interaction']=='unknown'for r in rows),
   underlying_model_pass=sum(r['model_interaction']=='pass'for r in rows),rows=rows,
   not_new_robot_rollouts=True,old_assistant_83_unchanged=True)
 (out/'SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({k:v for k,v in summary.items()if k!='rows'},ensure_ascii=False))
if __name__=='__main__':main()
