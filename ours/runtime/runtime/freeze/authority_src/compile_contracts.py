"""Rebind frozen reviewed training semantics to independent evaluation scenes.
This command validates stored contracts; it never regenerates legacy semantics.
"""
import copy,hashlib,json
from pathlib import Path
from functools import lru_cache
from benchmark_metrics.contracts import validate_contract
B=Path(__file__).resolve().parents[1]
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
@lru_cache(None)
def templates(memory=False):
 return json.loads((B/'training_adapter'/('memory_contract_templates.json' if memory else 'contract_templates.json')).read_text())
def compile_one(case,cfg,snapshot):
 ct=copy.deepcopy(templates(case.get('evaluation_split')=='memory')[case['config']]);ct['case_id']=case['case_id'];ct['budget']=case['budget']
 for c in ct['clauses']:
  if c['kind']=='restore_episode_start':c['reference_position']=snapshot['initial_measurement']['all_object_poses'][c['object']]['position']
  elif c['kind']=='preserve_position':c['reference_position']=snapshot['measurement_at_switch']['all_object_poses'][c['object']]['position']
  elif c['kind']=='preserve_articulation_state':c['reference_q']=snapshot['measurement_at_switch']['articulation'][c['joint']]
  elif c['kind']=='preserve_predicate_state':
   assert c['predicate']==['turnon','flat_stove_1'];c['reference_value']=bool(snapshot['measurement_at_switch']['goals']['7'])
 validate_contract(ct);return ct

def main():
 n=0
 for prefix in ['', 'memory_']:
  cases=[json.loads(l) for l in (B/(prefix+'cases.jsonl')).read_text().splitlines()];cts={c['case_id']:c for c in json.loads((B/(prefix+'contracts.json')).read_text())}
  for c in cases:
   sn=json.loads((B/'snapshots'/(c['snapshot_id']+'.json')).read_text());ct=compile_one(c,None,sn)
   assert ct==cts[c['case_id']] and digest(ct)==c['contract_sha256'];n+=1
 print(json.dumps(dict(passed=True,contracts=n)))
if __name__=='__main__':main()
