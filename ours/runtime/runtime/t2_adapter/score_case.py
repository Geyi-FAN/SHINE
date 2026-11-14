"""Reuse the previous strict T2 judge and actual-R8 audio binding unchanged."""
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
A = Path(__file__).resolve().parent
sys.path[:0] = [str(A/'analysis'), str(A/'tools')]
from audited_score import evaluate

if __name__ == '__main__':
    directory = Path(sys.argv[1])
    spec = next(s for s in json.loads((A/'dataset/selected.private.json').read_text()) if s['case_id'] == sys.argv[2])
    verdict = evaluate(directory, spec)
    print(json.dumps(dict(case_id=spec['case_id'], **{k:verdict[k] for k in ['interaction', 'target', 'instruction', 'failures']}), ensure_ascii=False))
