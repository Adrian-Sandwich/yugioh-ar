"""Two same-origin tabs share analysis, retain source age and survive owner changes."""
import json
import threading
import time

from playwright.sync_api import sync_playwright

from camera_viewer import Handler, ROOT, Server
from qa_live_camera import FakePhone
from http.server import ThreadingHTTPServer


class Recognizer:
    references=[{}]
    def __init__(self): self.calls=0;self.active=0;self.maximum=0
    def analyze_jpeg(self, data):
        self.calls+=1;self.active+=1;self.maximum=max(self.maximum,self.active)
        try:
            time.sleep(1.4)
            return {'detections':[], 'width':160, 'height':120, 'processing_ms':1400}
        finally: self.active-=1


from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
def main():
    FakePhone.offline=False
    phone=ThreadingHTTPServer(('127.0.0.1',0),FakePhone)
    viewer=Server(('127.0.0.1',0),Handler)
    viewer.camera=f'http://127.0.0.1:{phone.server_port}'
    viewer.fixture=None;viewer.mode='test';viewer.recognizer=Recognizer()
    viewer.recognition_lock=threading.Lock();viewer.overlay=None;viewer.tracker=None
    for server in (phone,viewer): threading.Thread(target=server.serve_forever,daemon=True).start()
    errors=[];statuses=[]
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
            context=browser.new_context()
            pages=[context.new_page(),context.new_page()]
            for page in pages:
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('response',lambda response:statuses.append(response.status) if response.url.endswith('/analyze') else None)
                page.goto(f'http://127.0.0.1:{viewer.server_port}')
                page.evaluate('''() => {window.observedCaptures=[];const original=acceptAnalysis;
                  acceptAnalysis=async (...args)=>{observedCaptures.push(args[0].captured_at);return original(...args);};}''')
                assert page.evaluate('!!sharedAnalysis'),'Cross-tab coordinator unavailable'
            for page in pages:
                page.wait_for_function("Number(detection.dataset.completed)>=1",timeout=8000)
            stamps=[page.evaluate('observedCaptures[0]') for page in pages]
            assert stamps[0]==stamps[1],stamps
            assert all(page.evaluate('performance.now()-resultAt>=1300') for page in pages)
            assert viewer.recognizer.maximum==1
            # Pausing a follower must not pause the other tab or accept broadcasts.
            pages[0].locator('#pause').click()
            frozen=pages[0].evaluate('Number(detection.dataset.completed)')
            previous=pages[1].evaluate('Number(detection.dataset.completed)')
            pages[1].wait_for_function(f'Number(detection.dataset.completed)>{previous}',timeout=6000)
            assert pages[0].evaluate('Number(detection.dataset.completed)')==frozen
            pages[0].locator('#pause').click()
            pages[1].locator('#recognize').uncheck()
            pages[0].wait_for_function(f'Number(detection.dataset.completed)>{frozen}',timeout=6000)
            # Closing a tab releases browser ownership; the remaining tab can run.
            pages[0].close()
            pages[1].locator('#recognize').check()
            previous=pages[1].evaluate('Number(detection.dataset.completed)')
            pages[1].wait_for_function(f'Number(detection.dataset.completed)>{previous}',timeout=6000)
            assert not errors,errors
            assert 503 not in statuses,statuses
            assert viewer.recognizer.maximum==1
            result={'status':'passed','first_capture_times':stamps,'http_statuses':statuses,
                'max_concurrent_inference':viewer.recognizer.maximum,
                'checks':['same analysis delivered to two tabs','capture age includes inference',
                          'pause is local','recognition toggle is local','owner close recovery','no busy responses','no JS errors']}
            (QA_OUT/'shared-camera.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result))
            browser.close()
    finally:
        for server in (viewer,phone): server.shutdown();server.server_close()


if __name__=='__main__': main()
