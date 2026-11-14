"""Production gateway: tested entry fixes, without evaluator scheduling/budgets."""
import runpy,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B))
source=runpy.run_path(str(B/'t3repair/gateway.py'),run_name='entry_live_source')['source']
old=' install_completion(SingleOwnerBridge)';assert source.count(old)==1
source=source.replace(old,old+'\n from entryfix.support import install as install_support\n install_support(SingleOwnerBridge)')
old=' install_support(SingleOwnerBridge)';source=source.replace(old,old+'\n from entryfix.lifecycle import install as install_lifecycle\n install_lifecycle(SingleOwnerBridge)')
from entryfix.lifecycle import patch_loop
source=patch_loop(source)
old='previous_instruction=previous_instruction)';assert source.count(old)==1
source=source.replace(old,"previous_instruction=previous_instruction,source_task_start_xyz=xyz if b.task_count==2 else None,current_binary_state={'turn_on_stove':bool(b.cache_reader.snapshot['native_goal_relations']['turn_on_stove'])})")
if __name__=='__main__':exec(compile(source,str(B/'entryfix/generated_live_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(B/'entryfix/live_gateway.py')))
