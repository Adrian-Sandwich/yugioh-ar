"""Regression checks for server recovery, bounded OCR work and tracking."""
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import cv2
import numpy as np

from ar_overlay import Tracker
from camera_viewer import Handler, ROOT, Server
from passcode_ocr import PasscodeWorker


from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
def wait_for(predicate, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for worker')


def main():
    image = np.full((800,800,3), 160, np.uint8)
    jpeg = cv2.imencode('.jpg', image)[1].tobytes()
    class Reader:
        calls = 0
        title_calls = 0
        fail_title = False
        def read(self, image, **_):
            self.calls += 1
            return None, False, []
        def read_name(self,image,**_):
            self.title_calls += 1
            if self.fail_title:raise RuntimeError('Controlled title OCR failure')
            return {'status':'unreadable','text':None,'matches':[]}
    reader = Reader()
    worker = PasscodeWorker(lambda: reader)
    # These cases isolate scheduling/resolution with upstream geometry supplied.
    small = {'corners': [[10,10],[110,10],[110,210],[10,210]],'geometry_status':'contour_refined'}
    large = {'corners': [[10,10],[400,10],[400,710],[10,710]],'geometry_status':'contour_refined'}
    try:
        assert worker.submit(jpeg, [small])
        wait_for(lambda: worker.snapshot().get('sequence') == 1)
        item = worker.snapshot()['items'][0]
        assert reader.calls == 0 and item['ocr_skipped'] == 'small_text'
        assert reader.title_calls == 0 and item['name_ocr']['reason'] == 'small_text'
        assert item['crop'] and item['rectified'] and item['status'] == 'unreadable'
        assert item['name_crop'] and item['name_crop_alternative'] and item['name_orientation_uncertain']
        worker.submit(jpeg, [large])
        wait_for(lambda: worker.snapshot().get('sequence') == 2)
        assert reader.calls == 1 and worker.snapshot()['items'][0]['ocr_skipped'] is None
        medium={'corners':[[10,10],[240,10],[240,410],[10,410]],'geometry_status':'contour_refined'}
        worker.submit(jpeg,[medium]);wait_for(lambda:worker.snapshot().get('sequence')==3)
        assert reader.calls==1 and reader.title_calls==2,'Name must work below serial pixel threshold'
        assert worker.snapshot()['items'][0]['name_ocr']['status']=='unreadable'
        reader.fail_title=True;worker.submit(jpeg,[large]);wait_for(lambda:worker.snapshot().get('sequence')==4)
        assert worker.snapshot()['state']=='ready' and worker.snapshot()['items'][0]['name_ocr']['status']=='error'
        assert reader.calls==2,'Title failure must not prevent serial processing'
        reader.fail_title=False
        # Simulate dropped submissions: fairness must follow processed batches,
        # not submission sequence numbers that may jump under load.
        boxes = [{**small, 'name': str(i)} for i in range(8)]
        seen = set()
        for sequence in (9, 13, 17, 21):
            with worker.condition:
                worker.sequence = sequence - 1
            worker.submit(jpeg, boxes)
            wait_for(lambda: worker.snapshot().get('sequence') == sequence)
            seen.update(i['visual_name'] for i in worker.snapshot()['items'])
        assert seen == set(map(str, range(8))), seen
    finally:
        worker.close()
        worker.thread.join(3)
    assert not worker.thread.is_alive() and not worker.submit(jpeg, [small])
    assert not worker.snapshot()['pending']

    def unavailable():
        raise RuntimeError('Controlled model load error')
    broken = PasscodeWorker(unavailable)
    broken.thread.join(3)
    assert broken.snapshot()['state'] == 'unavailable'
    assert not broken.submit(jpeg, [large]) and not broken.snapshot()['pending']
    broken.close()

    tracker = Tracker()
    def detection():
        return {'card_id': 'card-only', **small}
    assert not tracker.update([detection()], now=0)[0]['stable']
    assert tracker.update([detection()], now=1)[0]['stable']
    tracker.update([], now=2)
    assert not tracker.update([detection()], now=3)[0]['stable']

    class Recognizer:
        references = [{}]
        calls = 0
        def analyze_jpeg(self, data):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError('Controlled inference error')
            return {'detections': [], 'processing_ms': 0, 'width':800, 'height':800}
    server = Server(('127.0.0.1',0), Handler)
    server.recognizer = Recognizer()
    server.recognition_lock = threading.Lock()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}/analyze'
    def request(timestamp=None):
        headers={'Content-Type':'image/jpeg'}
        if timestamp is not None: headers['X-Captured-At']=str(timestamp)
        return urlopen(Request(url, data=jpeg, headers=headers), timeout=5)
    try:
        try:
            request()
        except HTTPError as error:
            assert error.code == 500
            error.close()
        else:
            raise AssertionError('Model failure was not an HTTP error')
        source_time=time.time()-5
        with request(source_time) as response:
            result = json.load(response)
        assert result['captured_at']==source_time
        assert result['received_at']-result['captured_at']>=5
        assert result['capture_time_basis']=='client_snapshot_timestamp'
        for timestamp in ('nan', 'bad', time.time()+30, time.time()-120):
            try: request(timestamp)
            except HTTPError as error:
                assert error.code==400
                error.close()
            else: raise AssertionError('Invalid capture timestamp accepted')
        assert result['pipeline_ms']['total'] >= result['pipeline_ms']['recognition']
        assert not server.recognition_lock.locked()
        server.recognition_lock.acquire()
        try:
            try:
                request()
            except HTTPError as error:
                assert error.code == 503
                error.close()
            else:
                raise AssertionError('Concurrent inference admitted')
        finally:
            server.recognition_lock.release()
        assert server.recognizer.calls == 2
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
    result = {'status':'passed', 'checks':['small-text OCR skipped with preview retained',
        'large-text OCR executed', 'batch fairness with dropped jobs', 'worker shutdown',
        'failed initialization rejects jobs', 'tracker accepts card_id without id',
        'absent track loses confirmation', 'HTTP 500 recovery and lock release',
        'busy request bounded and not analyzed', 'pipeline timings',
        'capture time survives inference','invalid and expired capture times rejected']}
    (QA_OUT/'pipeline-core.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
