"""Regression: slow/failed recognition must not freeze live camera acquisition."""
import json,threading,time,urllib.request
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import cv2,numpy as np
from playwright.sync_api import sync_playwright
from camera_viewer import Server,Handler
from ar_overlay import SpriteOverlay

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT=Path(__file__).resolve().parent
class FakePhone(BaseHTTPRequestHandler):
    count=0
    offline=False
    def do_GET(self):
        if self.offline:
            self.send_error(502);return
        type(self).count+=1
        image=np.full((120,160,3),((self.count*17)%256,40,80),np.uint8)
        cv2.putText(image,str(self.count),(10,65),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
        data=cv2.imencode('.jpg',image)[1].tobytes()
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.send_header('Content-Type','image/jpeg');self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

class SlowRecognizer:
    references=[{}]
    calls=0
    def analyze_jpeg(self,data):
        self.calls+=1
        assert cv2.imdecode(np.frombuffer(data,np.uint8),cv2.IMREAD_COLOR).shape==(120,160,3)
        time.sleep(3 if self.calls==1 else .4)
        if self.calls==2:raise ValueError('Controlled recognition failure')
        return {'detections':[{'id':'test','name':'Carta de prueba','corners':[[20,10],[100,10],[100,100],[20,100]]}],
                'processing_ms':3000 if self.calls==1 else 400,'width':160,'height':120}

def main():
    phone=ThreadingHTTPServer(('127.0.0.1',0),FakePhone)
    viewer=Server(('127.0.0.1',0),Handler)
    viewer.camera=f'http://127.0.0.1:{phone.server_port}';viewer.recognizer=SlowRecognizer();viewer.recognition_lock=threading.Lock()
    viewer.overlay=None;viewer.tracker=None;viewer.mode='test';viewer.fixture=None
    for s in (phone,viewer):threading.Thread(target=s.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
            page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{viewer.server_port}')
            page.evaluate('''() => {window.cameraDraws=0;const original=ctx.drawImage.bind(ctx);
              ctx.drawImage=(...args)=>{cameraDraws++;return original(...args);};}''')
            page.wait_for_function("Number(document.querySelector('#frame').dataset.frameNumber)>=8",timeout=2900)
            assert viewer.recognizer.calls==1,'Expected inference still busy'
            assert not page.locator('#detection').get_attribute('data-completed'),'Analysis completed too early'
            frames_during_inference=int(page.locator('#frame').get_attribute('data-frame-number'))
            assert page.evaluate('cameraDraws<=frameNumber+2'),'Unchanged video frame is repainted repeatedly'
            page.wait_for_function("Number(document.querySelector('#detection').dataset.completed)>=1",timeout=6000)
            assert page.evaluate('performance.now()-resultAt>2500'),'Slow result should already be too old for live overlay'
            assert page.locator('#analysisView').is_visible(),'Slow recognition must remain visible on its actual frame'
            assert 'Carta de prueba' in page.locator('#analysisNames').inner_text()
            page.wait_for_function("Number(document.querySelector('#detection').dataset.completed)>=2",timeout=10000)
            assert viewer.recognizer.calls>=3,'Recognition failed to recover after an error'
            page.route('**/analyze',lambda route:route.fulfill(status=503,body='Recognition busy'))
            previous_generation=page.evaluate('generation')
            page.wait_for_function("detection.textContent.includes('Reconocimiento ocupado')")
            assert page.evaluate('generation')==previous_generation,'Busy response invalidated valid state'
            assert page.locator('#analysisView').is_visible()
            page.unroute('**/analyze')
            page.locator('#pause').click();time.sleep(.4)
            frozen=page.locator('#frame').get_attribute('data-frame-number');time.sleep(.5)
            assert page.locator('#frame').get_attribute('data-frame-number')==frozen
            page.locator('#pause').click()
            page.wait_for_function(f"Number(document.querySelector('#frame').dataset.frameNumber)>{frozen}")
            FakePhone.offline=True
            page.wait_for_function("document.querySelector('#status').textContent.includes('Sin señal')")
            FakePhone.offline=False
            page.wait_for_function("document.querySelector('#status').textContent.includes('Cámara en vivo')",timeout=5000)
            # A decoded analysis image must not commit after pause invalidates it.
            # Only the analysis image (a data: URL) is delayed; intercepting
            # createImageBitmap also caught the camera loop and could hang the wait.
            page.locator('#recognize').uncheck()
            page.evaluate('''async () => {
              const original=window.fetch;
              window.delayedPaintRelease=null;
              window.fetch=async (...args)=>{
                const response=await original(...args);
                if(typeof args[0]==='string'&&args[0].startsWith('data:'))await new Promise(resolve=>window.delayedPaintRelease=resolve);
                return response;
              };
              window.restoreBitmap=()=>window.fetch=original;
              window.paintBefore=document.querySelector('#analysisNames').textContent;
              window.delayedPaint=paintAnalysis({...lastAnalysis,detections:[{name:'STALE RESPONSE'}]});
            }''')
            page.wait_for_function('window.delayedPaintRelease!==null')
            page.locator('#pause').click()
            page.evaluate('''async () => {delayedPaintRelease();await delayedPaint;restoreBitmap();
              if(document.querySelector('#analysisNames').textContent!==paintBefore)throw Error('Stale paint committed');}''')
            page.locator('#pause').click()
            assert not errors,errors
            browser.close()
        overlay=SpriteOverlay();overlay.cache['synthetic']=np.full((50,50,4),(0,0,0,255),np.uint8)
        blank=np.full((120,160,3),180,np.uint8)
        detections=[{'sprite_ref':'synthetic','stable':True,'corners':[[30,10],[130,10],[130,110],[30,110]]}]
        layer=overlay.render(blank,detections,transparent=True)
        assert layer.shape==(120,160,4) and layer[0,0,3]==0 and layer[60,80,3]==255
        assert layer[60,80,:3].max()==0,'Black sprite must remain opaque'
        result={'status':'passed','frames_while_first_inference_running':frames_during_inference,'checks':['independent capture and inference','no repeated repaint of unchanged frame','slow result visible on analyzed frame after live-overlay expiry','POST JPEG analysis','recognition error recovery and lock release','busy response preserves session and reference image','pause/resume','camera reconnect','late image decode discarded after pause','transparent AR including black pixels','no browser JS errors']}
        (QA_OUT/'live-camera.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
    finally:
        for s in (viewer,phone):s.shutdown();s.server_close()
if __name__=='__main__':main()
