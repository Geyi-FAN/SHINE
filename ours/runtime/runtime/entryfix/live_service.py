"""Original persistent lifecycle facade, only selects the repaired live gateway."""
from pathlib import Path
B=Path(__file__).resolve().parents[1];source=(B/'repair6/service.py').read_text()
old="B/'repair6/gateway.py'";assert source.count(old)==1
source=source.replace(old,"B/'entryfix/live_gateway.py'").replace("state['execution_service_revision']='R5'","state['execution_service_revision']='R7-T3.2'")
if __name__=='__main__':exec(compile(source,str(B/'entryfix/generated_live_service.py'),'exec'),dict(__name__='__main__',__file__=str(B/'repair6/service.py')))
