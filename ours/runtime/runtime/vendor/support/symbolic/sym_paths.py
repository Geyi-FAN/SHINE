import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get('MEMORY_WORK_ROOT', ROOT.parent))
BASE_CODE = WORK / 'pi05_memory_ad_experiments_20261013'
BASE_DATA = Path(os.environ.get('MEMORY_DATA_ROOT', WORK / 'pi05_memory_ad_data_20261013'))
STORAGE = Path(os.environ.get('SYMBOLIC_STORAGE', '/mnt/disk_4/geyi/pi05_symbolic_V3R_20261016'))
DATA = STORAGE / 'data'
for p in (BASE_CODE / 'src', WORK / 'openpi/src', WORK / 'openpi/packages/openpi-client/src'):
    if str(p) not in sys.path:
        sys.path.append(str(p))

