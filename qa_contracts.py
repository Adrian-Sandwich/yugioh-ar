"""contracts.py is the one definition: field lists, detection shape and analyze context, without models."""
import json
import multiprocessing as mp
import threading
from unittest.mock import patch

import numpy as np

import contracts


def main():
    checks = []
    import camera_viewer, live_tracking, vision_onnx, inference_host
    assert camera_viewer.TRACK_FIELDS is contracts.TRACK_FIELDS and live_tracking.IDENTITY_FIELDS is contracts.IDENTITY_FIELDS
    checks.append('viewer and tracker use the contract field lists')

    # The three ways detect() builds a detection all carry the required keys.
    box = {'corners': [[0, 0], [10, 0], [10, 14], [0, 14]], 'score': .9}
    geometry = {'geometry_status': 'contour_refined', 'geometry_iou': .97}
    quad = np.float32([[1, 1], [11, 1], [11, 15], [1, 15]])
    top = [{'card_id': 'a', 'score': .8}, {'card_id': 'b', 'score': .3}]
    made = [vision_onnx.detection(box, geometry, quad, 2, 'a', .8, .5, True, top, 'embedding', acceptance='score'),
            vision_onnx.detection(box, geometry, quad, 0, None, 0., 0., False, [], 'none'),
            vision_onnx.detection(box, {'geometry_status': 'tracked'}, quad, 1, 'a', .8, .5, True, top, 'track', reuse_iou=.9, track_id=7)]
    for d in made: assert not contracts.missing(d, contracts.DETECTION_REQUIRED), contracts.missing(d, contracts.DETECTION_REQUIRED)
    assert made[0]['corners'] == np.roll(quad, -2, axis=0).tolist() and made[0]['rotation'] == 180
    assert made[2]['geometry_iou'] is None and made[2]['track_id'] == 7 and made[0]['acceptance'] == 'score'
    json.dumps(made)  # plain JSON types: they cross a pipe and go to the browser
    checks += ['detections carry every required key', 'corners rolled by the rotation', 'JSON-serialisable']

    # Tracks sent to the browser hold only TRACK_FIELDS.
    track = {'track_id': 5, 'card_id': 'a', 'corners': [[0, 0], [1, 0], [1, 1], [0, 1]], 'top5': top, 'score': .8, 'stable': True}
    sent = camera_viewer.track_payload([track])[0]
    assert set(sent) <= set(contracts.TRACK_FIELDS) and 'top5' not in sent
    checks.append('browser tracks limited to TRACK_FIELDS')

    # inference_host passes the whole analyze context through, and refuses unknown names.
    seen = {}

    class Fake:
        references, cards = [], {}
        def __init__(self, mode): pass
        def analyze_jpeg(self, data, **context): seen.update(context); return {'detections': [], 'context': sorted(context)}
    parent, child = mp.Pipe()
    with patch.object(vision_onnx, 'LiveRecognizer', Fake):
        server = threading.Thread(target=inference_host._serve, args=(child, 'embedding'), daemon=True); server.start()
        assert parent.recv()[0] == 'ready'
        context = {'reuse': [{'card_id': 'a'}], 'verified': [], 'regions': [[[0, 0], [1, 0], [1, 1]]], 'back_zones': [{'id': 'z'}]}
        parent.send(('analyze', {'data': b'jpeg', **context}))
        kind, result = parent.recv(); parent.send(None); server.join(5)
    assert kind == 'ok' and result['context'] == sorted(contracts.ANALYZE_CONTEXT) and seen == context, (kind, result)
    host = inference_host.RemoteRecognizer.__new__(inference_host.RemoteRecognizer)
    try: host.analyze_jpeg(b'jpeg', regoins=[])
    except TypeError as exc: assert 'regoins' in str(exc)
    else: raise AssertionError('a misspelt context name must fail loudly')
    checks += ['analyze context forwarded whole to the child', 'unknown context name rejected']
    print(json.dumps({'status': 'passed', 'checks': checks}))


if __name__ == '__main__':
    main()
