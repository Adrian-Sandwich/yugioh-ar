"""Download Creative Commons photos of Yu-Gi-Oh! cards from Openverse for YOLO11 labeling.

Openverse (api.openverse.org) indexes openly licensed images from Flickr,
Wikimedia Commons and others; anonymous access needs no account. Every image is
kept with its license, creator and landing page (CC licenses require
attribution; NC/ND licenses allow this non-commercial research use but not
redistribution of modified images, so the files stay out of Git).

Results are mixed: duels and tournaments, but also icons, magazines and fan
art. Nothing is filtered here; labeling decides which photos have cards (four
corners) and which serve as negatives.

    .venv-eval/Scripts/python.exe research/download_openverse.py [--min-side 480]

Resumable: manifest.json keyed by Openverse id; files already verified are kept.
"""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'downloads' / 'internet-photos' / 'openverse'
API = 'https://api.openverse.org/v1/images/'
AGENT = 'yugioh-ar-lab/0.1 (research; card corner labeling; attribution kept)'
QUERIES = ('yugioh cards', 'yu-gi-oh cards', 'yugioh duel', 'yugioh tournament', 'yu-gi-oh card game', 'yugioh deck',
           'yu-gi-oh tournament', 'yugioh playmat', 'yu-gi-oh duel monsters cards', 'trading card game yugioh', 'yugioh regional')


def get(url, binary=False, tries=4):
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': AGENT}), timeout=60) as r:
                data = r.read(); return data if binary else json.loads(data)
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 410, 403): raise
            time.sleep(5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(3 * (attempt + 1))
    raise OSError('sin respuesta: ' + url)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--min-side', type=int, default=480, help='skip images whose shorter side is smaller (Openverse metadata)')
    parser.add_argument('--delay', type=float, default=1.0, help='seconds between requests')
    args = parser.parse_args()
    (OUT / 'images').mkdir(parents=True, exist_ok=True)
    state_path = OUT / 'manifest.json'
    state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'source': API, 'terms': 'https://docs.openverse.org/terms_of_service.html', 'items': {}}
    found = 0
    for query in QUERIES:
        page = 1
        while True:
            try: data = get(API + '?' + urllib.parse.urlencode({'q': query, 'page_size': 20, 'page': page}))
            except urllib.error.HTTPError: break  # past the last anonymous page
            time.sleep(args.delay)
            for r in data.get('results', []):
                item = state['items'].setdefault(r['id'], {'queries': []})
                if query not in item['queries']: item['queries'].append(query)
                item.update({k: r.get(k) for k in ('title', 'creator', 'creator_url', 'license', 'license_version', 'license_url', 'provider', 'source',
                                                   'foreign_landing_url', 'url', 'width', 'height', 'attribution', 'filetype')})
                found += 1
            if page >= data.get('page_count', 1): break
            page += 1
        print(f'{query!r}: {sum(query in i["queries"] for i in state["items"].values())} imágenes', flush=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    done = skipped = failed = 0
    for key, item in state['items'].items():
        if item.get('status') == 'ok' and (OUT / item['path']).exists(): done += 1; continue
        w, h = item.get('width') or 0, item.get('height') or 0
        if w and h and min(w, h) < args.min_side: item['status'] = 'small'; skipped += 1; continue
        ext = (item.get('filetype') or item['url'].rsplit('.', 1)[-1].split('?')[0] or 'jpg').lower()[:4]
        path = f'images/{key}.{ext}'
        try:
            data = get(item['url'], binary=True)
            if not (data[:2] == b'\xff\xd8' or data[:8] == b'\x89PNG\r\n\x1a\n' or data[:4] == b'RIFF'):
                raise ValueError('no es imagen')
            (OUT / path).write_bytes(data)
            item.update(status='ok', path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest()); done += 1
        except (urllib.error.HTTPError, OSError, ValueError) as exc:
            item.update(status='error', error=str(exc)[:200]); failed += 1
        time.sleep(args.delay)
        if (done + failed) % 25 == 0: state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    licenses = {}
    for item in state['items'].values():
        if item.get('status') == 'ok': licenses[item['license']] = licenses.get(item['license'], 0) + 1
    print(json.dumps({'encontradas': len(state['items']), 'descargadas': done, 'pequeñas': skipped, 'errores': failed, 'licencias': licenses}, ensure_ascii=False))


if __name__ == '__main__':
    main()
