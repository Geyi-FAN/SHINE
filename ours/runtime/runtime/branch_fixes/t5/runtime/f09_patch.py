"""F09 retains F01-F08 and exposes the new negative-confirmation source hash."""
import hashlib
from pathlib import Path
from f08_patch import install as previous
W=Path(__file__).resolve().parents[1]
def install(core):
 previous(core)
 core.F09_CONFIRMATION_FIX=dict(version='F09-negative-answer-current-permission-v1',semantics_sha256=hashlib.sha256((W/'authority/semantics.py').read_bytes()).hexdigest(),prior_wrappers_retained=True)
 return core.F09_CONFIRMATION_FIX
