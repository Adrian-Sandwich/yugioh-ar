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
import base64
import json
import math
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from shared_snapshot import SharedSnapshots
from identity_resolution import IDENTITIES,normalize_detection

ROOT = Path(__file__).resolve().parent
TRACK_FIELDS=('track_id','card_id','name','sprite_ref','corners','stable','verified_at','tracked_at','acceptance','inliers','frames')


def camera_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise argparse.ArgumentTypeError("Usa una URL http:// o https:// valida")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("La URL debe ser la direccion base de la camara")
    return value.rstrip("/")


def open_camera(base, endpoint):
    # The phone is on the local network; do not route it through HTTP proxies.
    return build_opener(ProxyHandler({})).open(Request(base + endpoint,headers={'Cache-Control':'no-cache'}), timeout=8)


def snapshot(base):
    with open_camera(base, "/shot.jpg?t="+str(time.time_ns())) as response:
        data = response.read(16 * 1024 * 1024 + 1)
    if len(data) > 16 * 1024 * 1024 or not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise ValueError("La camara no devolvio un JPEG completo")
    return data


def track_payload(tracks):
    """Compact, ASCII-safe track list for a response header or JSON body."""
    out=[]
    for t in tracks:
        item={k:t.get(k) for k in TRACK_FIELDS if k in t}
        item['corners']=[[round(float(x),1),round(float(y),1)] for x,y in t['corners']]
        out.append(item)
    return out


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self,*args,**kwargs):
        self.snapshots=SharedSnapshots()
        self.tracker=None;self.live_tracker=None;self.stream=None;self.overlay=None;self.passcode_worker=None
        self.recognizer=None;self.fixture=None;self.mode='single-reference';self.last_tracked_at=0.;self.analysis_loop=None;self.table=None
        super().__init__(*args,**kwargs)


