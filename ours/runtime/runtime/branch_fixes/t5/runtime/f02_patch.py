"""Apply only reviewed F01+F02 evidence and role-aware errors in isolated C3r."""
import ast,hashlib,importlib.util,sys
from pathlib import Path
W=Path(__file__).resolve().parents[1]
def install(core):
 import clarification,grounding
 assert Path(clarification.__file__).resolve()==Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102/freeze/voice/robot_gateway/clarification.py')
 path=W/'authority/clarification.py';spec=importlib.util.spec_from_file_location('_f02_clarification_candidate',path);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 clarification.effective_clarification_turns=module.effective_clarification_turns
 clarification.ClarificationMixin._clarification_command=module.ClarificationMixin._clarification_command
 path_ground=W/'authority/grounding.py';tree=ast.parse(path_ground.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='validate_grounding')
 old=grounding.validate_grounding;exec(compile(ast.Module(body=[node],type_ignores=[]),str(path_ground),'exec'),grounding.__dict__)
 for target in list(sys.modules.values()):
  if target is not None and getattr(target,'validate_grounding',None)is old:setattr(target,'validate_grounding',grounding.validate_grounding)
 core.F01_CLARIFICATION_FIX=dict(version='F01-open-object-literal-binding-v1',source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),retained=True)
 core.F02_CLARIFICATION_FIX=dict(version='F02-destination-binding-role-errors-v1',source=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),grounding_source=str(path_ground),grounding_sha256=hashlib.sha256(path_ground.read_bytes()).hexdigest())
 return core.F02_CLARIFICATION_FIX
