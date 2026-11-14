"""A transformed real observer must use the subsequently installed I/O guard."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import recovery_observer
from t06l_inspection import install


class RecoveryTransportLifecycleTests(unittest.TestCase):
    def test_actual_scoped_observer_resolves_latest_transport(self):
        class Local(recovery_observer.RecoveryObserver):
            pass
        # The production installation order: transform first, hook transport
        # afterwards. Calling a stale reference would hit forbidden_old.
        def forbidden_old(*args, **kwargs):
            raise AssertionError('Bypassed the subsequently installed owner guard')
        seen = []
        def current_guard(req, **kwargs):
            seen.append((req, kwargs))
            raise RuntimeError('guard reached before any network request')
        with patch.object(recovery_observer, 'request_json', forbidden_old):
            install(Local)
            recovery_observer.request_json = current_guard
            with tempfile.TemporaryDirectory() as d:
                observer = object.__new__(Local)
                observer.folder = Path(d)
                observer.calls = []
                observer.cfg = dict(model='offline', chat_url='http://127.0.0.1:1')
                observer.key = 'offline-placeholder'
                observer.episode_reference = Path(d)/'missing.png'
                rows = [dict(frame=f, sensor=dict(width=.078,eef_xyz=[0,0,1],eef_yx=[50,50]),
                    geometry={},image_points=[],main=np.zeros((24,24,3),np.uint8),
                    wrist=np.zeros((24,24,3),np.uint8)) for f in [0,4,8]]
                # The real observer records transport errors in its bounded
                # attempt list; it may catch the sentinel internally.
                try:
                    observer.check('put the wine bottle on the rack', rows,
                                   dict(operation='grasp_wine_bottle'))
                except RuntimeError as exc:
                    self.assertIn('guard reached', str(exc))
        self.assertTrue(seen, 'the actual observer never entered the owner guard')
        self.assertTrue(all(item[1].get('timeout') == 90 for item in seen))
