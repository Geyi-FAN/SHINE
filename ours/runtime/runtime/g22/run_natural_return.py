"""One actual source-task to return-switch regression; retain first outcome."""
import copy,hashlib,json,sys
from pathlib import Path
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2')]
import bootstrap
original=bootstrap.configure

def configure(out,gpu):
    core,runner,authority=original(out,gpu)
    from bridge import SingleOwnerBridge
    from g22.return_release import install
    install(SingleOwnerBridge)
    import policy_backend
    base=policy_backend.SmolHTTPClient
    class IsolatedClient(base):
        def infer(self,request):
            wire=copy.deepcopy(request);wire['evaluation_case_id']='G22-natural:'+out.parent.name+':'+wire['evaluation_case_id'];return super().infer(wire)
    policy_backend.SmolHTTPClient=IsolatedClient
    (out/'g22_addon.json').write_text(json.dumps(dict(addon='observed stalled return release',sha256=hashlib.sha256((B/'g22/return_release.py').read_bytes()).hexdigest(),source='actual Native source; no reset or pre-pause at switch; first outcome retained',geometry_preflight=False),indent=2))
    return core,runner,authority

bootstrap.configure=configure
import run_case
if __name__=='__main__':run_case.main()
