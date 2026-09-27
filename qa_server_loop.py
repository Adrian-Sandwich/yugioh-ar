"""Server loop: idle without viewers, newest frame once, long poll, error recovery, POST /analyze alongside."""
import json,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import cv2,numpy as np
from camera_source import MjpegSource
from camera_viewer import Server,Handler,AnalysisLoop


def jpeg(n):
    image=np.full((90,120,3),(n*7%256,80,40),np.uint8);cv2.putText(image,str(n),(5,60),cv2.FONT_HERSHEY_SIMPLEX,1.2,(255,255,255),2)
    return cv2.imencode('.jpg',image)[1].tobytes()


class Phone(BaseHTTPRequestHandler):
    streaming=True;shots=0
    def do_GET(self):
        if self.path.startswith('/shot.jpg'):
            type(self).shots+=1;data=jpeg(1000+self.shots)
            self.send_response(200);self.send_header('Content-Type','image/jpeg');self.send_header('Content-Length',str(len(data)));self.end_headers()
            return self.wfile.write(data)
        if not self.path.startswith('/video'):return self.send_error(404)
        self.send_response(200);self.send_header('Content-Type','multipart/x-mixed-replace; boundary=frame');self.end_headers()
        n=0
        while self.streaming:
            n+=1;data=jpeg(n)
            try:self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n'%len(data)+data+b'\r\n');self.wfile.flush()
            except OSError:return
            time.sleep(.03)
    def log_message(self,*a):pass


class Recognizer:
    """Stands in for LiveRecognizer: slow enough that frames pile up between analyses."""
    references=()
    def __init__(self):self.seen=[];self.fail_next=False;self.slow_next=False;self.lock=threading.Lock()
    def analyze_jpeg(self,data):
        with self.lock:
            if self.fail_next:self.fail_next=False;raise RuntimeError('forced failure')
            slow=self.slow_next;self.slow_next=False
            self.seen.append(data);time.sleep(3. if slow else .08)
            return {'detections':[],'candidates':[],'processing_ms':80.,'width':120,'height':90}


def get(url,timeout=5):
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=timeout) as r:
        return r.status,r.read()


def main():
    phone=ThreadingHTTPServer(('127.0.0.1',0),Phone);threading.Thread(target=phone.serve_forever,daemon=True).start()
    base=f'http://127.0.0.1:{phone.server_port}'
    viewer=Server(('127.0.0.1',0),Handler);viewer.camera=base;viewer.fixture=None
    viewer.recognizer=recognizer=Recognizer();viewer.recognition_lock=threading.Lock()
    viewer.stream=MjpegSource(base)
    loop=viewer.analysis_loop=AnalysisLoop(viewer,idle_after=1.)
    threading.Thread(target=viewer.serve_forever,daemon=True).start()
    url=f'http://127.0.0.1:{viewer.server_port}'
    checks=[]
    try:
        deadline=time.time()+5
        while time.time()<deadline and viewer.stream.frames<6:time.sleep(.02)
        assert viewer.stream.frames>=6 and loop.sequence==0 and not recognizer.seen,('no analysis without a viewer',viewer.stream.status(),loop.status(),len(recognizer.seen))
        checks.append('idle without viewers')
        status,body=get(url+'/analysis?after=-1');data=json.loads(body)
        assert status==200 and data['sequence']>=1 and data['capture_time_basis']=='stream_frame_receipt' and data['image'].startswith('data:image/jpeg;base64,'),data.keys()
        # Keep one tab watching for a while: every analysis must use a newer frame than the last.
        after=data['sequence'];sequences=[after];deadline=time.time()+1.2
        while time.time()<deadline:
            status,body=get(url+f'/analysis?after={after}')
            if status==200:after=json.loads(body)['sequence'];sequences.append(after)
        assert len(sequences)>=5 and sequences==sorted(sequences),sequences
        assert len(recognizer.seen)==len(set(recognizer.seen)),'a frame was analyzed twice'
        assert viewer.stream.frames>len(recognizer.seen),'frames arriving during an analysis are skipped, not queued'
        checks.append('newest frame, each at most once, in order')
        status,body=get(url+'/config');assert json.loads(body)['server_loop']['watching'] is True
        checks.append('/config reports the loop')
        # A tab from before a server restart holds a sequence this server never reached.
        status,body=get(url+f'/analysis?after={loop.sequence+10000}')
        assert status==200 and json.loads(body)['sequence']<=loop.sequence,'stale sequence must get the latest result'
        checks.append('stale sequence after restart gets the latest result')
        # POST /analyze still works while the loop runs (shared recognition lock).
        request=urllib.request.Request(url+'/analyze',data=jpeg(999),headers={'Content-Type':'image/jpeg','X-Captured-At':str(time.time())},method='POST')
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as r:
            assert r.status==200 and json.loads(r.read())['capture_time_basis']=='client_snapshot_timestamp'
        checks.append('POST /analyze alongside the loop')
        # One failure: reported to the tab, then the loop keeps analyzing.
        recognizer.fail_next=True;errors=0;ok_after=False;deadline=time.time()+3
        while time.time()<deadline and not ok_after:
            status,body=get(url+f'/analysis?after={after}')
            if status!=200:continue
            item=json.loads(body);after=item['sequence']
            if 'error' in item:errors+=1;assert item['error']=='forced failure' and item['detections']==[]
            elif errors:ok_after=True
        assert errors==1 and ok_after,(errors,ok_after)
        checks.append('failure reported, loop recovers')
        # An analysis slower than the long poll: the tab gets 204 and simply asks again.
        # (An analysis already running when the flag is set still answers 200 first.)
        recognizer.slow_next=True;status=None
        for _ in range(3):
            started=time.time();status,body=get(url+f'/analysis?after={loop.sequence}');waited=time.time()-started
            if status==204:break
        assert status==204 and 1.5<waited<2.8,(status,waited)
        checks.append('long poll times out with 204')
        # Stream stops: the viewer falls back to single shots and the loop keeps going.
        Phone.streaming=False;deadline=time.time()+6;basis=None
        while time.time()<deadline and basis!='server_snapshot_request':
            status,body=get(url+f'/analysis?after={after}')
            if status==200:item=json.loads(body);after=item['sequence'];basis=item.get('capture_time_basis')
        assert basis=='server_snapshot_request' and Phone.shots>0,(basis,Phone.shots)
        checks.append('stream loss falls back to single shots')
        # Nobody asks any more: the loop goes idle again.
        count=len(recognizer.seen);time.sleep(1.8);assert len(recognizer.seen)<=count+1 and loop.status()['watching'] is False
        checks.append('idle again without viewers')
    finally:
        loop.close();viewer.stream.close();viewer.shutdown();phone.shutdown()
    print(json.dumps({'status':'passed','analyses':len(recognizer.seen),'checks':checks}))


if __name__=='__main__':
    main()
