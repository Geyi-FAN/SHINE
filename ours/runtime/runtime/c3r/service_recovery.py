"""Explicit opt-in entry for C3r bounded recovery; core profile is the default."""
import os
import runpy
from pathlib import Path
os.environ['C3R_PROFILE'] = 'recovery'
runpy.run_path(str(Path(__file__).with_name('service.py')), run_name='__main__')
