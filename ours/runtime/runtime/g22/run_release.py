"""Full Agent pipeline from one reconstructed supported/closed-finger state."""
import argparse,copy,json,sys
from pathlib import Path
import numpy as np
B=Path(__file__).resolve().parents[1];sys.path[:0]=[str(B),str(B/'g2')]
import bootstrap
from g22.context import restore_complete
original=bootstrap.configure
parser=argparse.ArgumentParser();parser.add_argument('--arm',choices=['original','recovery'],required=True);parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);opts=parser.parse_args()

def configure(out,gpu):
    core,runner,authority=original(out,gpu)
    from bridge import SingleOwnerBridge
    if opts.arm=='recovery':
        from g22.return_release import install
        install(SingleOwnerBridge)
    context=dict(np.load(opts.fixture/'supported.npz'))
    def checked(case,folder):
        def restore(env,unused):
            obs=restore_complete(env,context,authority);actual=authority.state.capture(env)
            checks={k:bool(np.array_equal(actual[k],v,equal_nan=True))for k,v in context.items()if k in actual}
            assert all(checks.values()),checks
            from g22.close_pair import digest
            (out/'release_start.json').write_text(json.dumps(dict(arm=opts.arm,fixture=str(opts.fixture),full_context_sha256=digest(context),restored_keys=checks,scope='reconstructed diagnostic; original episode history retained; no post-start state writes'),indent=2))
            return obs
        return restore
    authority.checked_restore=checked
    return core,runner,authority

bootstrap.configure=configure
import run_case
sys.argv=['run_case','--case-id','SW4_T02_M2_T08_SWITCH_T02_M2_S04','--out',str(opts.out),'--gpu','4','--port','19866','--control-budget','500']
run_case.main()
