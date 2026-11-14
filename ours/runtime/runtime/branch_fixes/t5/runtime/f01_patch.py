"""Install only the reviewed clarification-evidence binding into private C3r."""
import hashlib, importlib.util, sys
from pathlib import Path
W=Path(__file__).resolve().parents[1]
FIX_ID='F01-open-object-literal-binding-v1'
def install(core):
 import clarification
 expected=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102/freeze/voice/robot_gateway/clarification.py')
 assert Path(clarification.__file__).resolve()==expected.resolve(),clarification.__file__
 candidate=W/'authority/clarification.py'
 spec=importlib.util.spec_from_file_location('_f01_clarification_candidate',candidate)
 module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 clarification.effective_clarification_turns=module.effective_clarification_turns
 core.F01_CLARIFICATION_FIX=dict(version=FIX_ID,source=str(candidate),sha256=hashlib.sha256(candidate.read_bytes()).hexdigest())
 return core.F01_CLARIFICATION_FIX
