"""Browser annotation export, real importer and session leakage rejection."""
import hashlib,json,tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright
from research.yolo11_pose.import_annotations import collect,build

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT=Path(__file__).resolve().parent


def main():
    source=ROOT/'data/pose/bootstrap-v1/images/train/00001.jpg'
    with tempfile.TemporaryDirectory(dir=ROOT/'.runtime') as temporary:
        folder=Path(temporary);photo=folder/'test.jpg';photo.write_bytes(source.read_bytes())
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
            page=browser.new_page(viewport={'width':1200,'height':1200});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:8767/pose-annotator')
            page.locator('#imageFile').set_input_files(str(photo));page.wait_for_function("document.querySelector('#status').textContent.includes('0 cartas')")
            page.locator('#session').fill('qa-session');box=page.locator('#canvas').bounding_box()
            for x,y in ((.2,.2),(.6,.2),(.6,.8),(.2,.8)):
                page.mouse.click(box['x']+box['width']*x,box['y']+box['height']*y)
            page.locator('#reviewed').check()
            with page.expect_download() as download:page.locator('#export').click()
            target=folder/'test.jpg.pose.json';download.value.save_as(str(target))
            assert not errors,errors;browser.close()
        rows=collect(folder);assert len(rows)==1 and len(rows[0][2][0].split())==17
        result=build(folder,folder/'export');assert result['images']==1 and not result['train_ready']
        changed=json.loads(target.read_text());changed['reviewed']=False;target.write_text(json.dumps(changed))
        try:collect(folder)
        except ValueError:pass
        else:raise AssertionError('Unreviewed labels accepted')
        changed['reviewed']=True;target.write_text(json.dumps(changed))
        second=folder/'other.jpg';second.write_bytes(photo.read_bytes()+b' ')
        changed.update(image='other.jpg',image_sha256=hashlib.sha256(second.read_bytes()).hexdigest(),split='val')
        (folder/'other.jpg.pose.json').write_text(json.dumps(changed))
        try:collect(folder)
        except ValueError as exc:assert 'Session leaks' in str(exc)
        else:raise AssertionError('Session leaked across train/val')
    result={'status':'passed','checks':['browser clicks/export','17-field label','partial corpus not train-ready','unreviewed rejected','same session split rejected']}
    (QA_OUT/'pose-annotations.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))


if __name__=='__main__':main()
