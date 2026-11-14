"""One fixed GLM-4.6V judgment per anonymous packet; preserve every response."""
import argparse,copy,csv,hashlib,json,statistics,time
from pathlib import Path
from client import call,content,parse_json,image_part
R=Path(__file__).resolve().parent;N=R.parent.parent;B=N.parents[1]
OLD=B/'deployments/our_T3_T1_T6_repair_20261109/t6_adjudication_20261109'

def read(p):return json.loads(Path(p).read_text())
def write(p,d):
 p=Path(p);tmp=p.with_suffix(p.suffix+'.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def validate(d,outputs):
 keys={'verdict','relevant_output_keys','relevant','complete','all_relevant_claims_supported','grounded_uncertainty','wrong_fact_already_spoken','reason_code','reason','claims'}
 if set(d)!=keys:raise ValueError('schema_keys')
 if d['verdict']not in ['pass','fail','insufficient_evidence']:raise ValueError('verdict')
 for k in ['relevant','complete','all_relevant_claims_supported','grounded_uncertainty','wrong_fact_already_spoken']:
  if type(d[k])is not bool:raise ValueError('boolean_required:'+k)
 if not isinstance(d['reason'],str)or not d['reason'].strip():raise ValueError('reason_required')
 valid={(o['output_id'],o['epoch'])for o in outputs};chosen=[]
 if not isinstance(d['relevant_output_keys'],list):raise ValueError('output_keys_list')
 for k in d['relevant_output_keys']:
  if not isinstance(k,dict)or set(k)!={'output_id','epoch'}or type(k['output_id'])is not int or type(k['epoch'])is not int:raise ValueError('output_key_schema')
  pair=k['output_id'],k['epoch']
  if pair not in valid or pair in chosen:raise ValueError('unknown_or_duplicate_output_key')
  chosen.append(pair)
 if not isinstance(d['claims'],list):raise ValueError('claims_required')
 for c in d['claims']:
  if set(c)!={'output_id','epoch','claim','status','evidence'}or(c['output_id'],c['epoch'])not in chosen:raise ValueError('claim_link')
  if c['status']not in ['supported','contradicted','not_established']:raise ValueError('claim_status')
 if d['verdict']=='pass'and(not chosen or not all(d[k]for k in ['relevant','complete','all_relevant_claims_supported'])or d['wrong_fact_already_spoken']or not d['claims']or any(c['status']!='supported'for c in d['claims'])):raise ValueError('inconsistent_pass')
 return d

def qualify(label,outputs,control):
 if label['verdict']=='insufficient_evidence':return dict(status='semantic_unknown',interaction='unknown',qualified_QA='unknown')
 ids={(x['output_id'],x['epoch'])for x in label['relevant_output_keys']}
 relevant=[o for o in outputs if(o['output_id'],o['epoch'])in ids]
 delivered=bool(relevant)and any(o['first_pcm_latency_s']is not None and o['first_pcm_latency_s']<=20 for o in relevant)and all(
  o['valid_clocked_complete']and o['completion_latency_s']is not None and o['completion_latency_s']<=40 for o in relevant)
 semantic=label['verdict']=='pass'
 qa=semantic and delivered and not label['wrong_fact_already_spoken']
 return dict(status='adjudicated',semantic_correct=semantic,audio_deadlines_passed=delivered,
             qualified_QA='pass'if qa else'fail',no_qa_control_error=control['no_qa_control_error'],
             interaction='pass'if qa and control['no_qa_control_error']else'fail')

def request(packet,protocol):
 p=copy.deepcopy(packet);images=[]
 for frame in p['current_QA_images']:
  path=Path(frame.pop('local_image'))
  if sha(path)!=frame['sha256']:raise ValueError('image_hash_changed')
  images.append(image_part(path))
 # No case IDs, previous labels, online self-review, timing passes, or method name.
 user=[dict(type='text',text=json.dumps(p,ensure_ascii=False)),*images]
 c=protocol['semantic_judge']
 return dict(model=c['model'],temperature=c['temperature'],top_p=c['top_p'],max_tokens=c['max_tokens'],thinking=c['thinking'],
             messages=[dict(role='system',content=(R/'SYSTEM_PROMPT.txt').read_text()),dict(role='user',content=user)])

def main():
 a=argparse.ArgumentParser();a.add_argument('--out',type=Path,required=True);a.add_argument('--repeat-audit',action='store_true');args=a.parse_args()
 args.out.mkdir(parents=True,exist_ok=False)
 protocol=read(R/'PROTOCOL.json');mapping=read(R/'PRIVATE_CASE_MAP.json')
 source=read(OLD/'EVIDENCE.json');by_case={r['case_id']:r for r in source}
 controls={r['case_id']:r for r in read(OLD/'CONTROL_AUDIT.json')}
 paths=[R/'PROTOCOL.json',R/'SYSTEM_PROMPT.txt',R/'run_judge.py',R/'client.py',R/'build_packets.py',R/'PRIVATE_CASE_MAP.json']
 frozen={str(p):sha(p)for p in paths}
 write(args.out/'FROZEN_JUDGE.json',dict(version=protocol['version'],source_sha256=frozen,
    frozen_at=time.time(),full_cohort_size=90,judge_model=protocol['semantic_judge']['model'],previous_labels_not_in_requests=True,
    primary_first_call_only=True,independent_human_calibration_completed=False,provider_immutable_revision_available=False))
 rows=[]
 def save():
  summary=dict(planned=90,completed=len(rows),semantic_pass=sum(x.get('semantic_correct')is True for x in rows),
    qualified_QA=sum(x.get('qualified_QA')=='pass'for x in rows),interaction=sum(x.get('interaction')=='pass'for x in rows),
    unknown=sum(x.get('interaction')=='unknown'for x in rows),failed=sum(x.get('interaction')=='fail'for x in rows),
    missing=90-len(rows),rows=rows,version=protocol['version'],updated_at=time.time(),primary='first_model_judgment',
    old_assistant_score_unchanged=True,not_a_new_system_rollout=True)
  write(args.out/'PROGRESS.json',summary)
  return summary
 save()
 for item in sorted(mapping,key=lambda x:x['packet_id']):
  assert all(sha(p)==h for p,h in frozen.items()),'judge_source_changed'
  packet=read(R/'packets'/(item['packet_id']+'.json'))
  assert sha(R/'packets'/(item['packet_id']+'.json'))==item['packet_sha256']
  row=dict(index=item['index'],case_id=item['case_id'],packet_id=item['packet_id'],status='pending',interaction='unknown',qualified_QA='unknown')
  folder=args.out/item['packet_id']
  try:
   answer=call(request(packet,protocol),folder,protocol['semantic_judge']['api_timeout_seconds'])
   if answer.get('model')!=protocol['semantic_judge']['model']:raise ValueError('returned_model_mismatch')
   label=validate(parse_json(content(answer)),packet['spoken_outputs'])
   write(folder/'JUDGMENT.json',label)
   row.update(qualify(label,by_case[item['case_id']]['outputs'],controls[item['case_id']]),
              verdict=label['verdict'],reason_code=label['reason_code'],reason=label['reason'])
  except Exception as e:
   row.update(status='judge_error',error_type=type(e).__name__,error=str(e)[:160])
  rows.append(row);save()
  print(json.dumps({k:row.get(k)for k in ['index','status','interaction','reason_code']},ensure_ascii=False),flush=True)
 summary=save();write(args.out/'SUMMARY.json',summary)
 # Post-hoc comparison is strictly outside the model input and cannot alter its labels.
 previous=read(OLD/'LABELS.json')
 if isinstance(previous,list):previous={x['case_id']:x for x in previous}
 if isinstance(previous,dict)and'all' in previous:previous=previous['all']
 comparison=[]
 for row in rows:
  before=previous.get(row['case_id'],{})
  comparison.append(dict(case_id=row['case_id'],index=row['index'],old_assistant_semantic=before.get('semantic_correct'),
     fixed_model_semantic=row.get('semantic_correct'),model_verdict=row.get('verdict'),reason=row.get('reason'),
     label_difference=before.get('semantic_correct')!=row.get('semantic_correct')))
 write(args.out/'ASSISTANT_COMPARISON.json',comparison)
 if args.repeat_audit:
  audit=[]
  for item in sorted(mapping,key=lambda x:hashlib.sha256(x['packet_id'].encode()).hexdigest())[:10]:
   packet=read(R/'packets'/(item['packet_id']+'.json'));original=next(x for x in rows if x['packet_id']==item['packet_id'])
   try:
    answer=call(request(packet,protocol),args.out/('repeat_'+item['packet_id']),protocol['semantic_judge']['api_timeout_seconds'])
    label=validate(parse_json(content(answer)),packet['spoken_outputs'])
    audit.append(dict(packet_id=item['packet_id'],first=original.get('verdict'),second=label['verdict'],same=original.get('verdict')==label['verdict']))
   except Exception as e:audit.append(dict(packet_id=item['packet_id'],error_type=type(e).__name__,same=None))
  write(args.out/'REPEATABILITY_AUDIT.json',dict(rows=audit,primary_scores_not_overwritten=True))
 write(args.out/'COMPLETED.json',dict(completed=time.time(),rows=len(rows),unknown=summary['unknown'],all_primary_attempts_retained=True))
 print(json.dumps({k:summary[k]for k in ['planned','completed','semantic_pass','qualified_QA','interaction','unknown','failed']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
