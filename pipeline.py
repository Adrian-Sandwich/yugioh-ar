"""The live analysis path, without HTTP: camera frames, one recognizer pass and what follows it.

camera_viewer.py serves pages and routes requests; everything that runs per analysis lives here:

    snapshot_record(server)    newest JPEG: fixture, MJPEG stream, or a single shot from the phone
    run_analysis(server, ...)  recognizer (with its context) -> OCR job -> tracking -> duel -> sprite URLs
    AnalysisLoop(server)       analyses the newest stream frame back to back while some page asks

`server` is camera_viewer.Server: its attributes (camera, recognizer, live_tracker, table, ...) are
declared, with what each one is, in Server.__init__.
"""
import base64
import json
import threading
import time
import traceback
from urllib.request import ProxyHandler, Request, build_opener

import settings
from contracts import TRACK_FIELDS
from identity_resolution import IDENTITIES, normalize_detection

ROOT = settings.ROOT
AUTO_SPRITES = settings.AUTO_SPRITES
# Seconds after the diagnostic viewer's last poll during which the analysis covers the whole frame.
DIAGNOSTIC_HOLD_S = 5.


# --- camera ------------------------------------------------------------------------------------
def open_camera(base, endpoint):
    # The phone is on the local network; do not route it through HTTP proxies.
    return build_opener(ProxyHandler({})).open(Request(base + endpoint, headers={'Cache-Control': 'no-cache'}), timeout=8)


def snapshot(base):
    with open_camera(base, "/shot.jpg?t=" + str(time.time_ns())) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024 or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("La camara no devolvio un JPEG completo")
    return data


def snapshot_record(server):
    """(jpeg, captured_at, basis): fixture, MJPEG stream, or single-shot polling."""
    fixture, stream = server.fixture, server.stream
    if fixture is None and stream is not None:
        try:
            data, captured = stream.latest()
            return data, captured, 'stream_frame_receipt'
        except OSError:
            pass  # Stale or disconnected stream: poll a single frame instead.
    data, captured = server.snapshots.get((server.camera, str(fixture)),
                                          lambda: fixture.read_bytes() if fixture else snapshot(server.camera))
    live = server.live_tracker
    if live is not None and captured > server.last_tracked_at:
        server.last_tracked_at = captured; live.update(data, captured)
    return data, captured, 'server_snapshot_request'


# --- what the browser gets ------------------------------------------------------------------------
def auto_sprite_url(ref):
    """Automatic sprites can change while the viewer runs (review_server.py --apply, auto_cutout.py
    build, both ending by replacing data/auto-sprites/index.json): the version in the URL makes the
    page fetch the new picture instead of reusing the one it already holds."""
    try: version = (AUTO_SPRITES / 'index.json').stat().st_mtime_ns
    except OSError: version = 0
    return '/sprite/' + ref + '?v=%d' % version


def track_payload(tracks):
    """Compact, ASCII-safe track list for a response header or JSON body."""
    out = []
    for t in tracks:
        item = {k: t.get(k) for k in TRACK_FIELDS if k in t}
        item['corners'] = [[round(float(x), 1), round(float(y), 1)] for x, y in t['corners']]
        if (item.get('sprite_ref') or '').startswith('auto:'): item['sprite_url'] = auto_sprite_url(item['sprite_ref'])
        out.append(item)
    return out


def diagnostic_watching(server):
    """The diagnostic page (/) polled recently: it shows every card, so the whole frame is analysed."""
    return time.monotonic() - server.diagnostic_seen < DIAGNOSTIC_HOLD_S


