"""Same candidate core with the parent's separately disclosed T3 evaluator."""
import runpy
import sys
from pathlib import Path
B = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(B))
from c3r.profile import configure
PROFILE = configure()
source = runpy.run_path(str(B/'selected_eval/gateway.py'), run_name='c3r_eval_parent')['source']
anchor = ' install_lifecycle(SingleOwnerBridge)'
assert source.count(anchor) == 1
source = source.replace(anchor, anchor + '\n from c3r.integration import install as install_c3r\n install_c3r(SingleOwnerBridge)')
anchor = ' install_release(SingleOwnerBridge)'
assert source.count(anchor) == 1
source = source.replace(anchor, ' # C3r owns the stalled-return review; no duplicate G22 insertion')
source = source.replace("result['note']=", "result['execution_kernel']='C3r';result['c3r_profile']=__import__('os').environ['C3R_PROFILE'];result['note']=")
if __name__ == '__main__':
    exec(compile(source, str(B/'c3r/generated_eval_gateway.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'c3r/eval_gateway.py')))
