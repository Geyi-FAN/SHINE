"""Original T5/C3r adapter plus the single reviewed F01 evidence fix."""
import runpy,sys
from pathlib import Path
A=Path(__file__).resolve().parent
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
sys.path.insert(0,str(A))
source=runpy.run_path('/mnt/disk_2/geyi/t5_c3r_30_20261103/runtime/gateway.py',run_name='f01_parent_gateway')['source']
anchor=' core,runner,authority=configure(a.out,a.gpu)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from f10_patch import install as install_f01\n install_f01(core)')
anchor="result['execution_kernel']='C3r';"
assert source.count(anchor)==1
source=source.replace(anchor,anchor+"result['f01_clarification_fix']=core.F01_CLARIFICATION_FIX;result['f02_clarification_fix']=core.F02_CLARIFICATION_FIX;result['f03_clarification_fix']=core.F03_CLARIFICATION_FIX;result['f04_clarification_fix']=core.F04_CLARIFICATION_FIX;result['f05_confirmation_fix']=core.F05_CONFIRMATION_FIX;result['f06_confirmation_fix']=core.F06_CONFIRMATION_FIX;result['f07_confirmation_fix']=core.F07_CONFIRMATION_FIX;result['f08_confirmation_fix']=core.F08_CONFIRMATION_FIX;result['f09_confirmation_fix']=core.F09_CONFIRMATION_FIX;result['f10_confirmation_fix']=core.F10_CONFIRMATION_FIX;")
if __name__=='__main__':
 exec(compile(source,str(A/'generated_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(B/'c3r/eval_gateway.py')))
