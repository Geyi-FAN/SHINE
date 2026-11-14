"""Retain all F01-F09; F06 loader installs updated whole confirmation semantics."""
import hashlib
from pathlib import Path
from f09_patch import install as previous
W=Path(__file__).resolve().parents[1]
def install(core):
 previous(core)
 core.F10_CONFIRMATION_FIX=dict(version='F10-cancel-request-late-consent-v1',semantics_sha256=hashlib.sha256((W/'authority/semantics.py').read_bytes()).hexdigest(),prior_wrappers_retained=True)
 return core.F10_CONFIRMATION_FIX
