"""Local Android IP Webcam viewer; Python standard library only."""

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

ROOT = Path(__file__).resolve().parent


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


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self,*args,**kwargs):
        self.snapshots=SharedSnapshots()
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
            elif route == '/camera.js':
                self.reply(200,(ROOT/'web/camera.js').read_bytes(),'text/javascript; charset=utf-8')
            elif route == '/pose-annotator':
                self.reply(200,(ROOT/'web/pose_annotator.html').read_bytes(),'text/html; charset=utf-8')
            elif route == "/snapshot":
                data,captured_at=self.get_snapshot_record()
                self.reply(200, data, "image/jpeg", {'X-Captured-At':captured_at,
                    'X-Capture-Time-Basis':'server_snapshot_request'})
            elif route == "/config":
                self.reply(200, json.dumps({"camera": self.server.camera, "recognition": self.server.recognizer is not None,
                    "mode":getattr(self.server,'mode','single-reference'),"offline":bool(getattr(self.server,'fixture',None)),
                    "experimental":getattr(self.server,'mode','') in ('draw2','embedding'),
                    "ar":getattr(self.server,'overlay',None) is not None,
                    "passcode_ocr":getattr(self.server,'passcode_worker',None) is not None,
                    "references":len(self.server.recognizer.references) if self.server.recognizer else 0}).encode(), "application/json")
            elif route == '/passcodes':
                worker=getattr(self.server,'passcode_worker',None)
                self.reply(200,json.dumps(worker.snapshot() if worker else {'state':'disabled','items':[]}).encode(),'application/json')
            elif route == "/analyze":
                self.analyze()
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
        if urlsplit(self.path).path!='/analyze':
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
        started=time.perf_counter()
        received_at=time.time()
        capture_basis='client_snapshot_timestamp' if captured_at is not None else 'server_receive_time'
        if data is not None and captured_at is None: captured_at=received_at
        if self.server.recognizer is None:
            return self.reply(503,b'Recognition disabled','text/plain')
        # A short bounded wait lets multiple tabs take turns instead of one
        # polling tab repeatedly missing the small gap between other requests.
        if not self.server.recognition_lock.acquire(timeout=2):
            return self.reply(503,b'Recognition busy','text/plain')
        acquired=time.perf_counter()
        def report_stall():
            import faulthandler
            path=ROOT/'.runtime'/f'camera-{self.server.server_port}-stall.log'
            path.parent.mkdir(exist_ok=True)
            with path.open('w') as log:
                faulthandler.dump_traceback(file=log,all_threads=True)
        watchdog=threading.Timer(20,report_stall)
        watchdog.daemon=True
        watchdog.start()
        try:
            if data is None:
                data,captured_at=self.get_snapshot_record();capture_basis='server_snapshot_request'
            inference_started=time.perf_counter()
            result=self.server.recognizer.analyze_jpeg(data)
            inference_finished=time.perf_counter()
            worker=getattr(self.server,'passcode_worker',None)
            if worker:
                named={tuple(map(tuple,d['corners'])):d for d in result['detections']}
                boxes=[]
                for d in result.get('candidates',result['detections']):
                    visual=named.get(tuple(map(tuple,d['corners'])),{})
                    boxes.append({'corners':d['corners'],'visual_card_id':visual.get('card_id'),'name':visual.get('name'),
                                  'candidate_ids':[t['card_id'] for t in d.get('top5',[]) if t.get('card_id')][:3],
                                  'geometry_status':d.get('geometry_status'),'geometry_iou':d.get('geometry_iou')})
                worker.submit(data,boxes,captured_at)
            if getattr(self.server,'tracker',None):
                result['detections']=self.server.tracker.update(result['detections'])
            if getattr(self.server,'overlay',None):
                import cv2
                import numpy as np
                frame=cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR)
                # Only the transparent layer travels; the browser composes it over
                # the original JPEG, so no second full-frame blend/encode here.
                layer=self.server.overlay.render(frame,result['detections'],transparent=True)
                result['ar_layer']='data:image/png;base64,'+base64.b64encode(cv2.imencode('.png',layer)[1]).decode('ascii')
            result['image']='data:image/jpeg;base64,'+base64.b64encode(data).decode('ascii')
            result.update(captured_at=captured_at,capture_time_basis=capture_basis,
                received_at=received_at,completed_at=time.time())
            result['pipeline_ms']={
                'lock_wait':round((acquired-started)*1000,1),
                'capture':round((inference_started-acquired)*1000,1),
                'recognition':round((inference_finished-inference_started)*1000,1),
                'postprocess':round((time.perf_counter()-inference_finished)*1000,1),
                'total':round((time.perf_counter()-started)*1000,1)}
        finally:
            watchdog.cancel()
            # Socket writes must not hold the inference lock (slow/disconnected tab).
            self.server.recognition_lock.release()
        self.reply(200,json.dumps(result).encode(),'application/json')

    def get_snapshot(self):
        return self.get_snapshot_record()[0]

    def get_snapshot_record(self):
        fixture=getattr(self.server,'fixture',None)
        return self.server.snapshots.get((self.server.camera,str(fixture)),
            lambda:fixture.read_bytes() if fixture else snapshot(self.server.camera))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera", type=camera_url, default="http://192.168.1.18:8080")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true", help="Fetch three JPEG frames and exit")
    parser.add_argument("--recognize", action="store_true", help="Enable recognition from the local reference catalog")
    parser.add_argument('--pilot',action='store_true',help='Use the reviewed pilot catalog with multi-card matching')
    parser.add_argument('--ar',action='store_true',help='Overlay sprites after two consistent observations')
    parser.add_argument('--image',type=Path,help='Offline fixture image; explicitly labelled in the viewer')
    parser.add_argument('--backend',choices=['sift','draw2','embedding'],default='sift',help='ONNX choices are experimental and require .venv-eval')
    parser.add_argument('--no-passcode',action='store_true',help='Disable asynchronous passcode crop/OCR')
    args = parser.parse_args()
    if args.check:
        for i in range(3):
            start = time.monotonic()
            data = snapshot(args.camera)
            print(f"Frame {i + 1}: JPEG completo, {len(data)} bytes, {(time.monotonic() - start) * 1000:.0f} ms", flush=True)
        return
    recognizer = None
    if args.backend!='sift':
        from vision_onnx import LiveRecognizer
        recognizer=LiveRecognizer('classifier' if args.backend=='draw2' else 'embedding')
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
    server.tracker=None
    server.overlay=None
    server.passcode_worker=None
    if recognizer:
        from ar_overlay import Tracker,SpriteOverlay
        server.tracker=Tracker()
        server.overlay=SpriteOverlay() if args.ar and (args.pilot or args.backend!='sift') else None
        if not args.no_passcode:
            from passcode_ocr import PasscodeWorker
            server.passcode_worker=PasscodeWorker()
    print(f"Visor: http://127.0.0.1:{args.port} | Camara: {args.camera}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server.passcode_worker: server.passcode_worker.close()
        server.server_close()


if __name__ == "__main__":
    main()
