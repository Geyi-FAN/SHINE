"""Install only F04 correction semantics, retaining prior C3r/T3/F01-F03 guards."""
import ast,hashlib,sys
from pathlib import Path
from f03_patch import install as install_previous
W=Path(__file__).resolve().parents[1]
def install(core):
 import grounding
 p=W/'authority/grounding.py'
 tree=ast.parse(p.read_text())
 old=grounding.command_content
 for name in ['explicit_object_correction','command_content']:
  node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
  exec(compile(ast.Module(body=[node],type_ignores=[]),str(p),'exec'),grounding.__dict__)
 for module in list(sys.modules.values()):
  if module is not None and getattr(module,'command_content',None) is old:setattr(module,'command_content',grounding.command_content)
 install_previous(core)
 core.F04_CLARIFICATION_FIX=dict(version='F04-explicit-object-correction-binding-v1',source=str(W/'authority/clarification.py'),sha256=hashlib.sha256((W/'authority/clarification.py').read_bytes()).hexdigest(),grounding_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 return core.F04_CLARIFICATION_FIX
