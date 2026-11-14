"""F08 patches original acoustic source lookup without dropping lifecycle wrappers."""
import hashlib,types
from pathlib import Path
from f07_patch import install as previous
from f06_patch import emit
W=Path(__file__).resolve().parents[1]
def command_base(root):
 pending=[root];seen=set()
 while pending:
  f=pending.pop()
  if id(f)in seen:continue
  seen.add(id(f))
  if f.__name__=='_command'and f.__module__=='core'and Path(f.__code__.co_filename).name=='core.py'and not f.__closure__:return f
  if f.__closure__:pending += [c.cell_contents for c in f.__closure__ if isinstance(c.cell_contents,types.FunctionType)]
 raise RuntimeError('Actual frozen core command not found; refuse to erase wrappers')
def install(core):
 previous(core)
 p=W/'authority/core_methods.py';old=command_base(core.RobotState._command);new=emit(p,'_command',dict(core.__dict__))
 assert not new.__closure__
 old.__code__=new.__code__
 core.F08_CONFIRMATION_FIX=dict(version='F08-bound-source-audio-confirmation-v1',core_methods_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),prior_wrappers_retained=True)
 return core.F08_CONFIRMATION_FIX
