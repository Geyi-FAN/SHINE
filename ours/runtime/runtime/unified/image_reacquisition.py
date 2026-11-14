"""Fresh same-view typed-point reacquisition; history guides search only."""
import json
import math


def reacquire(proc, image, frame, reference, previous, det_threshold=.1, keypoint_threshold=.1):
    if not reference or reference.get('time_source') != 'current' or reference.get('keypoint') != 'K1':
        return [], dict(reason='not_current_grasp_reference')
    if reference.get('entity') not in ('bowl', 'cheese', 'wine_bottle', 'plate') or not previous:
        return [], dict(reason='no_typed_visual_search_history')
    if not 0 < frame - previous['frame'] <= 48:
        return [], dict(reason='visual_search_history_expired')
    yx = previous.get('yx224', [])
    if len(yx) != 2 or not all(math.isfinite(v) and 0 <= v <= 223 for v in yx):
        return [], dict(reason='invalid_visual_search_prior')
    y, x = [(value + .5) / .875 - .5 for value in yx]
    candidates, trials, seconds = [], [], 0.
    for size in (128, 192):
        left, top = [max(0, min(256-size, int(round(v))-size//2)) for v in (x, y)]
        roi = [left, top, left+size, top+size]
        proc.stdin.write(json.dumps(dict(image=str(image), frame=frame, roi=roi,
                                        entity=reference['entity']))+'\n')
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                raise RuntimeError('YOLO multiscale worker exited')
            try:
                reply = json.loads(line)
            except ValueError:
                continue
            if isinstance(reply, dict) and ('points' in reply or 'error' in reply):
                break
        if 'error' in reply:
            raise RuntimeError(reply['error'])
        if reply.get('frame') != frame:
            raise RuntimeError('YOLO multiscale response frame mismatch')
        seconds += reply.get('seconds', 0.)
        valid = []
        for point in reply['points']:
            coords = point.get('yx224', [])
            if (point.get('entity') != reference['entity'] or point.get('keypoint') != 'K1'
                    or point.get('det_confidence', 0) < det_threshold
                    or point.get('keypoint_confidence', 0) < keypoint_threshold
                    or len(coords) != 2 or not all(math.isfinite(v) and 0 <= v <= 223 for v in coords)):
                continue
            valid.append(dict(point, roi_MAIN256=roi, source_frame=frame,
                              roi_reacquisition=True, multiscale_reacquisition=True))
        trials.append(dict(roi_MAIN256=roi, valid_candidates=len(valid)))
        candidates.append(valid)
    agreed = [a for a in candidates[0] for b in candidates[1]
              if math.dist(a['yx224'], b['yx224']) <= 8.]
    agreed += [b for b in candidates[1] for a in candidates[0]
               if math.dist(a['yx224'], b['yx224']) <= 8.]
    selected = [max(agreed, key=lambda p: (p['det_confidence'], p['keypoint_confidence']))] if agreed else []
    return selected, dict(source_frame=frame, search_reference_frame=previous['frame'],
                          trials=trials, returned_points=len(selected), seconds=seconds,
                          agreement_radius_px=8., oracle_pixel_used=False,
                          cached_coordinate_used_as_output=False)
