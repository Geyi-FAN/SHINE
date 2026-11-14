"""One F05 permission-clause parsing delta; all prior guards retained."""
import hashlib
from pathlib import Path
from f04_patch import install as previous
W=Path(__file__).resolve().parents[1]
def install(core):
 previous(core)
 p=W/'authority/grounding.py'
 core.F05_CONFIRMATION_FIX=dict(version='F05-confirm-infinitive-not-location-v1',source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 return core.F05_CONFIRMATION_FIX