# --- one analysis --------------------------------------------------------------------------------
def analysis_context(server, captured_at):
    """contracts.ANALYZE_CONTEXT for this frame: tracks to reuse, OCR/art evidence, duel zones."""
    from vision_onnx import REUSE_MAX_AGE_S
    live, worker, table = server.live_tracker, server.passcode_worker, server.table
    return {'reuse': live.reuse_candidates(captured_at, REUSE_MAX_AGE_S) if live else (),
            'verified': worker.verified() if worker and hasattr(worker, 'verified') else (),
            # With a duel board set, cards outside its field zones are not analysed at all, unless the
            # diagnostic page is watching (it shows every card on the table).
            'regions': table.field_regions() if table is not None and not diagnostic_watching(server) else None,
            # Face-down cards: zones without a detected card are compared with the card back (card_backs).
            'back_zones': table.back_zones() if table is not None else None}


def submit_ocr(server, result, data, captured_at):
    """Every candidate box to the OCR worker, with what the recognizer thought of it."""
    worker = server.passcode_worker
    worker.previews = diagnostic_watching(server) if getattr(server.recognizer, 'supports_context', False) else True
    named = {tuple(map(tuple, d['corners'])): d for d in result['detections']}
    boxes = []
    for d in result.get('candidates', result['detections']):
        visual = named.get(tuple(map(tuple, d['corners'])), {})
        boxes.append({'corners': d['corners'], 'visual_card_id': visual.get('card_id'), 'name': visual.get('name'),
                      'source_visual_card_id': visual.get('source_card_id', visual.get('card_id')),
                      'candidate_ids': [t['card_id'] for t in d.get('top5', []) if t.get('card_id')][:5],
                      'geometry_status': d.get('geometry_status'), 'geometry_iou': d.get('geometry_iou')})
    worker.submit(data, boxes, captured_at)


def feed_duel(server, result, data, captured_at):
    """Confirmed tracks to the duel; a duel bug must never stop recognition (logged, then ignored)."""
    table, live = server.table, server.live_tracker
    try:
        if table.mode == 'printed':
            # Printed mats: find their markers in this very frame (~7 ms at 1080p).
            import cv2, numpy as np
            grey = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_GRAYSCALE)
            if grey is not None: table.see_markers(grey, captured_at)
        # Only stable tracks: provisional identities could be wrong.
        table.feed([t for t in live.snapshot() if t.get('stable')], backs=result.get('backs'))
    except Exception: traceback.print_exc()


def run_analysis(server, data=None, captured_at=None, lock_timeout=-1):
    """One recognizer pass plus OCR submission, tracking and the duel; None if the lock was busy.

    Shared by POST /analyze (a browser-chosen frame) and the server loop (the newest stream frame).
    """
    started = time.perf_counter()
    received_at = time.time()
    capture_basis = 'client_snapshot_timestamp' if captured_at is not None else 'server_receive_time'
    if data is not None and captured_at is None: captured_at = received_at
    if not server.recognition_lock.acquire(timeout=lock_timeout):
        return None
    acquired = time.perf_counter()

    def report_stall():
        import faulthandler
        path = ROOT / '.runtime' / f'camera-{server.server_port}-stall.log'
        path.parent.mkdir(exist_ok=True)
        with path.open('w') as log:
            faulthandler.dump_traceback(file=log, all_threads=True)
    watchdog = threading.Timer(20, report_stall)
    watchdog.daemon = True
    watchdog.start()
    try:
        if data is None:
            data, captured_at, capture_basis = snapshot_record(server)
        inference_started = time.perf_counter()
        recognizer = server.recognizer
        if getattr(recognizer, 'supports_context', False):
            result = recognizer.analyze_jpeg(data, **analysis_context(server, captured_at))
        else:
            result = recognizer.analyze_jpeg(data)  # legacy SIFT recognizer (recognition.py)
        result['detections'] = [normalize_detection(d) for d in result['detections']]
        if 'candidates' in result: result['candidates'] = [normalize_detection(d) for d in result['candidates']]
        result['identity_resolution'] = IDENTITIES.info()
        inference_finished = time.perf_counter()
        if server.passcode_worker: submit_ocr(server, result, data, captured_at)
        if server.tracker: result['detections'] = server.tracker.update(result['detections'])
        live = server.live_tracker
        if live is not None:
            # Sprites and names follow these corners at video rate from here on.
            live.sync(result['detections'], captured_at)
            result['tracks'] = track_payload(live.snapshot())
            if server.table is not None: feed_duel(server, result, data, captured_at)
        if server.overlay is not None:
            for d in result['detections']:
                if d.get('sprite_ref'):
                    d['sprite_url'] = auto_sprite_url(d['sprite_ref']) if d['sprite_ref'].startswith('auto:') else '/sprite/' + d['sprite_ref']
        result['image'] = 'data:image/jpeg;base64,' + base64.b64encode(data).decode('ascii')
        result.update(captured_at=captured_at, capture_time_basis=capture_basis,
                      received_at=received_at, completed_at=time.time())
        result['pipeline_ms'] = {
            'lock_wait': round((acquired - started) * 1000, 1),
            'capture': round((inference_started - acquired) * 1000, 1),
            'recognition': round((inference_finished - inference_started) * 1000, 1),
            'postprocess': round((time.perf_counter() - inference_finished) * 1000, 1),
            'total': round((time.perf_counter() - started) * 1000, 1)}
        return result
    finally:
        watchdog.cancel()
        server.recognition_lock.release()


