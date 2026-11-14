import ast,copy,sys,tempfile,types,unittest
from pathlib import Path
from types import SimpleNamespace as N
import numpy as np
from g22.return_release import evidence,install

class ReleaseEvidence(unittest.TestCase):
    def setUp(self):
        point=dict(entity='wine_bottle',keypoint='K2',yx224=[110.,120.],det_confidence=.9,keypoint_confidence=.9)
        self.mon=N(active=dict(kind='return',object='wine_bottle',operation='return_wine_bottle'),samples=[dict(frame=i,width=.018,eef_xyz=[0,0,1],points={('wine_bottle','K2'):copy.deepcopy(point)})for i in [180,184,188,192]],history={('episode_start','wine_bottle','K2'):point},held='wine_bottle',settings=N(confidence=.35,min_width_m=.002,closed_width_m=.060,return_radius_px=6.,stable_radius_px=3.,motion_m=.008,near_hand_px=26.),diagnostics=dict(holding=dict(near_px=dict(wine_bottle=5.))))
        self.mon.point=lambda row,obj,k:row['points'].get((obj,k),{}).get('yx224')
    def test_aligned_closed_is_inspection_only(self):self.assertIsNotNone(evidence(self.mon));self.assertFalse(hasattr(self.mon,'grip_release_until'))
    def test_wrong_stage(self):self.mon.active['kind']='grasp';self.assertIsNone(evidence(self.mon))
    def test_other_object_held(self):self.mon.held='cheese';self.assertIsNone(evidence(self.mon))
    def test_far_from_return(self):self.mon.history[('episode_start','wine_bottle','K2')]=dict(self.mon.history[('episode_start','wine_bottle','K2')],yx224=[130,120]);self.assertIsNone(evidence(self.mon))
    def test_missing_point(self):self.mon.samples[-1]['points']={};self.assertIsNone(evidence(self.mon))
    def test_low_confidence_history(self):self.mon.history[('episode_start','wine_bottle','K2')]['det_confidence']=.1;self.assertIsNone(evidence(self.mon))
    def test_moving_hand(self):self.mon.samples[0]['eef_xyz']=[0,0,.97];self.assertIsNone(evidence(self.mon))
    def test_already_open(self):self.mon.samples[-1]['width']=.08;self.assertIsNone(evidence(self.mon))
    def test_same_frame_not_independent(self):self.mon.samples[-1]['frame']=181;self.assertIsNone(evidence(self.mon))
    def test_kernel_injection_once_with_two_stagnation_branches(self):
        old=sys.modules.get('recovery_observer');sys.modules['recovery_observer']=N(SYSTEM='base')
        try:
            with tempfile.TemporaryDirectory()as d:
                class Bridge:
                    recovery_class=object
                    root=Path(d)
                    def build_run_function(b):
                        src="def run():\n if os.environ.get('REPAIR_STAGNATION_OBSERVATION')=='1':pass\n if os.environ.get('REPAIR_STAGNATION_OBSERVATION')=='1':pass\n"
                        (b.root/'generated_kernel.py').write_text(src);b.run_function=lambda:None
                install(Bridge);b=Bridge();b.build_run_function();src=(b.root/'generated_kernel.py').read_text();self.assertEqual(src.count('G22_INSPECT_RETURN('),1);compile(src,'<test>','exec')
        finally:
            if old is None:sys.modules.pop('recovery_observer',None)
            else:sys.modules['recovery_observer']=old
if __name__=='__main__':unittest.main()