class Handler(BaseHTTPRequestHandler):
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
        for key,value in (headers or {}).items():
            self.send_header(key,str(value))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlsplit(self.path).path
        try:
            if route == "/":
                self.reply(200, (ROOT / "web" / "camera.html").read_bytes(), "text/html; charset=utf-8")
            elif route in ('/camera.js','/duel.js','/ar.js'):
                self.reply(200,(ROOT/'web'/route[1:]).read_bytes(),'text/javascript; charset=utf-8')
            elif route == '/duelo':
                # Duel view: video, board and duel panel only; / stays the diagnostic viewer.
                self.reply(200,(ROOT/'web/duel.html').read_bytes(),'text/html; charset=utf-8')
            elif route == '/pose-annotator':
                self.reply(200,(ROOT/'web/pose_annotator.html').read_bytes(),'text/html; charset=utf-8')
            elif route == "/snapshot":
                data,captured_at,basis=self.get_snapshot_record()
                headers={'X-Captured-At':captured_at,'X-Capture-Time-Basis':basis}
                live=getattr(self.server,'live_tracker',None)
                if live is not None:
                    headers['X-Tracks']=json.dumps(track_payload(live.snapshot()),ensure_ascii=True,separators=(',',':'))
                self.reply(200, data, "image/jpeg", headers)
            elif route == '/tracks':
                live=getattr(self.server,'live_tracker',None)
                self.reply(200,json.dumps({'tracks':track_payload(live.snapshot()) if live else [],'now':time.time(),
                    'tracking_ms':live.last_update_ms if live else None,'frames':live.frame_count if live else 0}).encode(),'application/json')
            elif route.startswith('/cutout/'):
                overlay=getattr(self.server,'overlay',None)
                # The page URL-encodes the reference id (tdoane:sprite:...); decode it back.
                from urllib.parse import unquote
                data=overlay.cutout_png(unquote(route[len('/cutout/'):])) if overlay else None
                if data is None: self.reply(404,b'No sprite','text/plain')
                else: self.reply(200,data,'image/png',{'Cache-Control':'max-age=3600'})
            elif route.startswith('/sprite/'):
                overlay=getattr(self.server,'overlay',None)
                data=overlay.sprite_png(route[len('/sprite/'):]) if overlay else None
                if data is None: self.reply(404,b'No sprite','text/plain')
                else: self.reply(200,data,'image/png',{'Cache-Control':'max-age=3600'})
            elif route == "/config":
                recognizer=self.server.recognizer
                stream=getattr(self.server,'stream',None)
                self.reply(200, json.dumps({"camera": self.server.camera, "recognition": recognizer is not None,
                    "mode":getattr(self.server,'mode','single-reference'),"offline":bool(getattr(self.server,'fixture',None)),
                    "experimental":getattr(self.server,'mode','') in ('draw2','embedding'),
                    "ar":getattr(self.server,'overlay',None) is not None,
                    "passcode_ocr":getattr(self.server,'passcode_worker',None) is not None,
                    "identity_resolution":IDENTITIES.info(),
                    "live_tracking":getattr(self.server,'live_tracker',None) is not None,
                    "stream":stream.status() if stream else None,
                    "server_loop":self.server.analysis_loop.status() if getattr(self.server,'analysis_loop',None) else None,
                    "inference":recognizer.status() if hasattr(recognizer,'status') else {'isolated':False},
                    "references":len(recognizer.references) if recognizer else 0}).encode(), "application/json")
            elif route == '/passcodes':
                worker=getattr(self.server,'passcode_worker',None)
                self.reply(200,json.dumps(worker.snapshot() if worker else {'state':'disabled','items':[]}).encode(),'application/json')
            elif route == '/download-status':
                path=ROOT/'.runtime/download-watch.json'
                payload=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'watch_state':'not_started'}
                self.reply(200,json.dumps(payload).encode(),'application/json')
            elif route == "/analyze":
                self.analyze()
            elif route == '/analysis':
                self.latest_analysis()
            elif route.startswith('/playmat/print/'):
                # Printable templates; generated on first request. Only known names are served.
                name=route.rsplit('/',1)[-1]
                allowed={f'tapete-jugador{p}{s}' for p in (1,2) for s in ('.png','-una-pieza.pdf','-hojas-carta.pdf')}
                if name not in allowed: return self.reply(404,b'Not found','text/plain')
                path=ROOT/'data/playmat/print'/name
                if not path.exists():
                    import subprocess,sys
                    subprocess.run([sys.executable,str(ROOT/'playmat_print.py')],cwd=ROOT,check=True,capture_output=True)
                self.reply(200,path.read_bytes(),'application/pdf' if name.endswith('.pdf') else 'image/png')
            elif route in ('/playmat','/duel'):
                table=getattr(self.server,'table',None)
                if table is None: return self.reply(404,b'Duel disabled (live camera only)','text/plain')
                body=table.overlay() if route=='/playmat' else table.view()
                self.reply(200,json.dumps(body,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            elif route == '/card-info':
                from card_info import card_sheet
                query=dict(p.split('=',1) for p in urlsplit(self.path).query.split('&') if '=' in p)
                sheet=card_sheet(query.get('id',''))
                if sheet is None: self.reply(404,b'Unknown card','text/plain')
                else: self.reply(200,json.dumps(sheet,ensure_ascii=False).encode(),'application/json; charset=utf-8')
            else:
                self.reply(404, b"Not found", "text/plain")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            try:
                self.reply(502, str(exc).encode(), "text/plain; charset=utf-8")
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
        except Exception:
            self.internal_error()

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

    def table_post(self,route):
        """Calibration (/playmat) or a player's decision (/duel); errors come back as 400 with the reason."""
        from duel_engine import DuelError
        table=getattr(self.server,'table',None)
        try:
            if table is None: return self.reply(404,b'Duel disabled (live camera only)','text/plain')
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536: return self.reply(413,b'Invalid body size','text/plain')
            payload=json.loads(self.rfile.read(length))
            if route=='/playmat' and payload.get('preview'): body=table.preview(payload['mode'],payload.get('virtual'),payload['image_size'])
            elif route=='/playmat': body=table.calibrate(payload['mode'],payload.get('mats',[]),payload.get('image_size'),payload.get('virtual'))
            else: body={'result':table.act(payload),'duel':table.view()}
            self.reply(200,json.dumps(body,ensure_ascii=False).encode(),'application/json; charset=utf-8')
        except (DuelError,ValueError,KeyError,TypeError) as exc:
            try: self.reply(400,json.dumps({'error':str(exc)},ensure_ascii=False).encode(),'application/json; charset=utf-8')
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError): pass
        except Exception: self.internal_error()

    def latest_analysis(self):
        """Long poll: the first server-loop analysis newer than `after`, or 204 after two seconds."""
        loop=getattr(self.server,'analysis_loop',None)
        if loop is None:
            return self.reply(404,b'Server loop disabled','text/plain')
        query=dict(p.split('=',1) for p in urlsplit(self.path).query.split('&') if '=' in p)
        try: after=int(query.get('after','-1'))
        except ValueError: return self.reply(400,b'Invalid sequence','text/plain')
        body=loop.wait_newer(after,timeout=2.)
        if body is None: return self.reply(204,b'','application/json')
        self.reply(200,body,'application/json')

    def get_snapshot(self):
        return self.get_snapshot_record()[0]

    def get_snapshot_record(self):
        return snapshot_record(self.server)


def snapshot_record(server):
    """(jpeg, captured_at, basis): fixture, MJPEG stream, or single-shot polling."""
    fixture=getattr(server,'fixture',None)
    stream=getattr(server,'stream',None)
    if fixture is None and stream is not None:
        try:
            data,captured=stream.latest()
            return data,captured,'stream_frame_receipt'
        except OSError:
            pass  # Stale or disconnected stream: poll a single frame instead.
    data,captured=server.snapshots.get((server.camera,str(fixture)),
        lambda:fixture.read_bytes() if fixture else snapshot(server.camera))
    live=getattr(server,'live_tracker',None)
    if live is not None and captured>server.last_tracked_at:
        server.last_tracked_at=captured;live.update(data,captured)
    return data,captured,'server_snapshot_request'


def run_analysis(server,data=None,captured_at=None,lock_timeout=-1):
    """One recognizer pass plus OCR submission and tracking; None if the lock was busy.

    Shared by POST /analyze (a browser-chosen frame) and the server loop
    (the newest stream frame).
    """
    started=time.perf_counter()
    received_at=time.time()
    capture_basis='client_snapshot_timestamp' if captured_at is not None else 'server_receive_time'
    if data is not None and captured_at is None: captured_at=received_at
    if not server.recognition_lock.acquire(timeout=lock_timeout):
        return None
    acquired=time.perf_counter()
    def report_stall():
        import faulthandler
        path=ROOT/'.runtime'/f'camera-{server.server_port}-stall.log'
        path.parent.mkdir(exist_ok=True)
        with path.open('w') as log:
            faulthandler.dump_traceback(file=log,all_threads=True)
    watchdog=threading.Timer(20,report_stall)
    watchdog.daemon=True
    watchdog.start()
    try:
        if data is None:
            data,captured_at,capture_basis=snapshot_record(server)
        inference_started=time.perf_counter()
        recognizer=server.recognizer
        live=getattr(server,'live_tracker',None)
        worker=getattr(server,'passcode_worker',None)
        if getattr(recognizer,'supports_context',False):
            from vision_onnx import REUSE_MAX_AGE_S
            reuse=live.reuse_candidates(captured_at,REUSE_MAX_AGE_S) if live else ()
            verified=worker.verified() if worker and hasattr(worker,'verified') else ()
            # With a duel board set, cards outside its field zones are not analysed at all.
            table=getattr(server,'table',None)
            regions=table.field_regions() if table is not None else None
            result=recognizer.analyze_jpeg(data,reuse=reuse,verified=verified,regions=regions)
        else:
            result=recognizer.analyze_jpeg(data)
        result['detections']=[normalize_detection(d) for d in result['detections']]
        if 'candidates' in result:result['candidates']=[normalize_detection(d) for d in result['candidates']]
        result['identity_resolution']=IDENTITIES.info()
        inference_finished=time.perf_counter()
        if worker:
            named={tuple(map(tuple,d['corners'])):d for d in result['detections']}
            boxes=[]
            for d in result.get('candidates',result['detections']):
                visual=named.get(tuple(map(tuple,d['corners'])),{})
                boxes.append({'corners':d['corners'],'visual_card_id':visual.get('card_id'),'name':visual.get('name'),
                              'source_visual_card_id':visual.get('source_card_id',visual.get('card_id')),
                              'candidate_ids':[t['card_id'] for t in d.get('top5',[]) if t.get('card_id')][:3],
                              'geometry_status':d.get('geometry_status'),'geometry_iou':d.get('geometry_iou')})
            worker.submit(data,boxes,captured_at)
        if getattr(server,'tracker',None):
            result['detections']=server.tracker.update(result['detections'])
        if live is not None:
            # Sprites and names follow these corners at video rate from here on.
            live.sync(result['detections'],captured_at)
            result['tracks']=track_payload(live.snapshot())
            table=getattr(server,'table',None)
            if table is not None:
                # Only confirmed tracks reach the duel; provisional identities could be wrong.
                # A duel bug must never stop recognition: log it and carry on.
                try:
                    if table.mode=='printed':
                        # Printed mats: find their markers in this very frame (~7 ms at 1080p).
                        import cv2,numpy as np
                        grey=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_GRAYSCALE)
                        if grey is not None: table.see_markers(grey,captured_at)
                    table.feed([t for t in live.snapshot() if t.get('stable')])
                except Exception: traceback.print_exc()
        for d in result['detections']:
            if d.get('sprite_ref') and getattr(server,'overlay',None) is not None:
                d['sprite_url']='/sprite/'+d['sprite_ref']
        result['image']='data:image/jpeg;base64,'+base64.b64encode(data).decode('ascii')
        result.update(captured_at=captured_at,capture_time_basis=capture_basis,
            received_at=received_at,completed_at=time.time())
        result['pipeline_ms']={
            'lock_wait':round((acquired-started)*1000,1),
            'capture':round((inference_started-acquired)*1000,1),
            'recognition':round((inference_finished-inference_started)*1000,1),
            'postprocess':round((time.perf_counter()-inference_finished)*1000,1),
            'total':round((time.perf_counter()-started)*1000,1)}
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
    def __init__(self,server,idle_after=5.):
        self.server=server;self.idle_after=idle_after
        self.condition=threading.Condition();self.sequence=0;self.body=None
        self.last_client=0.;self.last_captured=0.;self.errors=0;self.closed=False
        self.thread=threading.Thread(target=self.run,name='analysis-loop',daemon=True);self.thread.start()

    def wait_newer(self,after,timeout):
        with self.condition:
            self.last_client=time.monotonic();self.condition.notify_all()
            # A tab that outlived a server restart asks for a sequence this process never
            # reached: treat it as new instead of letting it wait forever.
            if after>self.sequence: after=-1
            ready=lambda:self.body is not None and self.sequence>after
            if not self.condition.wait_for(lambda:ready() or self.closed,timeout):return None
            return self.body if ready() else None

    def run(self):
        while not self.closed:
            with self.condition:
                if time.monotonic()-self.last_client>self.idle_after:
                    self.condition.wait(.5);continue
            try:
                data,captured_at,basis=snapshot_record(self.server)
                if captured_at<=self.last_captured:
                    time.sleep(.005);continue  # same frame as the last analysis
                self.last_captured=captured_at
                result=run_analysis(self.server,data,captured_at)
                result['capture_time_basis']=basis
                self.errors=0
            except Exception as exc:
                # A camera or inference failure is reported to the tabs, then retried.
                self.errors+=1;traceback.print_exc()
                result={'error':str(exc) or type(exc).__name__,'detections':[],'captured_at':time.time()}
                time.sleep(min(2.,.2*self.errors))
            with self.condition:
                self.sequence+=1;result['sequence']=self.sequence
                self.body=json.dumps(result).encode()
                self.condition.notify_all()

    def status(self):
        return {'sequence':self.sequence,'watching':time.monotonic()-self.last_client<=self.idle_after,'errors':self.errors}

    def close(self):
        with self.condition:
            self.closed=True;self.condition.notify_all()


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
    server.recognition_lock = threading.Lock()
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
