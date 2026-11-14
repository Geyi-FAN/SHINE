"""Persistent single-owner shell, full C3r T3 child, explicit version identity."""
import os
import runpy
from pathlib import Path
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102');A=Path(__file__).resolve().parent;os.environ['C3R_PROFILE']='recovery'
source=runpy.run_path(str(B/'c3r/service.py'),run_name='t3_service_parent')['source']
old="B/'c3r/gateway.py'";assert source.count(old)==1;source=source.replace(old,"Path("+repr(str(A/'gateway.py'))+")")
old="state['execution_service_revision']='R7-T3.2+C3r'";assert source.count(old)==1
source=source.replace(old,"state['execution_service_revision']='R7-T3.2+C3r+NativePrefetch-v1';state['t3_evaluation_adapter']='ZH2C10-original-contract-v1'")
assert source.count('p.wait(12)')==1;source=source.replace('p.wait(12)','p.wait(60)')
if __name__=='__main__':exec(compile(source,str(B/'t3_adapter/generated_service.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/service.py')))
