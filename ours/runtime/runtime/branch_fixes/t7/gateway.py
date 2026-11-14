"""Full shared C3r with T3's original independent recording and budgets."""
import runpy
import importlib.util
import sys
from pathlib import Path
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102');sys.path.insert(0,str(B))
private_spec=importlib.util.spec_from_file_location('_t7_frozen_language_repairs',Path(__file__).with_name('runtime_repairs.py'))
private=importlib.util.module_from_spec(private_spec);sys.modules[private_spec.name]=private;private_spec.loader.exec_module(private)
source=runpy.run_path(str(B/'c3r/eval_gateway.py'),run_name='t3_c3r_parent')['source']
anchor=' core,runner,authority=configure(a.out,a.gpu)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from _t7_frozen_language_repairs import install as install_t3_language_repairs\n install_t3_language_repairs(core)')
anchor=' install_t3_language_repairs(core)'
source=source.replace(anchor,anchor+'\n import sys;sys.path.insert(0,'+repr(str(Path(__file__).resolve().parent))+')\n from waiting_runtime import install as install_t7_waiting\n install_t7_waiting(core)')
anchor=' class Native(NativeExecution):';assert source.count(anchor)==1
source=source.replace(anchor,' from native_prefetch.scheduler import NativePrefetchMixin\n class Native(NativePrefetchMixin,NativeExecution):')
anchor="result['execution_kernel']='C3r';";assert source.count(anchor)==1
source=source.replace(anchor,anchor+"result['native_scheduler']='prefetch-frame-aligned-v1';result['t7_evaluation_adapter']='Goal10-waiting-C3r-v10-evidence-latency';")
anchor=' install_t7_waiting(core)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n import planner\n from stage_continuation import install as install_t7_continuation\n install_t7_continuation(planner)')
anchor=' from native_execution import NativeExecution,native_candidate,CATALOG'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from speech_routing import native_candidate')
# Disable only unsafe speculative wording: NativePrefetch action scheduling stays.
anchor=" from repair6.waiting_prefetch import install as install_waiting_prefetch\n install_waiting_prefetch(b,state)"
assert source.count(anchor)==1
source=source.replace(anchor," # T7: wording/planning starts under the actual current kernel identity.")
anchor="    stepped=b.pump(now>=tick)\n    if stepped:tick=time.monotonic()+.05"
assert source.count(anchor)==1
source=source.replace(anchor,"    stepped=b.pump(now>=tick)\n    from terminal_observation import tick as terminal_hold_tick\n    if not stepped:stepped=terminal_hold_tick(b,state,now>=tick)\n    if stepped:tick=time.monotonic()+.05")
# The old 1600s process lifetime also consumed shared-voice queue time. This is
# only the idle process watchdog; client/goal action and wall budgets stay fixed.
anchor="spec.get('serve_live')or time.monotonic()-started<1600"
assert source.count(anchor)==1
source=source.replace(anchor,"spec.get('serve_live')or time.monotonic()-started<spec.get('service_lifetime_s',1600)")
sys.path.insert(0,str(Path(__file__).resolve().parent))
anchor = ' install_c3r(SingleOwnerBridge)'
assert source.count(anchor) == 1
source = source.replace(anchor, anchor + '\n from latency_integration import install as install_latency\n install_latency(SingleOwnerBridge)')
if __name__=='__main__':
    exec(compile(source,str(Path(__file__).with_name('generated_gateway.py')),'exec'),dict(__name__='__main__',__file__=str(B/'c3r/eval_gateway.py')))
