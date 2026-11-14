"""Declared controlled-source track, separate from natural-source results."""
import os,sys
from pathlib import Path
R=Path('/mnt/disk_4/geyi/audio_switch_benchmark/regressions/c3r_pi05_70_serial_20261108')
OLD=Path(__file__).resolve().parents[1]/'adapter/eval_gateway70.py'
ns=dict(__name__='controlled_T3_composition',__file__=str(OLD))
exec(compile(OLD.read_text(),str(OLD),'exec'),ns);source=ns['source']
anchor=" server=http.GatewayHTTPServer("
assert source.count(anchor)==1
source=source.replace(anchor," from t3_preparer import SourcePreparer\n preparer=SourcePreparer(b,state,spec,a.out)\n"+anchor)
anchor='   if http.priority_stop_enabled:http.priority_stop.drain(state.command)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'''
   if not preparer.done:
    preparer.service()
    if now-last_image>.2:jpeg();last_image=now
    tick=time.monotonic();continue
   preparer.adopt_source()''')
if __name__=='__main__':
 W=Path(os.environ['C3R_RUNTIME_ROOT'])
 exec(compile(source,str(Path(__file__).parent/'generated_gateway_T3_controlled.py'),'exec'),dict(__name__='__main__',__file__=str(W/'runtime/unified/gateway.py')))
