"""MJPEG source: newest frame wins, callback per frame, stale detection, polling fallback in the viewer."""
import json,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import cv2,numpy as np
from camera_source import MjpegSource
from camera_viewer import Server,Handler

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT=Path(__file__).resolve().parent

def jpeg(n):
    image=np.full((90,120,3),(n*9%256,60,90),np.uint8);cv2.putText(image,str(n),(5,60),cv2.FONT_HERSHEY_SIMPLEX,1.2,(255,255,255),2)
    data=cv2.imencode('.jpg',image)[1].tobytes()
    # Like phone frames: an APP1 segment carrying a whole thumbnail JPEG (with its own EOI) right after SOI.
    thumb=cv2.imencode('.jpg',cv2.resize(image,(24,18)))[1].tobytes()
    app1=b'Exif\x00\x00'+thumb;segment=b'\xff\xe1'+(len(app1)+2).to_bytes(2,'big')+app1
    return data[:2]+segment+data[2:]

class Phone(BaseHTTPRequestHandler):
    frames=6;delay=.05;shots=0;streams=0;stop_stream=False
    def do_GET(self):
        if self.path.startswith('/video'):
            type(self).streams+=1
            self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame');self.end_headers()
            for n in range(1,self.frames+1):
                if self.stop_stream:return
                data=jpeg(n)
                # Split a frame across two writes to exercise buffering.
                self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n'%len(data)+data[:len(data)//2]);self.wfile.flush()
                time.sleep(.01);self.wfile.write(data[len(data)//2:]+b'\r\n');self.wfile.flush();time.sleep(self.delay)
            return
        if self.path.startswith('/shot.jpg'):
            type(self).shots+=1;data=jpeg(100+self.shots)
            self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Content-Type','image/jpeg');self.end_headers();self.wfile.write(data);return
        self.send_error(404)
    def log_message(self,*a):pass

def main():
    phone=ThreadingHTTPServer(('127.0.0.1',0),Phone);threading.Thread(target=phone.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{phone.server_port}'
    seen=[]
    source=MjpegSource(base,on_frame=lambda frame,captured:seen.append((len(frame),captured)),stale_s=.6)
    deadline=time.time()+5
    while time.time()<deadline and source.frames<Phone.frames:time.sleep(.02)
    assert source.frames>=Phone.frames,source.status()
    frame,captured=source.latest()
    assert frame.startswith(b'\xff\xd8') and frame.endswith(b'\xff\xd9') and cv2.imdecode(np.frombuffer(frame,np.uint8),cv2.IMREAD_COLOR).shape==(90,120,3)
    assert frame.count(b'\xff\xd9')==2,'frame must not be cut at the EXIF thumbnail EOI'
    assert frame in {jpeg(n) for n in range(1,Phone.frames+1)},'frame bytes must match a whole emitted frame'
    from camera_source import frame_end
    assert frame_end(bytearray(frame),0)==len(frame) and frame_end(bytearray(frame[:-1]),0)==-1
    assert len(seen)==source.frames and seen[-1][0]==len(frame),'callback must see every frame in order'
    assert all(b[1]>=a[1] for a,b in zip(seen,seen[1:])),'timestamps must not go backwards'
    # The stream ends after six frames: reconnects happen, and meanwhile latest() goes stale.
    Phone.stop_stream=True;time.sleep(.8)
    try:source.latest();raise AssertionError('stale stream must raise')
    except OSError:pass
    # Viewer: stream preferred, polling fallback when stale, tracker fed either way.
    viewer=Server(('127.0.0.1',0),Handler);viewer.camera=base;viewer.recognizer=None;viewer.recognition_lock=threading.Lock()
    class CountingTracker:
        updates=0;last_update_ms=0;frame_count=0
        def update(self,data,captured):type(self).updates+=1;type(self).frame_count+=1
        def snapshot(self):return [{'track_id':1,'card_id':'x','name':'Carta','corners':[[1.26,2],[3,4],[5,6],[7,8]],'stable':True}]
    viewer.live_tracker=CountingTracker();viewer.stream=source
    threading.Thread(target=viewer.serve_forever,daemon=True).start()
    with urllib.request.urlopen(f'http://127.0.0.1:{viewer.server_port}/snapshot',timeout=5) as r:
        body=r.read();basis=r.headers['X-Capture-Time-Basis'];tracks=json.loads(r.headers['X-Tracks'])
    assert basis=='server_snapshot_request' and Phone.shots>=1 and CountingTracker.updates==1,'stale stream must fall back to polling and feed the tracker'
    assert tracks==[{'track_id':1,'card_id':'x','name':'Carta','corners':[[1.3,2.0],[3.0,4.0],[5.0,6.0],[7.0,8.0]],'stable':True}]
    with urllib.request.urlopen(f'http://127.0.0.1:{viewer.server_port}/tracks',timeout=5) as r:
        assert json.loads(r.read())['tracks'][0]['card_id']=='x'
    # Stream back: the viewer serves stream frames without polling.
    Phone.stop_stream=False;Phone.frames=400;Phone.delay=.03
    deadline=time.time()+6
    while time.time()<deadline:
        try:source.latest();break
        except OSError:time.sleep(.05)
    shots=Phone.shots
    with urllib.request.urlopen(f'http://127.0.0.1:{viewer.server_port}/snapshot',timeout=5) as r:
        assert r.headers['X-Capture-Time-Basis']=='stream_frame_receipt' and r.read().startswith(b'\xff\xd8')
    assert Phone.shots==shots,'stream frames must not trigger polling'
    source.close();viewer.shutdown();viewer.server_close();Phone.stop_stream=True;phone.shutdown();phone.server_close()
    report={'status':'passed','frames_received':source.frames,'reconnects_observed':Phone.streams-1,
            'checks':['frames parsed across chunk boundaries','EXIF thumbnail EOI does not cut the frame','callback per frame in order','stale stream raises','viewer falls back to polling and feeds tracker','X-Tracks header and /tracks','stream frames served without polling']}
    (QA_OUT/'camera-source.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
