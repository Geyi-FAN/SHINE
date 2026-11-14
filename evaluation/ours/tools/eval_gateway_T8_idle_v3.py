"""Independent T8 idle observation sampling; no env.step or policy permission."""
import os,sys
from pathlib import Path
R=Path('/mnt/disk_4/geyi/audio_switch_benchmark/regressions/c3r_pi05_70_serial_20261108')
OLD=Path(__file__).resolve().parents[1]/'adapter/eval_gateway70.py'
ns=dict(__name__='T8_idle_observer_composition',__file__=str(OLD))
exec(compile(OLD.read_text(),str(OLD),'exec'),ns)
source=ns['source']
anchor="   if b.task_count==0 and state.task_id is None and state.mode=='idle':"
assert source.count(anchor)==1
source=source.replace(anchor,anchor+"\n    if spec.get('evaluation_family')=='T8' and now-getattr(b,'_idle_audit_publication',0)>.1:\n     b.audit._record('idle_publication_no_physics');b._idle_audit_publication=now")
if __name__=='__main__':
 W=Path(os.environ['C3R_RUNTIME_ROOT'])
 exec(compile(source,str(Path(__file__).parent/'generated_T8_idle_observer.py'),'exec'),dict(__name__='__main__',__file__=str(W/'runtime/unified/gateway.py')))
