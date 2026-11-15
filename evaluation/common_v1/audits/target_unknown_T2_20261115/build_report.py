"""Publish an explicitly separate measurement candidate; preserve all old tables."""
import collections,csv,hashlib,json
from pathlib import Path
Q=Path('/mnt/disk_4/geyi/audio_switch_benchmark/deployments/common_scoring_oracle_baselines_20261114');A=Q/'audits/target_unknown_T2_20261115'
read=lambda p:json.loads(p.read_text())
def csvout(name,rows):
 with (A/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
u=read(A/'unknown47.json');cats=read(A/'unknown47_categories.json');by={x['trial_uid']:x for x in cats['rows']};deep={x['trial_uid']:x for x in read(A/'unknown47_deep.json')}
unknown=[]
for x in u:
 z=deep[x['trial_uid']];assert x['audio_quality'] and not x['engine_error'] and not x['ids'] and not z['active_tick_count'] and not z['new_instruction_events']
 unknown.append(dict(trial_uid=x['trial_uid'],method='B1',branch=x['branch'],original='unknown',candidate='fail',category=by[x['trial_uid']]['category'],active_ticks=0,authorized_actions=0,directory=x['directory']))
for x in read(A/'ours_unknown4_audit.json'):
 assert x['attribution_valid'] and not x['ids'] and not x['active_ticks'] and not x['new_instructions'] and x['error']
 unknown.append(dict(trial_uid=x['trial_uid'],method='Ours',branch=x['trial_uid'].split(':')[0],original='unknown',candidate='fail',category='new_task_acceptance_timeout',active_ticks=0,authorized_actions=0,directory=x['directory']))
csvout('TARGET_LABEL_AUDIT_51.csv',unknown)
t2=read(A/'T2_EVIDENCE_CANDIDATE.json')+read(A/'T2_OURS_EVIDENCE_CANDIDATE.json');assert len(t2)==360
csvout('T2_PAIRED_360.csv',[dict(trial_uid=x['trial_uid'],method=x['method'],original_interaction=x['old_interaction'],candidate_interaction=x['candidate_interaction'],target=x['old_target'],instruction=x['old_instruction'],changed_checks=';'.join(y['name'] for y in x['changed_checks']),raw_unchanged=x['raw_unchanged']) for x in t2])
exclusive=collections.Counter()
for x in [x for x in t2 if x['method']=='B1']:
 fail=[c for c in x['checks'] if c['status']=='fail']
 if not fail:c='pass'
 elif any(c['name'] in ['verified_task_specific_trigger','three_authored_audio_turns','formal_enrollment_recorded'] for c in fail):c='preparation_or_missing_turns'
 elif any(c['name']=='hard_physical_pause_within_5s' for c in fail):c='physical_pause_deadline'
 elif any(c['name']=='resume_same_task_once' for c in fail):c='resume_commit'
 elif any(c['name'] in ['actual_resume_action_within_45s','no_unrequested_pause_after_resume'] for c in fail):c='resume_action'
 else:c='speech_receipt'
 exclusive[c]+=1
metrics=read(Q/'reports/final1770/METRICS.json')
for x in metrics:
 if x['task']=='T2' and x['metric']=='interaction':
  xx=[y for y in t2 if y['method']==x['method']];x['success']=sum(y['candidate_interaction']=='pass' for y in xx);x['unknown']=0;x['rate_percent']=100*x['success']/x['total']
 if x['metric']=='target':x['unknown']-=sum(y['method']==x['method'] and y['branch']==x['task'] for y in unknown);assert x['unknown']>=0
(A/'CANDIDATE_METRICS.json').write_text(json.dumps(metrics,indent=2)+'\n');csvout('CANDIDATE_METRICS.csv',metrics)
text=['# 共同测量修订候选 v1.1（未覆盖原始1770成绩）','','只读复核，无机器人补测、无新模型调用。T2三方法360例统一执行证据适配；严格保留原始语义、任务绑定、时限、物理条件与分母。目标未知中51例重新标记为已知未执行失败，所有成功率分母和目标成功数不变。','','|任务|指标|ASR＋π0.5|ASR＋Agent（Oracle辅助）|Ours|','|---|---|---:|---:|---:|']
for task,metric in dict.fromkeys((x['task'],x['metric']) for x in metrics):
 vals=[]
 for method in ['B0','B1','Ours']:
  x=next((x for x in metrics if x['task']==task and x['metric']==metric and x['method']==method),None)
  vals.append(('%s/%s（%.2f%%）'%(x['success'],x['total'],x['rate_percent'])) if x else ('N/S' if task=='T6' and method=='B0' else 'N/E'))
 text.append('|'+task+'|'+metric+'|'+'|'.join(vals)+'|')
text+=['','Oracle表示基线仍有仿真真值定位与已选阶段完成辅助。N/S为不支持，N/E为未单独统计。T6仍保留原固定GLM判分，包括B1的1例未知。原18例基础设施异常及3例音频节奏异常均保留，没有重跑或删除。尚未完成人工双评校准。本表为测量修订候选，不是一次新的在线评测。']
(A/'TABLE_CANDIDATE.md').write_text('\n'.join(text)+'\n')
summary=dict(version='measurement-audit-candidate-v1.1-20261115',original_scores_overwritten=False,new_rollouts=0,new_model_calls=0,unknown47_categories=cats['counts'],ours_same_rule_known_nonexecution=4,t2_regrade_count=360,t2_by_method={m:dict(original=sum(x['old_interaction']=='pass' for x in t2 if x['method']==m),candidate=sum(x['candidate_interaction']=='pass' for x in t2 if x['method']==m),denominator=120) for m in ['B0','B1','Ours']},t2_b1_exclusive_failure_groups=dict(exclusive),tests=10)
(A/'FINAL_AUDIT.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary))