class AnalysisLoop:
    """Analyze the newest stream frame as soon as the previous analysis ends.

    The browser no longer paces recognition: every tab long-polls
    /analysis?after=<seq> and receives the same result. The loop idles while no
    tab has asked for an analysis in the last `idle_after` seconds, so an
    unwatched viewer does not keep the GPU busy.
    """
    def __init__(self, server, idle_after=5.):
        self.server = server; self.idle_after = idle_after
        self.condition = threading.Condition(); self.sequence = 0; self.body = None; self.body_lite = None
        self.last_client = 0.; self.last_captured = 0.; self.errors = 0; self.closed = False
        self.thread = threading.Thread(target=self.run, name='analysis-loop', daemon=True); self.thread.start()

    def wait_newer(self, after, timeout, lite=False):
        with self.condition:
            self.last_client = time.monotonic(); self.condition.notify_all()
            # A tab that outlived a server restart asks for a sequence this process never
            # reached: treat it as new instead of letting it wait forever.
            if after > self.sequence: after = -1
            ready = lambda: self.body is not None and self.sequence > after
            if not self.condition.wait_for(lambda: ready() or self.closed, timeout): return None
            return (self.body_lite if lite else self.body) if ready() else None

    def run(self):
        while not self.closed:
            with self.condition:
                if time.monotonic() - self.last_client > self.idle_after:
                    self.condition.wait(.5); continue
            try:
                data, captured_at, basis = snapshot_record(self.server)
                if captured_at <= self.last_captured:
                    time.sleep(.005); continue  # same frame as the last analysis
                self.last_captured = captured_at
                result = run_analysis(self.server, data, captured_at)
                result['capture_time_basis'] = basis
                # Only the diagnostic viewer paints the analysed JPEG: without it watching, skip the base64 copy.
                if not diagnostic_watching(self.server): result.pop('image', None)
                self.errors = 0
            except Exception as exc:
                # A camera or inference failure is reported to the tabs, then retried.
                self.errors += 1; traceback.print_exc()
                result = {'error': str(exc) or type(exc).__name__, 'detections': [], 'captured_at': time.time()}
                time.sleep(min(2., .2 * self.errors))
            with self.condition:
                self.sequence += 1; result['sequence'] = self.sequence
                self.body = json.dumps(result).encode()
                self.body_lite = json.dumps({k: v for k, v in result.items() if k != 'image'}).encode() if 'image' in result else self.body
                self.condition.notify_all()

    def status(self):
        return {'sequence': self.sequence, 'watching': time.monotonic() - self.last_client <= self.idle_after, 'errors': self.errors}

    def close(self):
        with self.condition:
            self.closed = True; self.condition.notify_all()
