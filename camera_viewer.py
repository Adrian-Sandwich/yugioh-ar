"""Local Android IP Webcam viewer; Python standard library only for the camera path.

Frames come from the phone's MJPEG stream when available (camera_source.py)
and from single-shot polling otherwise. Every frame advances the corner
tracker (live_tracking.py); `/snapshot` carries the current tracks in an
`X-Tracks` header so the browser draws names and sprites at video rate. The
recognizer runs in a child process (inference_host.py) unless --no-isolate.
With a stream, the server analyzes the newest frame as soon as the previous
analysis ends (AnalysisLoop) and tabs long-poll /analysis; --no-server-loop
returns to browser-paced POST /analyze.
"""

import argparse
import json
import math
import re
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urlsplit
from shared_snapshot import SharedSnapshots
from identity_resolution import IDENTITIES
from contracts import TRACK_FIELDS  # noqa: F401  (camera_viewer.TRACK_FIELDS)
# The analysis path lives in pipeline.py; these names stay importable from here.
from pipeline import (DIAGNOSTIC_HOLD_S, AnalysisLoop, auto_sprite_url, open_camera, run_analysis,  # noqa: F401
                      snapshot, snapshot_record, track_payload)

ROOT = Path(__file__).resolve().parent


def camera_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise argparse.ArgumentTypeError("Usa una URL http:// o https:// valida")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("La URL debe ser la direccion base de la camara")
    return value.rstrip("/")


class Server(ThreadingHTTPServer):
    """The lab's state, shared by the HTTP handlers and pipeline.py. main() fills it from the command
    line; tests set what they need. None means the feature is off."""
    daemon_threads = True

    def __init__(self,*args,**kwargs):
        self.camera=None                      # phone base URL (IP Webcam), e.g. http://192.168.1.18:8080
        self.fixture=None                     # Path of a saved JPEG served instead of the camera (demo)
        self.snapshots=SharedSnapshots()      # one phone request shared by concurrent /snapshot calls
        self.stream=None                      # camera_source.MjpegSource: newest frame of the MJPEG stream
        self.recognizer=None                  # inference_host.RemoteRecognizer, vision_onnx.LiveRecognizer or recognition.*
        self.recognition_lock=threading.Lock()  # one analysis at a time
        self.mode='single-reference'          # backend name shown by /config
        self.tracker=None                     # ar_overlay.Tracker: marks detections stable after two analyses
        self.live_tracker=None                # live_tracking.LiveTracker: corners at video rate between analyses
        self.last_tracked_at=0.               # capture time of the last frame given to live_tracker
        self.overlay=None                     # ar_overlay.SpriteOverlay: /sprite and /cutout pictures
        self.passcode_worker=None             # passcode_ocr.PasscodeWorker: passcode, title, set code, art check
        self.analysis_loop=None               # pipeline.AnalysisLoop: server-paced analyses for /analysis
        self.table=None                       # table_duel.TableDuel: playmat, zones and the duel
        self.diagnostic_seen=-1e9             # monotonic time of the diagnostic page's last /analysis poll
        super().__init__(*args,**kwargs)

    def handle_error(self,request,client_address):
        # Keep-alive: a tab that closes or reloads drops its idle connection; not an error worth a traceback.
        import sys
        if isinstance(sys.exc_info()[1],(ConnectionResetError,ConnectionAbortedError,BrokenPipeError)):return
        super().handle_error(request,client_address)


