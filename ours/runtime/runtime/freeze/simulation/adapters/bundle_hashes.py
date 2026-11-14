"""Hash/verify all portable runtime artifacts, excluding generated run outputs."""
import argparse,json,hashlib
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(8*1024*1024),b''):h.update(x)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--verify',action='store_true');a=p.parse_args();a.root=a.root.resolve();manifest=a.root/'BUNDLE_SHA256.json'
 stats_file=a.root/'BUNDLE_FILE_STAT.json'
 if a.verify:
  rows=json.loads(manifest.read_text())
  for n,h in rows.items():assert sha(a.root/n)==h,n
  print('VERIFIED',len(rows),'files');return
 rows={};current_stats={};old=json.loads(manifest.read_text()) if manifest.exists() else {};previous=json.loads(stats_file.read_text()) if stats_file.exists() else {}
 for f in sorted(a.root.rglob('*')):
  if not f.is_file() or f.name in ('BUNDLE_SHA256.json','BUNDLE_FILE_STAT.json'):continue
  rel=f.relative_to(a.root)
  if any(x in rel.parts for x in ('.venv','.git','__pycache__','.jax_cache','logs','evaluations','smoke_eval')):continue
  if 'mini/runtime' in str(rel):continue
  stat=[f.stat().st_size,f.stat().st_mtime_ns];current_stats[str(rel)]=stat
  rows[str(rel)]=old[str(rel)] if previous.get(str(rel))==stat and str(rel) in old else sha(f)
 stats_file.write_text(json.dumps(current_stats,indent=2)+'\n')
 manifest.write_text(json.dumps(rows,indent=2)+'\n');print('HASHED',len(rows),'files')
if __name__=='__main__':main()
