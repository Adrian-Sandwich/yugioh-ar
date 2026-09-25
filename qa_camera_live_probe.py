"""Short browser probe of the real running camera, without modifying captures."""
import json,time,urllib.request,urllib.error
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parent
for attempt in range(30):
    try:
        with urllib.request.urlopen('http://127.0.0.1:8765/config',timeout=1) as response: response.read()
        break
    except (urllib.error.URLError,TimeoutError):
        if attempt==29: raise
        time.sleep(.5)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    page=browser.new_page(viewport={'width':1400,'height':1050});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('response',lambda r: print('analysis HTTP',r.status,flush=True) if '/analyze' in r.url else None)
    started=time.monotonic()
    page.goto('http://127.0.0.1:8765',wait_until='domcontentloaded')
    page.wait_for_function("Number(document.querySelector('#frame').dataset.frameNumber)>=3",timeout=15000)
    first=page.evaluate('frameNumber')
    first_hash=page.evaluate("async()=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await currentBlob.arrayBuffer()))).join(',')")
    try:
        page.wait_for_function("Number(document.querySelector('#detection').dataset.completed)>=2",timeout=30000)
    except Exception:
        print(page.evaluate('({configured,paused,frameNumber,lastAnalyzed,generation,resultAt,status:status.textContent,detection:detection.textContent})'),flush=True)
        page.screenshot(path=str(ROOT/'research/qa/camera-live-failure.png'))
        raise
    page.wait_for_function(f'frameNumber>={first+10}',timeout=15000)
    last_hash=page.evaluate("async()=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',await currentBlob.arrayBuffer()))).join(',')")
    result={'live':not page.evaluate('offline'),'frames_received':page.evaluate('frameNumber'),'completed_analyses':int(page.locator('#detection').get_attribute('data-completed')),
        'duration_seconds':round(time.monotonic()-started,2),'images_changed':first_hash!=last_hash,'status':page.locator('#status').inner_text(),'detection':page.locator('#detection').inner_text(),'javascript_errors':errors}
    result['quality_status']=page.locator('#qualityStatus').inner_text()
    result['quality_samples']=page.locator('.quality-card').count()
    assert 'No se pudo' not in result['quality_status'],result
    assert result['live'] and result['frames_received']>=13 and not errors,result
    page.screenshot(path=str(ROOT/'research/qa/camera-live.png'))
    (ROOT/'research/qa/camera-live-probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False),flush=True)
    browser.close()
