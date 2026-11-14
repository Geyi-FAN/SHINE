"""Same r17 benchmark adapter; controlled prefix is a private startup fixture."""
from pathlib import Path
import os,sys
HERE=Path('/mnt/disk_4/geyi/audio_switch_benchmark/T6/releases/t6-prefix-v2-20261108/adapter')
BENCHMARK_ROOT=next(p for p in HERE.parents if (p/'T6/current/dataset/selected90.private.json').exists())
OLD=Path(__file__).resolve().parents[1]/'adapter/eval_gateway70.py'
sys.path.insert(0,str(HERE/'support'))
namespace=dict(__name__='private_eval_composer',__file__=str(OLD))
exec(compile(OLD.read_text(),str(OLD),'exec'),namespace)
source=namespace['source'];assert source.count('from t6_eval import Evaluator')==1
source=source.replace('from t6_eval import Evaluator','from t6_replay_eval import Evaluator')
anchor='if t6.service():tick=time.monotonic()+.05'
assert source.count(anchor)==1
source=source.replace(anchor,"if t6.service():tick=time.monotonic()+(0. if getattr(t6,'replaying',False)else .05)")
# Explicit private benchmark replay is authorized initialization, not a user task.
# Keep v20's idle freeze for ordinary live execution, but allow this registered
# preparer to run before its active task is installed.
idle="if b.task_count==0 and state.task_id is None and state.mode=='idle':"
assert source.count(idle)==1
source=source.replace(idle,"if b.task_count==0 and state.task_id is None and state.mode=='idle' and not(t6 and t6.pending):")
sys.path.insert(0,str(HERE))
if __name__=='__main__':
    runtime=Path(os.environ['C3R_RUNTIME_ROOT'])
    exec(compile(source,str(HERE/'generated_replay_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(runtime/'runtime/unified/gateway.py')))