class Handler(BaseHTTPRequestHandler):
    # Keep-alive: a tab asks for /snapshot ~15 times a second; HTTP/1.0 opened a connection and a
    # thread for each. Every reply carries Content-Length (reply()).
    protocol_version = 'HTTP/1.1'

    def internal_error(self):
        traceback.print_exc()
        try:
            self.reply(500, b'Analysis failed; see server log', 'text/plain')
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def reply(self, status, body, content_type, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if status>=400:
            # An error may leave a request body unread: close rather than misread it as the next request.
            self.send_header("Connection","close");self.close_connection=True
        for key,value in (headers or {}).items():
            self.send_header(key,str(value))
        self.end_headers()
        self.wfile.write(body)

    # GET routes: exact paths, then prefixes (first match). Each handler replies itself.
    ROUTES = {'/': 'page_camera', '/duelo': 'page_duel', '/pose-annotator': 'page_pose', '/snapshot': 'get_snapshot',
              '/tracks': 'get_tracks', '/config': 'get_config', '/passcodes': 'get_passcodes', '/download-status': 'get_download_status',
              '/analyze': 'analyze', '/analysis': 'latest_analysis', '/duel/history': 'get_duel_history', '/card-image': 'get_card_image',
              '/playmat': 'get_table', '/duel': 'get_table', '/card-info': 'get_card_info',
              '/camera.js': 'get_script', '/duel.js': 'get_script', '/ar.js': 'get_script', '/common.js': 'get_script'}
    PREFIXES = (('/fx/', 'get_fx'), ('/cutout/', 'get_cutout'), ('/sprite/', 'get_sprite'), ('/playmat/print/', 'get_print'))

    def do_GET(self):
        route = urlsplit(self.path).path
        try:
            name = self.ROUTES.get(route) or next((n for prefix, n in self.PREFIXES if route.startswith(prefix)), None)
            if name is None: return self.reply(404, b"Not found", "text/plain")
            getattr(self, name)(route) if name not in ('analyze', 'latest_analysis') else getattr(self, name)()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            try:
                self.reply(502, str(exc).encode(), "text/plain; charset=utf-8")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        except Exception:
            self.internal_error()

    def query(self):
        """Query string as {name: first value}, URL-decoded."""
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}

    def json_reply(self, body, status=200):
        self.reply(status, json.dumps(body, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

    # --- pages and static files
    def page_camera(self, route): self.reply(200, (ROOT / 'web/camera.html').read_bytes(), 'text/html; charset=utf-8')
    # Duel view: video, board and duel panel only; / stays the diagnostic viewer.
    def page_duel(self, route): self.reply(200, (ROOT / 'web/duel.html').read_bytes(), 'text/html; charset=utf-8')
    def page_pose(self, route): self.reply(200, (ROOT / 'web/pose_annotator.html').read_bytes(), 'text/html; charset=utf-8')
    def get_script(self, route): self.reply(200, (ROOT / 'web' / route[1:]).read_bytes(), 'text/javascript; charset=utf-8')

    def get_fx(self, route):
        # Effect assets of the duel view (web/fx: sprite strips and their frame data).
        if not re.fullmatch(r'/fx/[\w.-]+\.(png|json)', route) or not (ROOT / 'web' / route[1:]).is_file():
            return self.reply(404, b"Not found", "text/plain")
        self.reply(200, (ROOT / 'web' / route[1:]).read_bytes(), 'image/png' if route.endswith('.png') else 'application/json')

    # --- camera, tracks and sprites
    def get_snapshot(self, route):
        data, captured_at, basis = self.get_snapshot_record()
        headers = {'X-Captured-At': captured_at, 'X-Capture-Time-Basis': basis}
        live = self.server.live_tracker
        if live is not None:
            headers['X-Tracks'] = json.dumps(track_payload(live.snapshot()), ensure_ascii=True, separators=(',', ':'))
        self.reply(200, data, "image/jpeg", headers)

    def get_tracks(self, route):
        live = self.server.live_tracker
        self.reply(200, json.dumps({'tracks': track_payload(live.snapshot()) if live else [], 'now': time.time(),
                                    'tracking_ms': live.last_update_ms if live else None, 'frames': live.frame_count if live else 0}).encode(), 'application/json')

    def get_cutout(self, route):
        overlay = self.server.overlay
        # The page URL-encodes the reference id (tdoane:sprite:...); decode it back.
        data = overlay.cutout_png(unquote(route[len('/cutout/'):])) if overlay else None
        if data is None: self.reply(404, b'No sprite', 'text/plain')
        else: self.reply(200, data, 'image/png', {'Cache-Control': 'max-age=3600'})

    def get_sprite(self, route):
        overlay = self.server.overlay
        if overlay: overlay.refresh_auto(every=0)  # a new ?v= must never get the old picture
        data = overlay.sprite_png(route[len('/sprite/'):]) if overlay else None
        if data is None: self.reply(404, b'No sprite', 'text/plain')
        else: self.reply(200, data, 'image/png', {'Cache-Control': 'max-age=3600'})

    # --- status
    def get_config(self, route):
        server = self.server; recognizer = server.recognizer; stream = server.stream
        self.reply(200, json.dumps({"camera": server.camera, "recognition": recognizer is not None,
            "mode": server.mode, "offline": bool(server.fixture),
            "experimental": server.mode in ('draw2', 'embedding'),
            "ar": server.overlay is not None,
            "passcode_ocr": server.passcode_worker is not None,
            "identity_resolution": IDENTITIES.info(),
            "live_tracking": server.live_tracker is not None,
            "stream": stream.status() if stream else None,
            "server_loop": server.analysis_loop.status() if server.analysis_loop else None,
            "inference": recognizer.status() if hasattr(recognizer, 'status') else {'isolated': False},
            "references": len(recognizer.references) if recognizer else 0}).encode(), "application/json")

    def get_passcodes(self, route):
        worker = self.server.passcode_worker
        self.reply(200, json.dumps(worker.snapshot() if worker else {'state': 'disabled', 'items': []}).encode(), 'application/json')

    def get_download_status(self, route):
        path = ROOT / '.runtime/download-watch.json'
        payload = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'watch_state': 'not_started'}
        self.reply(200, json.dumps(payload).encode(), 'application/json')

    # --- cards and duel
    def get_card_image(self, route):
        # Card picture for the duel view's "Carta en juego" panel (best linked image, 360 px wide).
        data = card_image(self.query().get('id', ''))
        if data is None: self.reply(404, b'No image', 'text/plain')
        else: self.reply(200, data, 'image/jpeg')

    def get_card_info(self, route):
        from card_info import card_sheet
        sheet = card_sheet(self.query().get('id', ''))
        if sheet is None: self.reply(404, b'Unknown card', 'text/plain')
        else: self.json_reply(sheet)

    def get_table(self, route):
        table = self.server.table
        if table is None: return self.reply(404, b'Duel disabled (live camera only)', 'text/plain')
        self.json_reply(table.overlay() if route == '/playmat' else table.view())

    def get_duel_history(self, route):
        table = self.server.table
        self.json_reply(table.history() if table else [])

    def get_print(self, route):
        # Printable templates; generated on first request. Only known names are served.
        name = route.rsplit('/', 1)[-1]
        allowed = {f'tapete-jugador{p}{s}' for p in (1, 2) for s in ('.png', '-una-pieza.pdf', '-hojas-carta.pdf')}
        if name not in allowed: return self.reply(404, b'Not found', 'text/plain')
        path = ROOT / 'data/playmat/print' / name
        if not path.exists():
            import subprocess, sys
            subprocess.run([sys.executable, str(ROOT / 'playmat_print.py')], cwd=ROOT, check=True, capture_output=True)
        self.reply(200, path.read_bytes(), 'application/pdf' if name.endswith('.pdf') else 'image/png')

    def log_message(self, fmt, *args):
        if args and str(args[1] if len(args) > 1 else "") in ("200","503"):
            return
        super().log_message(fmt, *args)

    def do_POST(self):
        route=urlsplit(self.path).path
        if route in ('/playmat','/duel'):
            return self.table_post(route)
        if route!='/analyze':
            return self.reply(404,b'Not found','text/plain')
        try:
            if self.headers.get('Content-Type','').split(';')[0]!='image/jpeg':
                return self.reply(415,b'Expected image/jpeg','text/plain')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16*1024*1024:
                return self.reply(413,b'Invalid image size','text/plain')
            self.connection.settimeout(10)
            data=self.rfile.read(length)
            if len(data)!=length or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
                return self.reply(400,b'Invalid JPEG','text/plain')
            captured_at=None
            if self.headers.get('X-Captured-At') is not None:
                try: captured_at=float(self.headers['X-Captured-At'])
                except ValueError: return self.reply(400,b'Invalid capture timestamp','text/plain')
                age=time.time()-captured_at
                if not math.isfinite(captured_at) or not -1<=age<=60:
                    return self.reply(400,b'Invalid or expired capture timestamp','text/plain')
            self.analyze(data,captured_at)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
            pass
        except (ValueError,OSError) as exc:
            try: self.reply(502,str(exc).encode(),'text/plain; charset=utf-8')
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
        except Exception:
            self.internal_error()

    def analyze(self,data=None,captured_at=None):
        if self.server.recognizer is None:
            return self.reply(503,b'Recognition disabled','text/plain')
        # A short bounded wait lets multiple tabs take turns instead of one
        # polling tab repeatedly missing the small gap between other requests.
        result=run_analysis(self.server,data,captured_at,lock_timeout=2)
        if result is None:
            return self.reply(503,b'Recognition busy','text/plain')
        # Socket writes happen after run_analysis released the inference lock (slow/disconnected tab).
        self.reply(200,json.dumps(result).encode(),'application/json')

    def teach_back(self,table,payload):
        """"Enseñar reverso": the newest frame's crop of the clicked zone becomes a card back
        reference (a sleeve); the recognizer process picks it up on its next analysis."""
        import card_backs,cv2,numpy as np
        if payload['type']=='forget_backs': return {'forgotten':card_backs.forget_taught(),**card_backs.summary()}
        polygon=table.zone_polygon(int(payload['player']),payload['zone'])
        if polygon is None: raise ValueError('Esa zona no está en el tablero calibrado')
        data=self.get_snapshot_record()[0]
        image=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR) if data else None
        if image is None: raise ValueError('No hay imagen de la cámara')
        return {'taught':card_backs.teach(image,polygon,int(payload['player']),payload['zone'])['id'],**card_backs.summary()}

    def table_post(self,route):
        """Calibration (/playmat) or a player's decision (/duel); errors come back as 400 with the reason."""
        from duel_engine import DuelError
        table=self.server.table
        try:
            if table is None: return self.reply(404,b'Duel disabled (live camera only)','text/plain')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536: return self.reply(413,b'Invalid body size','text/plain')
            payload=json.loads(self.rfile.read(length))
            if route=='/playmat' and payload.get('preview'): body=table.preview(payload['mode'],payload.get('virtual'),payload['image_size'])
            elif route=='/playmat': body=table.calibrate(payload['mode'],payload.get('mats',[]),payload.get('image_size'),payload.get('virtual'))
            elif payload.get('type') in ('teach_back','forget_backs'): body={'result':self.teach_back(table,payload),'duel':table.view()}
            else: body={'result':table.act(payload),'duel':table.view()}
            self.reply(200,json.dumps(body,ensure_ascii=False).encode(),'application/json; charset=utf-8')
        except (DuelError,ValueError,KeyError,TypeError) as exc:
            try: self.reply(400,json.dumps({'error':str(exc)},ensure_ascii=False).encode(),'application/json; charset=utf-8')
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
        except Exception: self.internal_error()

    def latest_analysis(self):
        """Long poll: the first server-loop analysis newer than `after`, or 204 after two seconds."""
        loop=self.server.analysis_loop
        if loop is None:
            return self.reply(404,b'Server loop disabled','text/plain')
        query=self.query()
        try: after=int(query.get('after','-1'))
        except ValueError: return self.reply(400,b'Invalid sequence','text/plain')
        # The duel view says so (view=duel); any other page is the diagnostic viewer, which must see
        # every card, so while it watches the analysis is not limited to the board's zones.
        if query.get('view')!='duel': self.server.diagnostic_seen=time.monotonic()
        # The duel view draws over its own video: it gets the result without the analysed JPEG (~330 KB).
        body=loop.wait_newer(after,timeout=2.,lite=query.get('view')=='duel')
        if body is None: return self.reply(204,b'','application/json')
        self.reply(200,body,'application/json')

    def get_snapshot_record(self):
        return snapshot_record(self.server)


