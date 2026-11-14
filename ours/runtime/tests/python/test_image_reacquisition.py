import io
import json
import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from unified.image_reacquisition import reacquire


def point(y=127., x=128., entity='wine_bottle', keypoint='K1', confidence=.3):
    return dict(entity=entity, keypoint=keypoint, yx224=[y,x],
                det_confidence=confidence, keypoint_confidence=.95)


class ImageReacquisitionTests(unittest.TestCase):
    def test_actual_composed_points_observe_uses_current_multiscale_results(self):
        from t3repair import memory
        memory.install()  # The live bridge installs this before Points.observe.
        import points
        with tempfile.TemporaryDirectory() as folder:
            p=points.Points.__new__(points.Points)
            p.folder=Path(folder);p.camera_id='main';p.episode_frame_at_takeover=0
            p.timings=[];p.memory={};p.history_camera={};p.current={};p.frame=None
            p.required_reference=dict(time_source='current',entity='wine_bottle',keypoint='K1')
            p.last_image_points={('wine_bottle','K1'):dict(point(129),frame=130)}
            p.scene=points.SceneMemory(Path(folder)/'memory.jsonl',episode_id='episode')
            p.scene.evidence(133,{},'main')
            p.proc=SimpleNamespace(stdin=io.StringIO(),stdout=io.StringIO('\n'.join(
                json.dumps(dict(frame=133,points=pts,seconds=.01))
                for pts in [[],[],[point(127)],[point(126,confidence=.4)]])+'\n'))
            with patch.dict('os.environ',REPAIR_ROI_YOLO='1'):
                p.observe(np.zeros((256,256,3),dtype=np.uint8),133)
            found,status=p.resolve('current','wine_bottle','K1')
            self.assertEqual(status,'fresh');self.assertTrue(found['multiscale_reacquisition'])
            self.assertEqual(found['frame'],133);self.assertEqual(found['yx224'],[126.,128.])
            requests=[json.loads(l)for l in p.proc.stdin.getvalue().splitlines()]
            self.assertEqual(len(requests),4)
            self.assertEqual([x['roi'][2]-x['roi'][0]for x in requests[1:]],[96,128,192])

    def run_search(self, first, second, reply_frame=133, prior=130, source='current'):
        proc=SimpleNamespace(stdin=io.StringIO(),stdout=io.StringIO('\n'.join(
            json.dumps(dict(frame=reply_frame,points=pts,seconds=.01))for pts in [first,second])+'\n'))
        reference=dict(entity='wine_bottle',keypoint='K1',time_source=source)
        result,audit=reacquire(proc,'current.png',133,reference,dict(frame=prior,yx224=[129.,128.]))
        return result,audit,proc.stdin.getvalue()

    def test_two_current_crops_agree_and_do_not_output_history(self):
        selected,audit,requests=self.run_search([point(127)],[point(126,confidence=.4)])
        self.assertEqual(selected[0]['source_frame'],133)
        self.assertEqual(selected[0]['yx224'],[126.,128.])
        self.assertNotEqual(selected[0]['yx224'],[129.,128.])
        self.assertFalse(audit['cached_coordinate_used_as_output'])
        self.assertEqual(len(requests.splitlines()),2)

    def test_conflicting_or_single_crop_cannot_supply_a_point(self):
        for first,second in [([point()],[point(180)]),([point()],[]),([],[])]:
            self.assertEqual(self.run_search(first,second)[0],[])

    def test_type_and_original_confidence_thresholds_preserved(self):
        for bad in [point(entity='bowl'),point(keypoint='K2'),point(confidence=.09),point(x=float('nan'))]:
            self.assertEqual(self.run_search([bad],[bad])[0],[])

    def test_stale_history_and_historical_target_not_reused(self):
        for kwargs in [dict(prior=10),dict(prior=134),dict(source='episode_start')]:
            result,audit,requests=self.run_search([point()],[point()],**kwargs)
            self.assertEqual(result,[]);self.assertEqual(requests,'')

    def test_mismatched_worker_frame_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'frame mismatch'):
            self.run_search([point()],[point()],reply_frame=132)
