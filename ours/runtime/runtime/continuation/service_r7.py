"""Same persistent facade; R7 authorized-resume gateway child."""
from pathlib import Path
B=Path(__file__).resolve().parents[1]
source=(B/'repair6/service.py').read_text();old="B/'repair6/gateway.py'";assert source.count(old)==1
source=source.replace(old,"B/'continuation/gateway_r7.py'")
source=source.replace("state['execution_service_revision']='R5'","state['execution_service_revision']='R7'")
if __name__=='__main__':exec(compile(source,str(B/'continuation/generated_service_r7.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/service.py')))
