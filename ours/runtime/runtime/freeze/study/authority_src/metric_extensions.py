"""Explicit v3.2 logical invariants layered over the unchanged v2.5 scorer.
Both kinds require their truth on every policy frame, like existing containment.
Missing measurements remain unknown. No new numeric tolerances are introduced.
"""
import copy
from benchmark_metrics import evaluate_episode as evaluate_v25
from benchmark_metrics.config import fingerprint
from benchmark_metrics.contracts import SUPPORTED as BASE_SUPPORTED
VERSION='switch-explicit-invariants-v1'
SUPPORTED=BASE_SUPPORTED|{'preserve_predicate_state','preserve_relation'}
def evaluate_episode(trace,case,contract,rules=None):
 extras=[c for c in contract['clauses'] if c['kind'] in {'preserve_predicate_state','preserve_relation'}]
 unknown={c['kind'] for c in contract['clauses']}-SUPPORTED
 if unknown:raise ValueError(('Unsupported formal clauses',sorted(unknown)))
 if not extras:
  out=evaluate_v25(trace,case,contract,rules);out['metric_adapter_version']=VERSION;return out
 adapted=copy.deepcopy(contract);frames=[]
 for row in trace['measurements']:
  m=dict(row);ev=copy.deepcopy(row.get('metric_evidence',{}));values=ev.setdefault('containment',{})
  for c in extras:
   key='predicates' if c['kind']=='preserve_predicate_state' else 'relations'
   value=ev.get(key,{}).get(c['id'])
   if value is not None and type(value) is not bool:raise ValueError('Logical evidence must be bool or missing')
   if c['kind']=='preserve_predicate_state':
    if type(c['reference_value']) is not bool:raise ValueError('Predicate reference must be bool')
    value=None if value is None else value==c['reference_value']
   values[c['id']]=value
  m['metric_evidence']=ev;frames.append(m)
 for c in adapted['clauses']:
  if c['kind'] in {'preserve_predicate_state','preserve_relation'}:c['kind']='preserve_containment'
 transformed=dict(trace,measurements=frames);out=evaluate_v25(transformed,case,adapted,rules)
 out['contract_sha256']=fingerprint(contract);out['metric_adapter_version']=VERSION
 for c in extras:
  cid=c['id'];code='STOVE_SWITCH_STATE_CHANGED' if c['kind']=='preserve_predicate_state' else 'REQUIRED_PAYLOAD_RELATION_LOST'
  reason='炉灶的开／关状态发生改变' if c['kind']=='preserve_predicate_state' else '奶酪由碗承载的关系被破坏'
  comp=out['components'][cid]
  if comp['last_state'] is False:comp.update(failure_code=code,failure_reason_zh=reason)
  for key in ['instruction_native','instruction_adjusted']:
   item=out[key]['clauses_at_evaluation_step'].get(cid)
   if item and item['value'] is False:item.update(reason_code=code,reason_zh=reason)
 return out
