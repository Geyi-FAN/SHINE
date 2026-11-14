"""Keep R7-T3.2 persistent service lifecycle, select the C3r child only."""
from pathlib import Path
B = Path(__file__).resolve().parents[1]
source = (B/'repair6/service.py').read_text()
old = "B/'repair6/gateway.py'"
assert source.count(old) == 1
source = source.replace(old, "B/'c3r/gateway.py'")
source = source.replace("state['execution_service_revision']='R5'",
                        "state['execution_service_revision']='R7-T3.2+C3r'")
if __name__ == '__main__':
    exec(compile(source, str(B/'c3r/generated_service.py'), 'exec'),
         dict(__name__='__main__', __file__=str(B/'repair6/service.py')))
