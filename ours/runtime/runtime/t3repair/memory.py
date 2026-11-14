"""Image-only points, tolerant static epochs and explicit provenance.

Cache validity remains simulator-assisted, as in M1; these facts never supply
pixel positions to the planner. No cross-K or historical-point substitution.
"""
import inspect
import textwrap
import numpy as np


def drawer_same_epoch(a, b, translation_m, rotation_deg):
    from scene_memory import pose_deltas
    if a is None or b is None or len(a) != 8 or len(b) != 8:
        return False
    delta, angle = pose_deltas(a[:7], b[:7])
    return delta <= translation_m and angle <= rotation_deg and abs(a[7] - b[7]) <= translation_m


def install():
    import scene_memory
    import points
    if getattr(scene_memory.SceneMemory, '_t3_static_epochs', False):
        return
    previous = scene_memory.SceneMemory

    class StaticMemory(previous):
        _t3_static_epochs = True

        def same_pose(self, a, b):
            return drawer_same_epoch(a, b, self.object_translation, self.object_rotation)

        def resolve(self, entity, keypoint):
            slot = (entity, keypoint)
            # Current points have passed the same bounds/confidence/jump checks.
            if slot in self.current:
                return self.current[slot], 'fresh'
            return super().resolve(entity, keypoint)

        def ingest(self, values, frame):
            accepted = []
            for p in values:
                slot = p['entity'], p['keypoint']
                anchor = self.anchors.get(slot)
                if anchor and np.linalg.norm(np.asarray(p['yx224']) - np.asarray(anchor['point']['yx224'])) > 10:
                    self.log('reject', entity=slot[0], keypoint=slot[1],
                             reason='static_anchor_pixel_jump', candidate=p['yx224'])
                    continue
                accepted.append(p)
            return super().ingest(accepted, frame)

    scene_memory.SceneMemory = StaticMemory
    points.SceneMemory = StaticMemory
    # One extra image-only crop only after the full frame actually missed the
    # required slot. It searches for a fresh detection; it never fills a point.
    source = textwrap.dedent(inspect.getsource(points.Points.observe))
    old = "ref['keypoint']=='K3' and ref['entity'] in ('bowl','plate')"
    assert source.count(old) == 1, 'YOLO crop integration anchor changed'
    source = source.replace(old, "ref['keypoint'] in ('K1','K3') and ref['entity'] in ('bowl','plate','cheese','wine_bottle')")
    namespace = dict(points.Points.observe.__globals__)
    exec(compile(source, '<T3 image-only typed-slot reacquisition>', 'exec'), namespace)
    points.Points.observe = namespace['observe']


def install_evidence(reader):
    original = reader.memory_evidence

    def evidence():
        facts = original()
        drawer = facts.get('top_drawer_interior')
        values = list(reader.joints)
        if drawer and len(values) == 5:
            positions = [float(v['top']) for v in values]
            # Same 5mm static-epoch tolerance as object caching, NOT a change
            # to drawer completion/closing, return or task scoring thresholds.
            drawer['static'] = bool(reader.snapshot['drawers']['top']['open'] and
                                    max(positions) - min(positions) <= .005)
        return facts

    reader.memory_evidence = evidence
