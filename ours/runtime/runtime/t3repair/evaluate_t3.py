"""Run the independent T3 evaluator with explicitly versioned text fixes.

Example: python -m t3repair.evaluate_t3 --directory CASE --spec SPEC.json
         --rules physical_rules.json --out NEW_verdict.json
The original result and verdict files are strictly read-only.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--spec',type=Path,required=True)
    p.add_argument('--rules',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    if args.out.exists() or args.out.resolve().is_relative_to(args.directory.resolve()):
        raise ValueError('Write a NEW verdict outside the immutable original case directory')
    sys.path.insert(0,str(B/'repair6/reference'))
    import benchmark_metrics.events
    sys.path.insert(0,str(B/'t3repair/reference_t3'))
    import score_t3
    from t1_contract import instruction_goal
    from t3repair import scoring
    score_t3.goal_from_full=lambda text:scoring.goal_from_full(text,instruction_goal)
    score_t3.restore_radius=scoring.restore_radius
    score_t3.VERSION=scoring.VERSION
    result_file=args.directory/'result.json'
    original_hash=hashlib.sha256(result_file.read_bytes()).hexdigest()
    verdict=score_t3.evaluate(args.directory,json.loads(args.spec.read_text()),json.loads(args.rules.read_text()))
    assert hashlib.sha256(result_file.read_bytes()).hexdigest()==original_hash
    verdict['audit_scope']='new independent verdict, unchanged robot trajectory and numeric thresholds'
    verdict['original_result_sha256']=original_hash
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(verdict,ensure_ascii=False,indent=2))
    print(json.dumps({k:verdict.get(k)for k in ['case_id','interaction','target','instruction','failures','scoring_version']}))


if __name__=='__main__':main()
