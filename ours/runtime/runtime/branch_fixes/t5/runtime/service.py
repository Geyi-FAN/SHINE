"""Original private single-simulator service, selecting only our F01 gateway."""
import runpy
from pathlib import Path
A=Path(__file__).resolve().parent
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102')
source=runpy.run_path('/mnt/disk_2/geyi/t5_c3r_30_20261103/runtime/service.py',run_name='f01_parent_service')['source']
old="Path("+repr('/mnt/disk_2/geyi/t5_c3r_30_20261103/runtime/gateway.py')+")"
assert source.count(old)==1
source=source.replace(old,"Path("+repr(str(A/'gateway.py'))+")")
if __name__=='__main__':
 exec(compile(source,str(A/'generated_service.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/service.py')))
