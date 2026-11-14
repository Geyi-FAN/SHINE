"""Read-only partial score monitor; does not touch runtime, audio or case data."""
import json,subprocess,time
from pathlib import Path
from continuation.chain_r6 import B,ROOT,SIM,REGROOT,REG
def main():
 count=-1
 while True:
  now=len(list((REG/'cases').glob('*/verdict.json')))
  if now and now!=count:
   subprocess.run([SIM,'-m','continuation.audited_score','--root',str(REGROOT),'--label',REG.name,'--waiting','45'],cwd=B,check=True);count=now
  if(REG/'COMPLETED.json').exists()or(REG/'BLOCKED_CLOUD.json').exists()or(REG/'INVALID_AUDIO_TIMING.json').exists():return
  time.sleep(15)
if __name__=='__main__':main()
