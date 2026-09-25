"""Headless Edge smoke checks and screenshots of the actual local interfaces."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'research/qa'
OUT.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8768',wait_until='networkidle')
    page.locator('#query').fill('Dragão Branco de Olhos Azuis')
    page.locator('#search').click()
    blue=page.locator('#grid .tile').filter(has=page.get_by_role('heading',name='Dragón Blanco de Ojos Azules',exact=True))
    blue.get_by_role('button',name='Ver artes',exact=True).click()
    page.locator('#detail').wait_for(state='visible')
    page.wait_for_timeout(1000)
    assert page.locator('#detail .tile').count()>2
    page.locator('#detail .tile button').first.click()
    page.locator('#review').wait_for(state='visible')
    page.locator('#identity option').first.wait_for(state='attached')
    page.get_by_role('button',name='Cancelar',exact=True).click()
    page.screenshot(path=str(OUT/'catalog.png'),full_page=False)
    page.goto('http://127.0.0.1:8768/capture',wait_until='networkidle')
    page.locator('#file').set_input_files(str(ROOT/'data/captures/carta-2026-09-25T04-13-54-278Z.jpg'))
    page.wait_for_function("document.querySelector('#canvas').width===1920")
    page.locator('#canvas').click(position={'x':100,'y':100})
    assert page.locator('#points').inner_text()=='1/4 esquinas'
    page.locator('#clear').click()
    assert page.locator('#points').inner_text()=='0/4 esquinas'
    page.screenshot(path=str(OUT/'capture.png'),full_page=False)
    page.goto('http://127.0.0.1:8767',wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#detection').textContent.includes('confirmada')",timeout=90000)
    assert 'no es vídeo en vivo' in page.locator('#source').inner_text()
    page.locator('#pause').click()
    page.screenshot(path=str(OUT/'viewer.png'),full_page=False)
    assert not errors,errors
    browser.close()
print('PASS: multilingual search, variants, review dialog, capture UI, offline AR viewer; no JavaScript errors')
