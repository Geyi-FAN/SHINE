"""Independent authored-task scoring; passive pause samples never count as physics."""
import os,argparse,collections,csv,hashlib,importlib.util,json,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];OUT=Path(os.environ.get('AUDIO_REPAIR_OUT','/mnt/disk_4/geyi/voice_audio_unified_repair_20261102'));DATA=OUT/'dataset';REF=B/'repair/reference'
sys.path.insert(0,str(REF))
import score_preflight
score_preflight.DOC=DATA
# score_preflight appends a legacy package path; bind the frozen authority copy.
sys.path.insert(0,str(REF))
import score_dev96
from aggregate import summarize
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--partial',action='store_true');ap.add_argument('--final',action='store_true');ap.add_argument('--label',default='formal24_r1');args=ap.parse_args();cases=json.loads((DATA/'selected.private.json').read_text());planned=len(cases);protocol=json.loads((DATA/'PROTOCOL.json').read_text());verdicts=[];report=OUT/args.label/'reports';report.mkdir(exist_ok=True,parents=True)
 for case in cases:
  directory=OUT/args.label/'cases'/case['case_id']
  if not(directory/'result.json').exists():continue
  v=score_dev96.evaluate(directory,case,protocol);r=json.loads((directory/'result.json').read_text());ticks=score_preflight.lines(directory/'physical.jsonl');checks=v.get('checks',[])
  if r.get('errors'):checks.append(dict(name='runner_completed_without_transport_or_setup_error',status='fail',evidence=r['errors']));v['interaction']='fail'
  if case['category']=='T2':
   passed=r.get('true_pause',{}).get('passed',False);checks.append(dict(name='pause_zero_physics_time_and_identical_state',status='pass'if passed else'fail',evidence=r.get('true_pause')))
   v['interaction']=score_preflight.conjunction([c['status']for c in checks])
  pauses=[t for t in ticks if t['mode']=='paused'];bad=[t for t in pauses if t['physics_tick']];v['pause_audit']=dict(paused_wall_samples=len(pauses),paused_physics_ticks=len(bad),passed=not bad)
  if bad:checks.append(dict(name='explicit_pause_no_env_step',status='fail'));v['interaction']='fail'
  voice=[e for f in(directory/'voice/sessions').glob('*.jsonl')for e in score_preflight.lines(f)];v['transcripts']=[dict(time=e.get('ts',0)/1000,**e.get('payload',{}))for e in voice if e.get('type')=='transcript.user'];v['audible_replies']=[dict(text=e['payload'].get('text'),time=p['time'],output_id=p['outputId'],evidence=e.get('audibility_evidence'))for e,p in score_dev96.audible_records(voice,r.get('messages',[]))]
  v['actual_turns']=[{k:t.get(k)for k in('turn_id','text','prelude','audio_started_wall','audio_ended_wall','input_file','input_sha256')}for t in r.get('turns',[])];v['physical_samples']=sum(t['physics_tick']for t in ticks);v['termination']=r.get('termination');v['backend_final_mode']=r.get('final',{}).get('state');v['video']=str(directory/'gateway_environment.mp4');v['evidence_directory']=str(directory);v['failures']=[c['name']for c in checks+v.get('physical_checks',[])if c['status']!='pass'];v['checks']=checks
  (directory/'verdict.json').write_text(json.dumps(v,ensure_ascii=False,indent=2));verdicts.append(v)
 flat=[dict(case_id=c['case_id'],category=c['category'],physical_eligible=c['private_contract']['physical_eligible'])for c in cases];summary=summarize(flat,verdicts);summary.update(valid_for_audio_benchmark=bool(verdicts)and all((Path(v['evidence_directory'])/'AUDIO_QUALITY.json').exists() and json.loads((Path(v['evidence_directory'])/'AUDIO_QUALITY.json').read_text()).get('passed')for v in verdicts)and len(verdicts)==planned,code_base='repair-R3-from-6e52599',input='human-reviewed TTS / PCM CLI / cloud speech / local F28d execution agents',physical='v2.5 frozen candidate; actual-physics hold only',first_attempts=True,status='partial'if args.partial else'complete',denominator_note='24 planned cases for all three metrics; precondition and cloud failures retained; unknown not pass',controlled_source=True,independent_hold=True)
 (report/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(report/'verdicts.json').write_text(json.dumps(verdicts,ensure_ascii=False,indent=2))
 with(report/'cases.csv').open('w',newline='')as f:
  writer=csv.DictWriter(f,fieldnames=['case_id','category','interaction','target','instruction','termination','backend_final_mode','failures','video','evidence_directory']);writer.writeheader()
  for v in verdicts:writer.writerow({k:';'.join(v[k])if k=='failures'else v.get(k)for k in writer.fieldnames})
 rows=['# 冻结24例真实音频开发评测','',f"已完成 {len(verdicts)}/{planned}。合成语音实时输入，不是真人测试；受控持物窗口，不是自然打断正式成绩。",'', '|类别|例数|交互通过|目标达成|完整指令|','|---|---:|---:|---:|---:|']
 for k,g in summary['groups'].items():
  n=sum(c['category']==k for c in cases);rows.append('|'+k+'|'+str(n)+'|'+ '|'.join(f"{g[m]['passed']}/{g[m]['denominator']}"for m in('interaction','target','instruction'))+'|')
 rows+=['|合计|'+str(planned)+'|'+'|'.join(f"{summary['micro'][m]['passed']}/{summary['micro'][m]['denominator']}（{100*summary['micro'][m]['rate']:.2f}%）"for m in('interaction','target','instruction'))+'|','','交互、目标、完整指令分别判定；交互失败不自动否定独立物理证据。所有前置失败保留分母。代码和模型在正式运行中不修改，首次结果不重跑。','','实际控制器收尾与独立物理成功分开记录；未知语义不计通过。语音延迟使用音频末端代理，未标注关键词精确时间。','','## 逐例证据','']
 for v in verdicts:
  d=Path(v['evidence_directory']);r=json.loads((d/'result.json').read_text());rows +=[f"### {v['case_id']}：Interaction {v['interaction']} / Target {v['target']} / Instruction {v['instruction']}",'',f"失败检查：{', '.join(v['failures'])or'无'}。终止：{v.get('termination')}。",'',*[f"- {'前置'if t.get('prelude')else'用户'}：{t.get('text')}"for t in r.get('turns',[])],*[f"- 实际语音回答：{p['text']}"for p in v['audible_replies']],f"- [视频]({d/'gateway_environment.mp4'}) · [逐项评分]({d/'verdict.json'}) · [输入/输出音频]({d/'client'}) · [工具回执与执行事件]({d/'gateway.jsonl'}) · [Agent完整请求]({d/'local_requests'}) · [语音会话]({d/'voice/sessions'})",'']
 (report/'RESULTS.md').write_text('\n'.join(rows)+'\n');print(json.dumps(dict(received=len(verdicts),planned=planned,metrics=summary['micro']),ensure_ascii=False))
 if not args.partial:assert len(verdicts)==planned,'All first attempts required'
if __name__=='__main__':main()
