"""Exact frozen case runner, override only the enlarged GPU/renderer map."""
from pathlib import Path
import hashlib,json
Q=Path(__file__).resolve().parents[1];original=Q/'tools/one_case.py'
locked=json.loads((Q/'plans/FROZEN.json').read_text())['files']['tools/one_case.py']
assert hashlib.sha256(original.read_bytes()).hexdigest()==locked
source=original.read_text();needle="gpu=read(N/'reports/GPU_MAP.json')";assert source.count(needle)==1
source=source.replace(needle,"gpu=read(Q/'scale/GPU_MAP7.json')")
exec(compile(source,str(original),'exec'),dict(__name__='__main__',__file__=str(original)))
