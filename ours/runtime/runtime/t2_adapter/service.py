"""Reuse the shared persistent service; T2 adds evaluator-only recording."""
import os
import runpy
from pathlib import Path

B = Path(__file__).resolve().parents[1]
os.environ['C3R_PROFILE'] = 'recovery'
source = runpy.run_path(str(B/'c3r/service.py'), run_name='t2_service_parent')['source']
old = "B/'c3r/gateway.py'"
assert source.count(old) == 1
source = source.replace(old, "B/'t2_adapter/gateway.py'")
old = "state['execution_service_revision']='R7-T3.2+C3r'"
assert source.count(old) == 1
source = source.replace(old, "state['execution_service_revision']='R7-T3.2+C3r+NativePrefetch-v1';state['t2_evaluation_adapter']='MX10-original-contract-v1'")
# Allow post-cutoff archive/encoder shutdown; this does not extend scoring time.
assert source.count('p.wait(12)') == 1
source = source.replace('p.wait(12)', 'p.wait(60)')
if __name__ == '__main__':
    exec(compile(source, str(B/'t2_adapter/generated_service.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'repair6/service.py')))
