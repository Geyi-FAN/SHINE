"""Same frozen audio runtime; remove only an after-result facade wait.

The persistent HTTP facade intentionally never exits when a test client sends
/evaluator/finish. Waiting 30s for it after PCM flushing/result capture cannot
produce new scored evidence. Terminate it in the existing finally cleanup,
retaining the independent 30s between-cloud-session cooling period.
"""
from pathlib import Path
B=Path(__file__).resolve().parents[1]
source=(B/'repair6/run.py').read_text()
old="   if not probe:\n    try:processes[1].wait(30)\n    except subprocess.TimeoutExpired:pass"
assert source.count(old)==1
source=source.replace(old,"   # Client already captured its result and flushed received PCM.\n   # Persistent facade is shut down by the existing finally block.")
if __name__=='__main__':
 exec(compile(source,str(B/'continuation/generated_run96.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/run.py')))
