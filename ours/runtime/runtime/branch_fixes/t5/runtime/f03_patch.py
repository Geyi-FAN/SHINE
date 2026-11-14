"""Retain the prior loader and explicitly identify the single F03 addition."""
import hashlib
from pathlib import Path
from f02_patch import install as install_previous
W=Path(__file__).resolve().parents[1]
def install(core):
 install_previous(core)
 p=W/'authority/clarification.py'
 core.F03_CLARIFICATION_FIX=dict(version='F03-two-slot-deictic-binding-v1',source=str(p),sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 return core.F03_CLARIFICATION_FIX
