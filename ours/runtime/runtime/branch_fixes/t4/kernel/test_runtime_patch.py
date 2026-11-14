import copy
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
import numpy as np

P=Path('/mnt/disk_2/geyi/voice_c3r_integration_20261102/freeze/f28d/source')
sys.path.insert(0,str(P))
from observed_completion import ObservedCompletion
from runtime_patch import install_ownership,revalidate_late_policy


class HoldingTests(unittest.TestCase):
    def setUp(self):
        install_ownership(ObservedCompletion)
        self.mon=ObservedCompletion();self.mon.held='bowl';self.mon.held_width=.018
        self.mon.last_held_frame=195
    def sample(self,width):
        return dict(frame=199,width=width,eef_yx=[50,50],eef_xyz=[0,0,1],points={})
    def test_historical_1mm_hand_cannot_keep_bowl_ownership(self):
        self.mon._holding(self.sample(.0009997234289680454))
        self.assertEqual(self.mon.held,'none')
        self.assertIn('negative_ownership_evidence',self.mon.holding_evidence)
        self.assertEqual(self.mon.events,[])
    def test_empty_evidence_overrides_occlusion_memory(self):
        self.mon.last_held_frame=199
        self.mon._holding(self.sample(.001))
        self.assertEqual(self.mon.held,'none')
    def test_normal_closed_grasp_is_not_revoked_for_occlusion(self):
        self.mon._holding(self.sample(.018))
        self.assertEqual(self.mon.held,'bowl')
    def test_existing_threshold_is_not_loosened(self):
        self.mon._holding(self.sample(.002))
        self.assertEqual(self.mon.held,'bowl')
    def test_actual_alternate_monitor_base_is_patched_explicitly(self):
        from completion_s1_base import ObservedCompletion as ActualBase
        class ActualMonitor(ActualBase):pass
        install_ownership(ActualMonitor)
        monitor=ActualMonitor();monitor.held='bowl';monitor.held_width=.018;monitor.last_held_frame=195
        monitor._holding(self.sample(.001))
        self.assertEqual(monitor.held,'none')
    def test_past_completion_is_not_deleted_or_reinvented(self):
        event=dict(operation='grasp_bowl',outcome='completed',confirmed_step=64)
        self.mon.events.append(event)
        self.mon._holding(self.sample(.001))
        self.assertEqual(self.mon.events,[event])


class LatePolicyTests(unittest.TestCase):
    def setUp(self):
        self.obs=dict(agentview_image=np.zeros((8,8,3),np.uint8),robot0_eye_in_hand_image=np.zeros((8,8,3),np.uint8),robot0_eef_quat=np.array([0,0,0,1]))
        self.logs=[]
        self.bridge=SimpleNamespace(state=SimpleNamespace(mode='running'),token=lambda:('e','t',1,2),closed=False,terminal_reason=None,
            obs=copy.deepcopy(self.obs),log=lambda *a,**k:self.logs.append((a,k)),
            observed_continuity=lambda *a:(True,dict(point_displacements_MAIN224_px={'bowl.K1':0.},passed=True)))
        self.context={'decision':{'reference':{'entity':'bowl','keypoint':'K1','time_source':'current'}}}
        self.job=dict(token=('e','t',1,2),capture_monotonic=time.monotonic()-6.5)
    def check(self,proof=None):
        return revalidate_late_policy(self.bridge,self.context,[],self.obs,proof or {'passed':True},self.job)
    def test_late_but_independently_current_scene_is_revalidated(self):
        old=self.job['capture_monotonic'];self.assertTrue(self.check())
        self.assertEqual(self.job['capture_monotonic'],old)
    def test_pause_always_rejects(self):
        self.bridge.state.mode='paused';self.assertFalse(self.check())
    def test_replaced_task_rejects(self):
        self.bridge.token=lambda:('e','new',1,3);self.assertFalse(self.check())
    def test_current_main_change_rejects(self):
        self.bridge.obs['agentview_image'][:]=50;self.assertFalse(self.check())
    def test_current_wrist_change_rejects(self):
        self.bridge.obs['robot0_eye_in_hand_image'][:]=50;self.assertFalse(self.check())
    def test_changed_rotation_rejects(self):
        self.bridge.obs['robot0_eef_quat']=np.array([0,0,.1,.995]);self.assertFalse(self.check())
    def test_original_continuity_failure_rejects(self):
        self.assertFalse(self.check({'passed':False}))
    def test_required_point_missing_rejects(self):
        self.bridge.observed_continuity=lambda *a:(True,dict(point_displacements_MAIN224_px={'plate.K1':0.}))
        self.assertFalse(self.check())
    def test_over_bound_rejects(self):
        self.job['capture_monotonic']=time.monotonic()-11;self.assertFalse(self.check())
    def test_terminal_rejects(self):
        self.bridge.terminal_reason='finished';self.assertFalse(self.check())


if __name__=='__main__':unittest.main()
