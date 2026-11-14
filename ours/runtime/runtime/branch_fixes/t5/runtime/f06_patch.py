"""F06 patches only current selection semantics and context-bound approval."""
import ast,hashlib,inspect,sys,types
from pathlib import Path
from f05_patch import install as previous
W=Path(__file__).resolve().parents[1]
def emit(path,name,namespace):
 tree=ast.parse(path.read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name==name)
 exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
 return namespace[name]
def original_inspector(root,filename):
 pending=[root];seen=set()
 while pending:
  f=pending.pop()
  if id(f)in seen:continue
  seen.add(id(f))
  if f.__code__.co_filename==filename and f.__name__=='inspect_semantics':return f
  if f.__closure__:
   pending += [c.cell_contents for c in f.__closure__ if isinstance(c.cell_contents,types.FunctionType)]
 raise RuntimeError('Frozen base inspector not found; refuse to drop wrappers')
def install(core):
 import grounding,semantics
 p=W/'authority/grounding.py';emit(p,'explicit_object_selection',grounding.__dict__)
 previous(core)
 semantics.explicit_object_selection=grounding.explicit_object_selection
 old=semantics.confirmation_answer
 p=W/'authority/semantics.py';emit(p,'matching_task_confirmation',semantics.__dict__);new=emit(p,'confirmation_answer',semantics.__dict__)
 for m in list(sys.modules.values()):
  if m is not None and getattr(m,'confirmation_answer',None)is old:setattr(m,'confirmation_answer',new)
 base=original_inspector(semantics.inspect_semantics,str(Path(semantics.__file__)))
 replacement=emit(p,'inspect_semantics',dict(semantics.__dict__))
 assert not base.__code__.co_freevars and not replacement.__code__.co_freevars
 base.__code__=replacement.__code__
 p=W/'authority/core_methods.py'
 for name in ['record_interaction','_resolve_proposal']:
  old_method=getattr(core.RobotState,name)
  assert old_method.__module__=='core' and not old_method.__closure__,(name,'unexpected wrapper')
  setattr(core.RobotState,name,emit(p,name,core.__dict__))
 core.F06_CONFIRMATION_FIX=dict(version='F06-current-object-and-live-task-approval-v1',grounding_sha256=hashlib.sha256((W/'authority/grounding.py').read_bytes()).hexdigest(),semantics_sha256=hashlib.sha256((W/'authority/semantics.py').read_bytes()).hexdigest(),core_methods_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),prior_semantic_wrappers_retained=True)
 return core.F06_CONFIRMATION_FIX
