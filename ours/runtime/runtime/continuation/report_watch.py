"""Read-only report refresh for the running fixed96; never calls a model."""
import time
from continuation import progress,final_report,analyze96

if __name__=='__main__':
 while True:
  try:
   progress.update();final_report.main();analyze96.main()
  except Exception as e:print(type(e).__name__+': '+str(e),flush=True)
  time.sleep(30)
