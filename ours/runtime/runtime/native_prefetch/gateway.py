"""C3r recovery plus Native prefetch; preserve the existing acceptance owner."""
import runpy
import sys
from pathlib import Path
B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
source = runpy.run_path(str(B/'c3r/gateway.py'), run_name='prefetch_parent')['source']
anchor = ' class Native(NativeExecution):'
assert source.count(anchor) == 1
source = source.replace(anchor,
    ' from native_prefetch.scheduler import NativePrefetchMixin\n'
    ' class Native(NativePrefetchMixin,NativeExecution):')
anchor = "result['execution_kernel']='C3r';"
assert source.count(anchor) == 1
source = source.replace(anchor, anchor + "result['native_scheduler']='prefetch-frame-aligned-v1';")
if __name__ == '__main__':
    exec(compile(source, str(B/'native_prefetch/generated_gateway.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'c3r/gateway.py')))
