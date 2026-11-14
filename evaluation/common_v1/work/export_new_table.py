"""Build counts from fixed registration, not from whichever scores succeeded."""
from pathlib import Path
import csv,json,collections
Q=Path(__file__).resolve().parents[1];B=Q.parents[1];N=Q.parent/'ours_full930_readiness_20261114'
def read(p):return json.loads(Path(p).read_text())
def export():
 run=Q/'runs/formal1770_v1';rows=read(run/'PROGRESS.json')['rows'];assert len(rows)==1770
 reg=read(Q/'plans/REGISTERED1770.private.json');records={x['trial_uid']:x for x in rows};assert len(records)==1770
 table=[];details=[]
 for method in ['B0','B1']:
  for branch in ['T1','T2','T3','T4','T5','T7','T8']:
   items=[x for x in reg if x['method']==method and x['branch']==branch]
   for metric in ['interaction','target','instruction']:
    applicable=[x for x in items if x.get('metric_applicability',{}).get('interaction45'if branch=='T7'and metric=='interaction'else metric,False)]
    if not applicable:continue
    vals=[records[x['trial_uid']].get('score',{}).get(metric,'unknown')for x in applicable]
    n=len(applicable);passed=sum(x is True or x=='pass'for x in vals);unknown=sum(x in ['unknown',None]for x in vals)
    table.append(dict(method=method,task=branch,metric=metric,success=passed,total=n,unknown=unknown,rate_percent=100*passed/n))
 for method in ['B1']:
  xs=[x for x in reg if x['method']==method and x['branch']=='T8'and x.get('metric_applicability',{}).get('dual_channel',False)]
  assert len(xs)==24
  vals=[records[x['trial_uid']].get('score',{}).get('dual_channel','unknown')for x in xs];good=sum(x is True or x=='pass'for x in vals)
  table.append(dict(method=method,task='T8',metric='speech_action_separation',success=good,total=24,unknown=sum(x in ['unknown',None]for x in vals),rate_percent=100*good/24))
  j=read(Q/'finalization/formal1770_v1/judge90_first/SUMMARY.json');assert j['planned']==90 and j['completed']==90
  table.append(dict(method=method,task='T6',metric='QA_success',success=j['confirmed_pass'],total=90,unknown=j['unknown'],rate_percent=100*j['confirmed_pass']/90))
 # Same scorer for all existing Ours non-QA first attempts.
 candidate=read(Q/'plans/FROZEN.json')['version']
 pools=list((Q/'reports').glob('ours_common_full_*/COMPLETED.json'))
 assert len(pools)==1,'Exactly one complete original-Ours regrade is required'
 completed=read(pools[0]);assert completed['completed']==840 and completed['errors']==0
 ours=read(pools[0].parent/'PROGRESS.json')['rows'];assert len(ours)==840
 original_registry=read(N/'plans/REGISTERED930.json')['rows'];registered={x['trial_uid']:x for x in original_registry}
 for branch in ['T1','T2','T3','T4','T5','T7','T8']:
  for metric in ['interaction','target','instruction']:
   xs=[x for x in ours if x['branch']==branch and registered[x['trial_uid']]['metric_applicability'].get('interaction45'if branch=='T7'and metric=='interaction'else metric,False)]
   if not xs:continue
   vals=[x['score'].get(metric,'unknown')for x in xs];good=sum(x is True or x=='pass'for x in vals)
   table.append(dict(method='Ours',task=branch,metric=metric,success=good,total=len(xs),unknown=sum(x in ['unknown',None]for x in vals),rate_percent=100*good/len(xs)))
 xs=[x for x in ours if x['branch']=='T8'and registered[x['trial_uid']]['metric_applicability'].get('dual_channel',False)];assert len(xs)==24
 good=sum(x['score'].get('dual_channel')in [True,'pass']for x in xs)
 table.append(dict(method='Ours',task='T8',metric='speech_action_separation',success=good,total=24,unknown=sum(x['score'].get('dual_channel')in [None,'unknown']for x in xs),rate_percent=100*good/24))
 oldqa=read(N/'finalization_formal930_v1/judge90_live/SUMMARY.json');assert oldqa['planned']==oldqa['completed']==90
 table.append(dict(method='Ours',task='T6',metric='QA_success',success=oldqa['confirmed_pass'],total=90,unknown=oldqa['unknown'],rate_percent=100*oldqa['confirmed_pass']/90))
 out=Q/'reports/final1770';out.mkdir(exist_ok=False)
 with(out/'METRICS.csv').open('w')as f:
  w=csv.DictWriter(f,fieldnames=['method','task','metric','success','total','unknown','rate_percent']);w.writeheader();w.writerows(table)
 # QA90 and actual scorer results stay linked, not hand-entered.
 (out/'METRICS.json').write_text(json.dumps(table,indent=2)+'\n')
 (out/'README.md').write_text('# 新共同评分基线结果\n\n由固定1770注册项生成。纯ASR T6不支持且未运行；新B1保留旧Oracle点与所选阶段完成辅助。\nUnknown/缺失留在主分母，不按已评分数缩小分母。原Ours及旧基线未覆盖。\n\nOurs共同评分应从 reports/ours_common_full_* 全部840记录生成，再继承原90条固定QA；不能把旧数值不核查地复制进“共同评分”列。\n')
 paired=[];ours_by={x['trial_uid']:x for x in ours}
 for x in rows:
  if x['branch']=='T6':continue
  o=ours_by[x['paired_trial_uid']];assert o['branch']==x['branch']
  for metric in ['interaction','target','instruction']:
   a=x.get('score',{}).get(metric);b=o['score'].get(metric)
   if a not in ['pass','fail','unknown']and b not in ['pass','fail','unknown']:continue
   paired.append(dict(method=x['method'],paired_trial_uid=x['paired_trial_uid'],task=x['branch'],metric=metric,baseline=a,ours=b))
 with(out/'PAIRED_CASES.csv').open('w')as f:
  w=csv.DictWriter(f,fieldnames=['method','paired_trial_uid','task','metric','baseline','ours']);w.writeheader();w.writerows(paired)
 txt=['# 三方法共同评分最终表','', '原始首试保留。B1仍有已披露的Oracle辅助；不能把辅助信息差异写成不存在。','', '|任务|指标|ASR＋π0.5|ASR＋Agent（Oracle辅助）|Ours|','|---|---|---:|---:|---:|']
 keys=list(dict.fromkeys((r['task'],r['metric'])for r in table))
 for task,metric in keys:
  vals=[]
  for m in ['B0','B1','Ours']:
   r=next((r for r in table if r['task']==task and r['metric']==metric and r['method']==m),None)
   vals.append((str(r['success'])+'/'+str(r['total'])+' ('+format(r['rate_percent'],'.2f')+'%)')if r else('N/S'if task=='T6'and m=='B0'else'N/E'))
  txt.append('|'+task+'|'+metric+'|'+'|'.join(vals)+'|')
 txt+=['', '所有Unknown保留固定分母；本数据用于开发，未完成人工双评校准；真实音频、回执和物理证据详见逐例目录。原Ours旧表没有覆盖，本表Ours来自同评分器复核。']
 (out/'TABLE_COMMON.md').write_text('\n'.join(txt)+'\n')
 print(out)
if __name__=='__main__':export()
