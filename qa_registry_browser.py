"""Verify registry search and multilingual printing table in the actual browser."""
from pathlib import Path
from playwright.sync_api import sync_playwright
from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT=Path(__file__).resolve().parent
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless=True)
    page=browser.new_page(viewport={'width':1440,'height':1000})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:8769',wait_until='networkidle')
    page.locator('.card').first.click()
    page.locator('#detail').wait_for(state='visible')
    assert 'Dragón Blanco de Ojos Azules' in page.locator('#title').inner_text()
    page.locator('#lang').select_option('pt')
    page.wait_for_function("document.querySelector('#rows tr td:nth-child(2)')?.textContent.startsWith('pt')")
    assert page.locator('#rows tr').count()>10
    assert 'Dragão Branco de Olhos Azuis' in page.locator('#names').inner_text()
    page.screenshot(path=str(QA_OUT/'registry.png'),full_page=False)
    page.locator('#query').fill('LOB-EN001')
    page.locator('#searchMode').select_option('set')
    page.locator('#search button').click()
    page.wait_for_timeout(800)
    assert '89631139' in page.locator('#cards').inner_text()
    page.locator('#searchMode').select_option('passcode')
    page.locator('#query').fill('89631140')
    page.locator('#search button').click()
    page.wait_for_function("document.querySelector('#count').textContent.startsWith('0 cartas')")
    page.locator('#searchMode').select_option('all')
    page.locator('#query').fill('zzzznotacard98765')
    page.locator('#search button').click()
    page.wait_for_function("document.querySelector('#count').textContent.startsWith('0 cartas')")
    assert not errors,errors
    browser.close()
print('Registry browser: pass; screenshot .runtime/qa/registry.png')
