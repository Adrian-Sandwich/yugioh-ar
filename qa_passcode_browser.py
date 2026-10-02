"""Actual HTTP viewer + local OCR, using an explicitly fixed reference photograph."""
import json,threading
from urllib.request import urlopen
from playwright.sync_api import sync_playwright
from camera_viewer import Server,Handler,ROOT
from passcode_ocr import PasscodeWorker,lookup
from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ref=json.loads((ROOT/'data/references/catalog.json').read_text(encoding='utf-8'))[0]
uid=lookup('89631139')[0]['card_id']
class Recognizer:
    references=[ref]
    def analyze_jpeg(self,jpeg,**context):
        return {'detections':[{'id':'fixture','card_id':uid,'name':'Dragón Blanco de Ojos Azules','corners':ref['corners']}],
                'width':1920,'height':1080,'processing_ms':1}
server=Server(('127.0.0.1',0),Handler)
server.camera='http://127.0.0.1:1';server.fixture=(ROOT/'data/references'/ref['source']).resolve()
server.recognizer=Recognizer();server.recognition_lock=threading.Lock();server.tracker=None;server.overlay=None;server.mode='test-fixture'
server.passcode_worker=PasscodeWorker()
threading.Thread(target=server.serve_forever,daemon=True).start()
try:
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
        page=browser.new_page(viewport={'width':1400,'height':1100});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}')
        page.wait_for_function("document.querySelector('#downloadWatch').textContent.startsWith('Neuron:')",timeout=10000)
        page.wait_for_function("document.querySelector('#passcodeCards code')?.textContent==='89631139'",timeout=20000)
        assert page.locator('.passcode-card .zoom').is_visible()
        assert page.locator('.passcode-card .name-zoom').first.is_visible()
        assert page.locator('.passcode-card .name-zoom').first.evaluate('(img)=>img.complete&&img.naturalWidth>0')
        assert page.locator('.passcode-card .rectified').is_visible()
        assert page.locator('.passcode-card a[href*="mode=passcode"]').first.get_attribute('href').endswith('?mode=passcode&q=89631139')
        assert page.locator('.name-reading strong').first.inner_text()=='BLUE-EYES WHITE DRAGON'
        assert 'Coincidencia por nombre' in page.locator('.name-reading').first.inner_text()
        assert 'Lectura candidata' in page.locator('.passcode-card').inner_text()
        first=int(page.locator('#frame').get_attribute('data-frame-number'))
        page.wait_for_function(f'frameNumber>{first+8}')
        page.locator('#passcodes').scroll_into_view_if_needed()
        page.screenshot(path=str(QA_OUT/'passcode/browser.png'))
        data=json.load(urlopen(f'http://127.0.0.1:{server.server_port}/passcodes'))
        config=json.load(urlopen(f'http://127.0.0.1:{server.server_port}/config'))
        assert data['identity_resolution']['version']==config['identity_resolution']['version']
        assert data['identity_resolution']['aliases']==12
        assert data['items'][0]['consistent_frames']==1,'A fixed photograph must not count as distinct captures'
        assert data['items'][0]['name_crop'].startswith('data:image/png;base64,')
        assert data['items'][0]['name_ocr']['status']=='matched'
        assert data['items'][0]['set_ocr']['code']=='LED3-EN006'
        assert data['items'][0]['set_ocr']['status']=='matched'
        assert data['items'][0]['evidence']['status']=='corroborated'
        assert data['items'][0]['evidence']['consistent_frames']==1
        assert set(data['items'][0]['evidence']['sources'])=={'image','name','serial','set','art'},data['items'][0]['evidence']
        assert data['items'][0]['art_match']['status']=='matched'
        assert not errors,errors
        browser.close()
    print('PASS: original photograph -> asynchronous OCR -> passcode + registry link + visible name and serial crops; camera continues; fixed image never confirms')
finally:
    server.passcode_worker.close();server.shutdown();server.server_close()
