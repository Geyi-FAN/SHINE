"""Evidence-only tables and same-case comparisons; never changes verdicts."""
import csv,json,statistics
from collections import Counter
from pathlib import Path
from continuation.final_report import ROOT,score_paths,load

NEW=ROOT/'R8/expanded96/formal96_r8_20261102'
OLD=ROOT/'R5b/formal24_r5b_20261102'
FIELDS=('interaction','target','instruction')

def dumpcsv(p,rows,keys):
 with p.open('w',newline='')as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)

def rate(vs,k,eligible):
 selected=[v for v in vs if k=='interaction'or v['case_id']in eligible]
 return dict(passed=sum(v.get(k)=='pass'for v in selected),received=len(selected))

def main():
 out=ROOT/'reports';out.mkdir(exist_ok=True)
 cases=load(NEW.parent/'dataset/selected.private.json')or load(ROOT/'expanded96/dataset/selected.private.json')or[]
 vs=load(score_paths(NEW)/'verdicts.json')or[]
 oldvs={v['case_id']:v for v in load(score_paths(OLD)/'verdicts.json')or[]}
 planned={c['case_id']:c for c in cases};eligible={c['case_id']for c in cases if c['private_contract']['physical_eligible']}
 quality=Counter();opportunities=0;rows=[];failures=Counter();latencies={};claims=Counter();inputs=0
 finish_mismatches=[]
 for v in vs:
  cid=v['case_id'];d=NEW/'cases'/cid;r=load(d/'result.json')or{};q=load(d/'AUDIO_QUALITY.json')or{}
  turns=[t for t in r.get('turns',[])if not t.get('prelude')]
  opportunities+=bool(r.get('precondition_validated')and turns)
  inputs+=len(q.get('clips',[]));quality['passed'if q.get('passed')else'failed_or_missing']+=1
  failed=[]
  for c in v.get('checks',[]):
   if c['status']!='pass':failures[c['name']]+=1;failed.append(c['name'])
   e=c.get('evidence')or{}
   if isinstance(e,dict)and isinstance(e.get('latency_s'),(int,float)):
    latencies.setdefault(c['name'].split('_T')[0],[]).append(e['latency_s'])
  for k,n in v.get('auxiliary_counts',{}).items():claims[k]+=n
  if v.get('instruction')=='pass'and v.get('backend_final_mode')not in ['completed','success']:
   finish_mismatches.append(dict(case_id=cid,backend_mode=v.get('backend_final_mode'),termination=r.get('termination')))
  rows.append(dict(case_id=cid,category=v['category'],physical_eligible=cid in eligible,
   audio_quality=q.get('passed'),precondition=r.get('precondition_validated'),scored_audio_turns=len(turns),
   **{k:v.get(k)for k in FIELDS},interaction_failed_checks='; '.join(failed),
   physical_failed_checks='; '.join(c['name']for c in v.get('physical_checks',[])if c['status']!='pass'),
   authored=' / '.join(t['text']for t in turns),
   asr=' / '.join(x['text']for x in v.get('transcripts',[])),
   actually_played=' / '.join(x['text']for x in v.get('audible_replies',[])),
   authorized_control_steps=(r.get('final',{}).get('execution_budget')or{}).get('authorized_control_steps',r.get('final',{}).get('policy_action_steps')),
   authorized_control_limit=(r.get('final',{}).get('execution_budget')or{}).get('control_limit'),
   termination=r.get('termination'),backend_final_mode=v.get('backend_final_mode'),
   environment_video=v.get('video'),case_result=str(d/'result.json'),verdict=str(score_paths(NEW)/'cases'/(cid+'.json'))))
 if rows:dumpcsv(out/'ALL_96_CASES.csv',rows,list(rows[0]))
 paired=[];paircounts={k:Counter()for k in FIELDS}
 for v in vs:
  cid=v['case_id']
  if cid not in oldvs:continue
  old=oldvs[cid];a=load(OLD/'cases'/cid/'result.json')or{};b=load(NEW/'cases'/cid/'result.json')or{}
  aa=[(t['turn_id'],t.get('input_sha256'))for t in a.get('turns',[])];bb=[(t['turn_id'],t.get('input_sha256'))for t in b.get('turns',[])]
  row=dict(case_id=cid,identical_actual_audio_sequence=aa==bb,old_actual_turns=len(aa),new_actual_turns=len(bb))
  for k in FIELDS:
   oa=old.get(k);nb=v.get(k);row['old_'+k]=oa;row['new_'+k]=nb
   if oa=='pass'and nb=='pass':label='both_pass'
   elif oa=='pass':label='lost_pass'
   elif nb=='pass':label='gained_pass'
   else:label='both_not_pass'
   paircounts[k][label]+=1
  paired.append(row)
 if paired:dumpcsv(out/'SAME24_PAIRED.csv',paired,list(paired[0]))
 groups={}
 for group in sorted({c['category']for c in cases}):
  cv=[v for v in vs if v['category']==group];pc=[c for c in cases if c['category']==group]
  groups[group]={k:dict(**rate(cv,k,eligible),denominator=len(pc)if k=='interaction'else sum(c['private_contract']['physical_eligible']for c in pc))for k in FIELDS}
 # Any conditional opportunity score is labeled secondary; all planned cases remain primary.
 secondary=[v for v in vs if planned.get(v['case_id'],{}).get('script_id')!='T4_04']
 same=[v for v in vs if v['case_id']in oldvs]
 data=dict(status='complete'if(NEW/'COMPLETED.json').exists()else'partial',planned=len(cases),received=len(vs),
  physical_denominator=len(eligible),scored_audio_opportunities=opportunities,input_quality=dict(quality),clips=inputs,
  groups=groups,failed_interaction_checks=dict(failures),auxiliary_counts=dict(claims),physical_pass_backend_finish_disagreements=finish_mismatches,
  latencies={k:dict(count=len(x),median_s=statistics.median(x),maximum_s=max(x))for k,x in latencies.items()},
  same24=dict(received=len(paired),planned=24,paired_counts={k:dict(v)for k,v in paircounts.items()},
   audio_sequence_identical=sum(r['identical_actual_audio_sequence']for r in paired),metrics={k:dict(**rate(same,k,set(oldvs)),denominator=24)for k in FIELDS}),
  secondary_excluding_three_out_of_training_goal_cases=dict(planned=93,physical_denominator=78,metrics={k:dict(**rate(secondary,k,eligible),denominator=93 if k=='interaction'else 78)for k in FIELDS},note='secondary only; does not replace96/81 primary'),
  note='No failure reclassification or threshold change. Same24 comparison uses same independent scorer, but shared load, hardware and asynchronous states differ.')
 (out/'ANALYSIS_96.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 text=['# 96例分组、失败证据与同24例配对','',f'状态：{data["status"]}；实际结束{len(vs)}/96。主交互分母96，物理分母81；尚未结束的案例不算成功。','',
  '|类别|Interaction|Target|Instruction|','|---|---|---|---|']
 for group,vals in groups.items():text.append('|'+group+'|'+'|'.join(f"{vals[k]['passed']}/{vals[k]['denominator']}"for k in FIELDS)+'|')
 text+=['',f'已结束案例中，{opportunities}例满足前置且实际发送了评分音频；{quality["passed"]}例音频收发质量通过，共{inputs}段。前置失败仍保留在主分母；不能用条件成功率替代主结果。','',
  f'[全部逐例证据CSV]({out/"ALL_96_CASES.csv"}) · [同24例配对CSV]({out/"SAME24_PAIRED.csv"}) · [机器可读统计]({out/"ANALYSIS_96.json"})','',
  '## 同24例配对','',f'已配对{len(paired)}/24，实际完整输入音频序列哈希一致{data["same24"]["audio_sequence_identical"]}例。不一致需看是否因前置失败/真实澄清分支不同，不能默认同一执行状态。','',
  '|指标|两者均通过|新增通过|丢失通过|均未通过|','|---|---|---|---|---|']
 for k,c in paircounts.items():text.append('|'+k+'|'+'|'.join(str(c[x])for x in ['both_pass','gained_pass','lost_pass','both_not_pass'])+'|')
 text+=['','## 交互检查失败项（同一例可重复）','',*['- '+k+'：'+str(n)+'例'for k,n in failures.most_common()],
  '', '## 边界','', '这是用于修复的开发集，合成语音、固定音色、三个批准初始状态。动作模型/归一化/四角色提示词相同；语音/传输/任务生命周期经过修复，GPU与负载、实际切换时刻并非逐步相同。不是独立真人或噪声泛化成绩。','']
 (out/'ANALYSIS_96.md').write_text('\n'.join(text))
 print(json.dumps(dict(received=len(vs),same24=len(paired),opportunities=opportunities,quality=dict(quality))))

if __name__=='__main__':main()
