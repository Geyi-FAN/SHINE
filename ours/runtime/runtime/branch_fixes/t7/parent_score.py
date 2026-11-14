"""Reuse old T7 behavioral/physical checks; adapt only evidence transport."""
import argparse,collections,csv,json,re,sys,sqlite3
from pathlib import Path
B=Path(__file__).resolve().parent;REF=B/'reference';OUT=Path(__import__('os').environ['T7_REPAIR_OUT']);DATA=OUT/'dataset'
sys.path.insert(0,str(REF))
import score_t7,score_preflight
old_lines=score_t7.lines
# New private recorder contains passive wall-clock samples. They must not
# manufacture 5-tick stability or count as policy steps; old traces had ticks only.
def physical_lines(path):
 rows=old_lines(path)
 return [r for r in rows if r.get('physics_tick',True)]if str(path).endswith('control_ticks.jsonl')else rows
score_t7.lines=physical_lines
def execution_events(directory,result):
 """Database time/identity are authoritative; inner event time is provenance."""
 path=directory/'gateway/episodes.sqlite'
 if not path.exists()or not result.get('episode_id'):return []
 with sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)as db:
  rows=db.execute('SELECT rowid,id,time,kind,version,payload FROM events WHERE episode=? AND time<=? ORDER BY rowid',(result['episode_id'],result['finished']['time'])).fetchall()
 answer=[]
 for row in rows:
  payload=json.loads(row[5]);reserved={k:payload[k]for k in('time','kind','version','sequence','event_id')if k in payload}
  answer.append(dict(payload,sequence=row[0],event_id=row[1],time=row[2],kind=row[3],version=row[4],payload_reserved_fields=reserved))
 return answer
score_t7.execution_events=execution_events
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--scope',default='formal90_v3');ap.add_argument('--partial',action='store_true');args=ap.parse_args();root=OUT/args.scope;report=root/'reports';report.mkdir(exist_ok=True)
 cases=json.loads((DATA/'selected.private.json').read_text());protocol=json.loads((DATA/'PROTOCOL.json').read_text());verdicts=[]
 if args.scope.startswith('precheck'):cases=[c for c in cases if(root/'cases'/c['case_id']).exists()]
 for c in cases:
  d=root/'cases'/c['case_id']
  if not(d/'result.json').exists():continue
  v=score_t7.evaluate(d,c,protocol);r=json.loads((d/'result.json').read_text());v['joint']='pass'if v['interaction']==v['instruction']=='pass'else'fail'
  voice=[e for p in(d/'voice/sessions').glob('*.jsonl')for e in old_lines(p)];v['transcripts']=[dict(time=e['ts']/1000,**e.get('payload',{}))for e in voice if e.get('type')=='transcript.user'];v['audio_evidence']=[dict(time=e['ts']/1000,**e.get('payload',{}))for e in voice if e.get('type')=='realtime.protocol'and e.get('payload',{}).get('type')in('robot.audio_grounding','robot.audio_relisten')];v['video']=str(d/'gateway_environment.mp4');v['evidence_directory']=str(d);v['run_status']=r.get('run_status');v['actual_turns']=len(r.get('turns',[]));v['expected_turns']=len(c['turns']);v['backend_final_mode']=r.get('final',{}).get('state')
  (d/'verdict.json').write_text(json.dumps(v,ensure_ascii=False,indent=2));verdicts.append(v)
 metrics={m:dict(passed=sum(v[m]=='pass'for v in verdicts),denominator=len(cases),rate=sum(v[m]=='pass'for v in verdicts)/len(cases))for m in('interaction','target','instruction','joint')}
 groups={g:{m:dict(passed=sum(v.get('branch')==g and v[m]=='pass'for v in verdicts),denominator=sum(c['branch']==g for c in cases))for m in metrics}for g in('N','C','R')}
 failures=collections.Counter(f for v in verdicts for f in v.get('failures',[]));summary=dict(status='partial'if args.partial else'complete',scope=args.scope,received=len(verdicts),planned=len(cases),metrics=metrics,branches=groups,failures=dict(failures),input='same synthetic speech/direct Realtime framework WS/no web server',planner='F28d Qwen3.8-27B-FP8',actor='SmolVLA E3 v4 raw30000',stage_completion='F28d observation/S1/visual verification',old_comparison='same IDs/audio/scenes/budget; changed kernel/stage judge/client; not a repair-only ablation')
 (report/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(report/'verdicts.json').write_text(json.dumps(verdicts,ensure_ascii=False,indent=2))
 with(report/'cases.csv').open('w',newline='')as f:
  writer=csv.DictWriter(f,fieldnames=['case_id','branch','interaction','target','instruction','joint','actual_turns','expected_turns','handoff_tested','backend_final_mode','failures','video']);writer.writeheader()
  for v in verdicts:writer.writerow({k:';'.join(v.get(k,[]))if k=='failures'else v.get(k)for k in writer.fieldnames})
 rows=['# T7直连框架修复候选回归','',f'已完成 {len(verdicts)}/{len(cases)}。所有失败保留分母；不是独立泛化成绩。','', '|指标|成功/总数|成功率|','|---|---:|---:|']
 for m,x in metrics.items():rows.append(f"|{m}|{x['passed']}/{x['denominator']}|{x['rate']:.2%}|")
 rows+=['','同旧90例的ID、音频字节、初态和时限；规划内核、阶段判断和客户端已改变，不能把全部变化归因于waiting补丁。没有人工麦克风或物理扬声器测试。','','## 逐例输入、输出与证据','']
 for v in verdicts:
  d=Path(v['evidence_directory']);c=next(c for c in cases if c['case_id']==v['case_id']);rows +=[f"### {v['case_id']}：{v['interaction']} / {v['target']} / {v['instruction']}",'',f"失败项：{', '.join(v.get('failures',[])) or '无'}。实际播放 {v['actual_turns']}/{v['expected_turns']} 轮。",'',*[f"- 原话：{t['text']}"for t in c['turns']],*[f"- 实时转写：{t.get('text')}"for t in v['transcripts']],f"- [视频]({v['video']}) · [音频]({d/'client'}) · [逐项评分]({d/'verdict.json'}) · [工具/阶段日志]({d/'gateway.jsonl'}) · [Agent请求]({d/'local_requests'})",'']
 (report/'RESULTS.md').write_text('\n'.join(rows)+'\n');print(json.dumps(dict(scope=args.scope,received=len(verdicts),metrics=metrics)),flush=True)
 if not args.partial:assert len(verdicts)==len(cases)
if __name__=='__main__':main()
