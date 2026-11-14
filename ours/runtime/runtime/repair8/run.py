"""R7 physical service; only replace the frozen voice bundle with R8."""
import runpy
from pathlib import Path
B=Path(__file__).resolve().parents[1]
source=runpy.run_path(str(B/'continuation/run_r7.py'),run_name='r8_source')['source']
old="B/'artifacts/repair7_audio_daemon/dist/index.js'";assert source.count(old)==1
source=source.replace(old,"B/'artifacts/repair8_audio_daemon/dist/index.js'")
if __name__=='__main__':exec(compile(source,str(B/'repair8/generated_run.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/run.py')))
