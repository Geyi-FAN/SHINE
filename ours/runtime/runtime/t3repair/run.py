"""Small real-PCM regression on isolated ports, using the R8 audio client."""
import runpy
import sys
from pathlib import Path
B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
source = runpy.run_path(str(B/'repair8/run.py'), run_name='t3_regression_source')['source']
old = "B/'continuation/service_r7.py'"
assert source.count(old) == 1
source = source.replace(old, "B/'t3repair/service.py'")
old = '(19281+slot*100,19287+slot*100,19289+slot*100)'
assert source.count(old) == 1
source = source.replace(old, '(23081+slot*100,23087+slot*100,23089+slot*100)')
source = source.replace('emit(\'round_completed\',cases=24)', "emit('round_completed',cases=len(cases))")
if __name__ == '__main__':
    exec(compile(source, str(B/'t3repair/generated_run.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'repair6/run.py')))
