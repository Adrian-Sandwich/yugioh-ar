"""Browser checks for glare diagnostics, duplicate cards, expiry and original-image use."""
import json
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright
from camera_viewer import Server, Handler

ROOT = Path(__file__).resolve().parent

def main():
    server = Server(('127.0.0.1', 0), Handler)
    server.camera = 'http://127.0.0.1:1'
    server.recognizer = None
    server.mode = 'qa'
    server.fixture = ROOT / 'data/captures/carta-2026-09-25T04-15-19-512Z.jpg'
    server.overlay = None
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless=True)
            page = browser.new_page(viewport={'width': 1200, 'height': 900})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(f'http://127.0.0.1:{server.server_port}')
            page.wait_for_function('configured && frameNumber > 0')
            results = page.evaluate('''async () => {
              function check(x,msg){if(!x)throw Error(msg);}
              function fixture(glare=false, unknown=false){
                const c=document.createElement('canvas');c.width=500;c.height=300;
                const x=c.getContext('2d');x.fillStyle='#ddd';x.fillRect(0,0,500,300);
                x.fillStyle='#706040';x.fillRect(30,30,120,230);x.fillRect(300,30,120,230);
                if(glare){x.fillStyle='white';x.fillRect(50,70,75,90);}
                const candidates=[{corners:[[30,30],[150,30],[150,260],[30,260]]},{corners:[[300,30],[420,30],[420,260],[300,260]]}];
                return {image:c.toDataURL(), ar_image:'invalid-on-purpose', candidates,
                  detections:unknown?[]:candidates.map(d=>({...d,id:'same',card_id:'same',name:'Ojos Anómalos'}))};
              }
              const now=performance.now();
              await paintQuality(fixture(),now,generation);
              const ids=qualityTracks.map(t=>t.id);
              check(ids.length===2&&ids[0]!==ids[1],'Copies merged');
              await paintQuality(fixture(true),now+100,generation);
              check(qualityTracks.every((t,i)=>t.id===ids[i]),'Stationary copies lost IDs');
              check(qualityTracks[0].white>.1,'Glare not measured');
              check(qualityTracks[1].white===0,'Neighbor polluted');
              check(qualityTracks[0].best.at===now,'Cleaner historical crop not selected');
              check(qualityTracks[0].best.url!==qualityTracks[0].url,'Current substituted for best');
              const measured=qualityTracks[0].white;
              await paintQuality(fixture(true),now+11000,generation);
              check(qualityTracks[0].best.at===now+11000,'Expired best retained');
              await paintQuality(fixture(false,true),now+11100,generation);
              check(qualityTracks.every(t=>!t.identity&&t.history.length===1),'Unknown borrowed identity');
              await paintQuality({...fixture(),candidates:[],detections:[]},now+11200,generation);
              check(qualityTracks.length===0,'Absent card retained');
              await paintQuality(fixture(true),performance.now(),generation);
              const c=document.createElement('canvas');c.width=40;c.height=40;
              check(cardSample(c,[[0,0],[1,0],[1,1],[0,1]])===null,'Tiny crop accepted');
              return {duplicate_ids:ids,glare_fraction:measured,checks:8};
            }''')
            page.locator('#quality').scroll_into_view_if_needed()
            out = ROOT / 'research/qa/card-quality'
            out.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out/'browser.png'), full_page=True)
            assert not errors, errors
            (out/'validation.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
            print(json.dumps(results))
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

if __name__ == '__main__':
    main()
