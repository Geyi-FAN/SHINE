"""Unchanged per-case T7 judges, predeclared denominator three; pending retained."""
import argparse, importlib.util, json, time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--root',required=True,type=Path);root=p.parse_args().root
adapter=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('t7_parent_score',adapter/'score.py');score=importlib.util.module_from_spec(spec);spec.loader.exec_module(score)
cases=score.read(root/'dataset/selected.private.json');assert len(cases)==10
judge,derive=score.load_judge(root);results=[]
for case in cases:
 folder=root/'cases'/case['case_id']
 if not(folder/'RUN_FINISHED.json').exists():continue
 raw,verdict=score.evaluate_one(judge,derive,folder,case,score.read(root/'dataset/PROTOCOL.json'))
 score.dump(folder/'verdict_raw.json',raw);score.dump(folder/'verdict.json',verdict);results.append(verdict)
report=root/'reports';report.mkdir(exist_ok=True)
summary=dict(status='complete'if len(results)==len(cases) else'running',planned=len(cases),received=len(results),
 metrics=score.stats(results,len(cases)),raw_metrics=score.stats(results,len(cases),True),per_case_judges_and_thresholds_unchanged=True,
 original_full_ten_not_replaced=True,time=time.time())
score.dump(report/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False))
