"""Full shared C3r with T3's original independent recording and budgets."""
import runpy
import importlib.util
import sys
from pathlib import Path
B=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102');sys.path.insert(0,str(B))
private_spec=importlib.util.spec_from_file_location('_t3_frozen_language_repairs',Path(__file__).with_name('runtime_repairs.py'))
private=importlib.util.module_from_spec(private_spec);sys.modules[private_spec.name]=private;private_spec.loader.exec_module(private)
source=runpy.run_path(str(B/'c3r/eval_gateway.py'),run_name='t3_c3r_parent')['source']
anchor=' core,runner,authority=configure(a.out,a.gpu)'
assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from _t3_frozen_language_repairs import install as install_t3_language_repairs\n install_t3_language_repairs(core)')
anchor=' class Native(NativeExecution):';assert source.count(anchor)==1
source=source.replace(anchor,' from native_prefetch.scheduler import NativePrefetchMixin\n class Native(NativePrefetchMixin,NativeExecution):')
anchor="result['execution_kernel']='C3r';";assert source.count(anchor)==1
source=source.replace(anchor,anchor+"result['native_scheduler']='prefetch-frame-aligned-v1';result['t3_evaluation_adapter']='ZH2C10-original-contract-v1';")
if __name__=='__main__':
    exec(compile(source,str(B/'t3_adapter/generated_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(B/'c3r/eval_gateway.py')))
