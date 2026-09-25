"""Inventory and resume the public CardsOricaBR collection; standard library only."""
import concurrent.futures as cf
import hashlib
import json
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'downloads' / 'cardsoricabr'
STATE = OUT / 'manifest.json'
ROOT_ID = '1_AcddAI-MbuXIaaa5-VdzXLaw8ej7dmC'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            url = dict(attrs).get('href', '')
            match = re.search(r'drive\.google\.com/(?:file/d/|drive/folders/)([\w-]+)', url)
            if match:
                self.current = [match[1], '/drive/folders/' in url, []]

    def handle_data(self, data):
        if self.current:
            self.current[2].append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current:
            fid, folder, name = self.current
            self.items.append({'id': fid, 'folder': folder, 'name': ''.join(name).strip()})
            self.current = None


def request(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=60)


def safe(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).rstrip(' .')[:110] or 'unnamed'


def save(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATE)


def discover(folder):
    cache = OUT / 'listings' / (folder['id'] + '.html')
    if cache.exists():
        html = cache.read_text(encoding='utf-8')
    else:
        with request('https://drive.google.com/embeddedfolderview?id=' + folder['id']) as response:
            html = response.read().decode('utf-8')
        if 'flip-' not in html:
            raise ValueError('Unrecognized folder listing: ' + folder['id'])
        cache.write_text(html, encoding='utf-8')
    parser = Links()
    parser.feed(html)
    return list({item['id']: item for item in parser.items}.values())


def download(item):
    dest = OUT / item['path']
    if item.get('status') == 'ok' and dest.exists():
        data = dest.read_bytes()
        if len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256']:
            return item
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            with request('https://drive.usercontent.google.com/download?export=download&id=' + item['id']) as response:
                data = response.read()
                if 'text/html' in response.headers.get('Content-Type', '') or not data:
                    raise ValueError('HTML/empty response instead of file; permission/quota/confirmation may be required')
                expected = response.headers.get('Content-Length')
                if expected and int(expected) != len(data):
                    raise ValueError('Incomplete response')
            temp = dest.with_suffix(dest.suffix + '.part')
            temp.write_bytes(data)
            temp.replace(dest)
            return dict(item, status='ok', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), error=None)
        except Exception as exc:
            error = str(exc)
            if attempt < 3:
                time.sleep(2 ** (attempt + 1))
    return dict(item, status='error', error=error)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'listings').mkdir(exist_ok=True)
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {
        'source': 'https://www.deviantart.com/cardsoricabr/art/Yugioh-DataBase-Images-17-500-Cards-976699742',
        'root_id': ROOT_ID, 'folders': {ROOT_ID: {'id': ROOT_ID, 'path': '', 'listed': False}}, 'files': {}}
    while True:
        pending = [f for f in state['folders'].values() if not f.get('listed')]
        if not pending:
            break
        with cf.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(discover, f): f for f in pending}
            for future in cf.as_completed(futures):
                parent = futures[future]
                for item in future.result():
                    if item['folder']:
                        state['folders'].setdefault(item['id'], dict(item, path=parent['path'] + '/' + safe(item['name']), listed=False))
                    else:
                        # Drive ID prevents collisions, reserved names and duplicate filenames.
                        state['files'].setdefault(item['id'], dict(item, source_path=parent['path'], path='files/' + item['id'] + '__' + safe(item['name']), status='pending'))
                parent['listed'] = True
                save(state)
                print('INVENTORY', sum(f.get('listed', False) for f in state['folders'].values()), '/', len(state['folders']), 'folders;', len(state['files']), 'files', flush=True)
    state['discovery_complete'] = True
    save(state)
    print('DOWNLOAD', len(state['files']), 'files', flush=True)
    with cf.ThreadPoolExecutor(max_workers=24) as pool:
        futures = [pool.submit(download, item) for item in state['files'].values()]
        for count, future in enumerate(cf.as_completed(futures), 1):
            item = future.result()
            state['files'][item['id']] = item
            if count % 50 == 0 or item['status'] != 'ok':
                save(state)
                ok = sum(i['status'] == 'ok' for i in state['files'].values())
                errors = sum(i['status'] == 'error' for i in state['files'].values())
                print('PROGRESS', count, '/', len(futures), 'verified', ok, 'errors', errors, flush=True)
    state['download_complete'] = all(i['status'] == 'ok' for i in state['files'].values())
    state['total_bytes'] = sum(i.get('bytes', 0) for i in state['files'].values() if i['status'] == 'ok')
    save(state)
    print('FINISHED', state['download_complete'], state['total_bytes'], 'bytes', flush=True)


if __name__ == '__main__':
    main()
