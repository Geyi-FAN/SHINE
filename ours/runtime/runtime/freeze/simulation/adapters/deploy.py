"""Resolve local simulation assets after moving the workspace."""
import json,sys
from pathlib import Path
from common import ROOT,write_json
from schema import WORK
assets=json.loads((WORK/'pi05_memory_ad_data_20261013/mini/assets.json').read_text())
assets['turbovla_root']=str(WORK/'pi05_layout_memory_20261012/runtime/TurboVLA')
assets['libero_root']=str(WORK/'pi05_layout_memory_20261012/runtime/LIBERO')
assets['dataset_dir']=str(WORK/'pi05_memory_ad_data_20261013')
assets['stats_path']=str(WORK/'memory_dataset_v5_fast60_20261013/pipeline/configs/action_stats.json')
write_json(ROOT/'configs/assets.local.json',assets)
print('Local runtime paths:',ROOT/'configs/assets.local.json')
