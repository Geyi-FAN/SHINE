"""Explicit new candidate; does not replace the frozen C3r service entry."""
import os
import runpy
from pathlib import Path
B = Path(__file__).resolve().parents[1]
os.environ['C3R_PROFILE'] = 'recovery'
source = runpy.run_path(str(B/'c3r/service.py'), run_name='prefetch_service_parent')['source']
anchor = "B/'c3r/gateway.py'"
assert source.count(anchor) == 1
source = source.replace(anchor, "B/'native_prefetch/gateway.py'")
anchor = "state['execution_service_revision']='R7-T3.2+C3r'"
assert source.count(anchor) == 1
source = source.replace(anchor,
    "state['execution_service_revision']='R7-T3.2+C3r+NativePrefetch-v1'")
if __name__ == '__main__':
    exec(compile(source, str(B/'native_prefetch/generated_service.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'repair6/service.py')))
