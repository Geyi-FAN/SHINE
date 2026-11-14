import copy
import unittest
from output_contract import normalize_evidence_frames


class RecoveryFrameIDs(unittest.TestCase):
    def test_actual_provider_string_id_is_losslessly_normalized(self):
        raw=dict(held_object='wine_bottle',evidence_frames=['196'],support_visible=dict(bowl=True))
        old=copy.deepcopy(raw);fixed=normalize_evidence_frames(raw)
        self.assertEqual(fixed,dict(raw,evidence_frames=[196]));self.assertEqual(raw,old)

    def test_unknown_frame_is_never_replaced_by_current_frame(self):
        fixed=normalize_evidence_frames(dict(evidence_frames=['192']))
        self.assertFalse(set(fixed['evidence_frames'])<={196})

    def test_ambiguous_or_fractional_ids_still_fail_integer_schema(self):
        import jsonschema
        schema=dict(type='array',items=dict(type='integer',enum=[196]))
        for value in ['196.0',' 196','0196','196 or 197',True,196.5,'-196']:
            with self.subTest(value=value),self.assertRaises(jsonschema.ValidationError):
                jsonschema.validate(normalize_evidence_frames(dict(evidence_frames=[value]))['evidence_frames'],schema)

    def test_no_missing_evidence_or_semantic_field_is_filled(self):
        for raw in [{},dict(evidence_frames=[]),dict(held_object='unknown',evidence_frames=[196],recovery_request='observe_only')]:
            self.assertEqual(normalize_evidence_frames(raw),raw)

    def test_normalized_actual_id_passes_both_observer_frame_fences(self):
        from t06l_inspection import extra_errors
        fixed=normalize_evidence_frames(dict(evidence_frames=['196'],held_object='wine_bottle',recovery_request='none'))
        self.assertTrue(set(fixed['evidence_frames'])<={192,196})
        self.assertEqual(extra_errors(fixed,dict(scoped_inspection='initial_contact',current_image_frames_shown=[196])),[])

    def test_unshown_historical_frame_still_fails_scoped_rgb_fence(self):
        from t06l_inspection import extra_errors
        fixed=normalize_evidence_frames(dict(evidence_frames=['192'],held_object='wine_bottle',recovery_request='none'))
        self.assertTrue(extra_errors(fixed,dict(scoped_inspection='initial_contact',current_image_frames_shown=[196])))

    def test_real_scoped_observer_accepts_once_and_preserves_raw_provider_reply(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        import numpy as np
        import recovery_observer
        from t06l_inspection import install
        install(recovery_observer.RecoveryObserver)
        raw=dict(held_object='wine_bottle',support_visible=dict(bowl=True,cheese=None,wine_bottle=False,plate=True),
                 evidence_frames=['196'],rationale='Bottle at the closed hand.',recovery_request='none',release_object=None)
        with tempfile.TemporaryDirectory() as folder:
            ob=object.__new__(recovery_observer.RecoveryObserver)
            ob.folder=Path(folder);ob.calls=[];ob.cfg=dict(model='offline',chat_url='http://127.0.0.1/offline');ob.key='offline-test';ob.episode_reference=ob.folder/'absent.png'
            rows=[dict(frame=f,sensor=dict(width=.015),main=np.zeros((8,8,3),np.uint8),wrist=np.zeros((8,8,3),np.uint8))for f in [192,196]]
            with patch.object(recovery_observer,'request_json',return_value=dict(choices=[dict(message=dict(content=json.dumps(raw)))]))as request:
                result=ob.check('Return the wine bottle.',rows,{})
            self.assertTrue(result['accepted']);self.assertEqual(request.call_count,1)
            self.assertEqual(result['attempts'][0]['raw_output'],raw)
            self.assertEqual(result['response']['evidence_frames'],[196])
