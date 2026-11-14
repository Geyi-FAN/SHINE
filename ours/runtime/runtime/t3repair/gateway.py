"""Candidate gateway entry; R7 + explicit, audited T3 repair hooks."""
import os
import runpy
import sys
from pathlib import Path

B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
os.environ.setdefault('REPAIR_ROI_YOLO', '1')
source = runpy.run_path(str(B/'continuation/gateway_r7.py'), run_name='t3_source')['source']
anchor = ' install_dispatch_index(SingleOwnerBridge)'
assert source.count(anchor) == 1
source = source.replace(anchor, anchor + '\n from t3repair.integration import install as install_t3_repairs\n install_t3_repairs(SingleOwnerBridge)')
if __name__ == '__main__':
    exec(compile(source, str(B/'t3repair/generated_gateway.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'t3repair/gateway.py')))
