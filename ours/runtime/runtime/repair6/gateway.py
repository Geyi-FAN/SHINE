"""R6 uses R4/R5 execution unchanged; add only clarification guard and raw contacts."""
import runpy,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path.insert(0,str(B));source=runpy.run_path(str(B/'continuation/live_gateway.py'),run_name='r6_source')['source']
anchor=' core,runner,authority=configure(a.out,a.gpu)';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from repair6.clarification_guard import install as install_clarification_guard\n install_clarification_guard(core.RobotState)')
source=source.replace('from continuation.terminal.completion_r4 import install as install_completion','from repair6.completion import install as install_completion')
assert source.count('from repair.recorder import Recorder')==1;source=source.replace('from repair.recorder import Recorder','from repair6.recorder import Recorder')
anchor='b.audit=Recorder(a.out,b);b.scoring_active=False;b.audit.record()';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from repair6.cached_logging import install as install_cached_logging\n install_cached_logging(b)')
# Reset public execution metadata immediately on actual semantic activation.
anchor="  previous_instruction=b.case.get('public_user_instruction','');previous_target=b.case.get('target_task',0)";assert source.count(anchor)==1
source=source.replace(anchor,"  state.agent_execution=dict(phase='planning',task_id=state.task_id,semantic_revision=state.task_intent_revision,completion_current_verified=False,source='current_task_activation')\n"+anchor)
anchor="result=base_snapshot();result['note']=";assert source.count(anchor)==1
source=source.replace(anchor,"result=base_snapshot();from repair6.public_execution import bind as bind_execution;result=bind_execution(result);result['note']=")
anchor=' state.command=command';assert source.count(anchor)==1
source=source.replace(anchor,anchor+'\n from repair6.waiting_prefetch import install as install_waiting_prefetch\n install_waiting_prefetch(b,state)')
if __name__=='__main__':exec(compile(source,str(B/'repair6/generated_gateway.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/gateway.py')))