from functools import lru_cache


@lru_cache(maxsize=256)
def card_image(card_id):
    """JPEG of the widest linked or approved card image of an identity, 360 px wide, or None."""
    if not card_id: return None
    import cv2,numpy as np
    from catalog import connect,EFFECTIVE,PILOT_REFS,asset_path
    with connect() as conn:
        row=conn.execute('SELECT r.* FROM ('+EFFECTIVE+') r WHERE r.effective_card_id=? AND '+PILOT_REFS+' ORDER BY r.width DESC LIMIT 1',(card_id,)).fetchone()
    if row is None: return None
    image=cv2.imdecode(np.frombuffer(asset_path(row).read_bytes(),np.uint8),cv2.IMREAD_COLOR)
    if image is None: return None
    image=cv2.resize(image,(360,round(image.shape[0]*360/image.shape[1])),interpolation=cv2.INTER_AREA)
    return cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,88])[1].tobytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=camera_url, default="http://192.168.1.18:8080")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true", help="Fetch three JPEG frames and exit")
    parser.add_argument("--recognize", action="store_true", help="Enable recognition from the local reference catalog")
    parser.add_argument('--pilot',action='store_true',help='Use the reviewed pilot catalog with multi-card matching')
    parser.add_argument('--ar',action='store_true',help='Serve sprites for stable detections; the browser warps them')
    parser.add_argument('--image',type=Path,help='Offline fixture image; explicitly labelled in the viewer')
    parser.add_argument('--backend',choices=['sift','draw2','embedding'],default='sift',help='ONNX choices are experimental and require .venv-eval')
    parser.add_argument('--no-passcode',action='store_true',help='Disable asynchronous passcode crop/OCR')
    parser.add_argument('--no-stream',action='store_true',help='Poll /shot.jpg instead of reading the MJPEG /video stream')
    parser.add_argument('--no-isolate',action='store_true',help='Run the ONNX recognizer inside this process instead of a restartable child')
    parser.add_argument('--no-tracking',action='store_true',help='Disable corner tracking between analyses')
    parser.add_argument('--no-server-loop',action='store_true',help='Let the browser pace recognition with POST /analyze instead of the server analyzing the newest stream frame')
    args = parser.parse_args()
    if args.check:
        for i in range(3):
            start = time.monotonic()
            data = snapshot(args.camera)
            print(f"Frame {i + 1}: JPEG completo, {len(data)} bytes, {(time.monotonic() - start) * 1000:.0f} ms", flush=True)
        return
    recognizer = None
    if args.backend!='sift':
        mode='classifier' if args.backend=='draw2' else 'embedding'
        if args.no_isolate:
            from vision_onnx import LiveRecognizer
            recognizer=LiveRecognizer(mode)
        else:
            from inference_host import RemoteRecognizer
            recognizer=RemoteRecognizer(mode)
    elif args.recognize or args.pilot:
        from recognition import Recognizer,PilotRecognizer
        recognizer = PilotRecognizer() if args.pilot else Recognizer()
    server = Server(("127.0.0.1", args.port), Handler)
    server.camera = args.camera
    server.recognizer = recognizer
    server.mode=args.backend if args.backend!='sift' else ('sift-pilot' if args.pilot else 'single-reference')
    server.fixture=args.image.resolve() if args.image else None
    if server.fixture:
        data=server.fixture.read_bytes()
        if not data.startswith(b'\xff\xd8'):
            parser.error('--image requiere una captura JPEG')
    if recognizer:
        from ar_overlay import Tracker,SpriteOverlay
        server.tracker=Tracker()
        server.overlay=SpriteOverlay() if args.ar and (args.pilot or args.backend!='sift') else None
        if not args.no_passcode:
            from passcode_ocr import PasscodeWorker
            server.passcode_worker=PasscodeWorker()
        if not args.no_tracking:
            from live_tracking import LiveTracker
            server.live_tracker=LiveTracker()
    if not args.no_stream and server.fixture is None:
        from camera_source import MjpegSource
        live=server.live_tracker
        server.stream=MjpegSource(args.camera,on_frame=(lambda frame,captured:live.update(frame,captured)) if live else None)
    # Only with a live stream: a fixture has a single frame and polling cameras keep the browser-paced path.
    if recognizer and server.stream and not args.no_server_loop:
        server.analysis_loop=AnalysisLoop(server)
    # Duel on the playmat: live camera with tracking only (a fixture never changes).
    if recognizer and server.fixture is None and server.live_tracker is not None:
        from table_duel import TableDuel
        from card_info import card_sheet
        server.table=TableDuel(sheet=card_sheet)
    print(f"Visor: http://127.0.0.1:{args.port} | Camara: {args.camera}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server.analysis_loop: server.analysis_loop.close()
        if server.stream: server.stream.close()
        if server.passcode_worker: server.passcode_worker.close()
        if hasattr(recognizer,'close'): recognizer.close()
        server.server_close()


if __name__ == "__main__":
    main()
