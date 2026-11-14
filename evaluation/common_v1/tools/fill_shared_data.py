from pathlib import Path
import shutil,json,hashlib
Q=Path(__file__).resolve().parents[1];a=Q/'actors/B1';b=Q/'actors/B0';copied=[]
for p in(a/'data').rglob('*'):
 if p.is_file()and not p.is_symlink():
  out=b/'data'/p.relative_to(a/'data')
  if not out.exists():out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,out);copied.append(dict(path=str(out.relative_to(b)),sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(Q/'reports/COMMON_DATA_FILLS.json').write_text(json.dumps(copied,indent=2)+'\n');print('filled',len(copied),'shared fixture/catalog files; no actor prompt changed')
