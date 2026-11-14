"""F07 explicit drawer affirmative; previous F06 loader retains all wrappers."""
import hashlib
from pathlib import Path
from f06_patch import install as previous
W=Path(__file__).resolve().parents[1]
def install(core):
 previous(core)
 import ast,native_execution
 path=W/'authority/native_candidate.py';tree=ast.parse(path.read_text());ns=dict(native_execution.__dict__)
 exec(compile(tree,str(path),'exec'),ns)
 original=native_execution.native_candidate;replacement=ns['native_candidate']
 assert not original.__closure__ and not replacement.__closure__,'Unexpected native wrapper; preserve it'
 original.__code__=replacement.__code__
 core.F07_CONFIRMATION_FIX=dict(version='F07-live-drawer-affirmative-consent-route-v2',native_routing_sha256=hashlib.sha256((W/'authority/native_candidate.py').read_bytes()).hexdigest(),semantics_sha256=hashlib.sha256((W/'authority/semantics.py').read_bytes()).hexdigest(),prior_semantic_wrappers_retained=True)
 return core.F07_CONFIRMATION_FIX
