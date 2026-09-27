"""Download and self-host YGOPRODeck images for registry illustrations.

YGOPRODeck asks not to hotlink images and blocks IPs above 20 requests/s; this
runs far below that limit, keeps a resumable manifest with hashes, and never
rewrites a file that already verified. Standard library only.

    .venv-eval/Scripts/python.exe research/download_ygoprodeck_art.py [--limit N] [--rate 6] [--audit]
    .venv-eval/Scripts/python.exe research/download_ygoprodeck_art.py --kind card --only-missing

--kind art (default): cropped artwork into downloads/ygoprodeck-art.
--kind card: the whole card (`artworks.card_url`, 421x614) into
downloads/ygoprodeck-cards; --only-missing limits it to cards without a catalog
image the pilot can use (catalog.PILOT_REFS), e.g. recent sets.

Priority: illustrations of pilot cards first, then the rest of the registry.
Create <output>/STOP to pause; delete it to resume.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# kind -> (output folder, artworks column with the URL, subfolder, source prefix)
KINDS = {'art': (ROOT / 'downloads' / 'ygoprodeck-art', 'art_url', 'art/', 'https://images.ygoprodeck.com/images/cards_cropped/'),
         'card': (ROOT / 'downloads' / 'ygoprodeck-cards', 'card_url', 'cards/', 'https://images.ygoprodeck.com/images/cards/')}
OUT = KINDS['art'][0]
STATE = OUT / 'manifest.json'
KIND = 'art'
REGISTRY = ROOT / 'data' / 'registry' / 'registry.sqlite'
AGENT = 'yugioh-ar-lab/0.1 (local research; images self-hosted, not hotlinked)'


class Limiter:
    """Minimum spacing between requests shared by all threads."""
    def __init__(self, per_second):
        self.interval = 1.0 / per_second
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_at)
            self.next_at = start + self.interval
        time.sleep(max(0.0, start - time.monotonic()))


def save(state):
    temp = STATE.with_suffix('.tmp')
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
    temp.replace(STATE)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding='utf-8'))
    what = 'Cropped artwork' if KIND == 'art' else 'Whole card image'
    return {'source': KINDS[KIND][3], 'terms': 'https://ygoprodeck.com/api-guide/', 'kind': KIND,
            'note': what + ' keyed by registry artwork id; url comes from the artworks table (YGOJSON snapshot).',
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'items': {}}


def cards_without_pilot_image():
    """Catalog identities with no reference export_pilot accepts."""
    import sys
    sys.path.insert(0, str(ROOT))
    from catalog import EFFECTIVE, PILOT_REFS, connect
    with connect() as conn:
        return {r[0] for r in conn.execute('SELECT c.id FROM cards c WHERE NOT EXISTS (SELECT 1 FROM (' + EFFECTIVE + ') r WHERE r.effective_card_id=c.id AND ' + PILOT_REFS + ')')}


def registry_items(state, only=None):
    _, column, folder, _ = KINDS[KIND]
    db = sqlite3.connect(REGISTRY.as_uri() + '?mode=ro', uri=True, timeout=5)
    try:
        rows = db.execute(f"SELECT id,card_id,image_source_id,art_url,card_url FROM artworks WHERE {column} IS NOT NULL AND {column}!='' ORDER BY id").fetchall()
    finally:
        db.close()
    pilot_path = ROOT / 'data' / 'pilot' / 'catalog.json'
    pilot = {e['card_id'] for e in json.loads(pilot_path.read_text(encoding='utf-8'))} if pilot_path.exists() else set()
    for art_id, card_id, source_id, art_url, card_url in rows:
        # Items already in the manifest stay there (and stay verified) even if the card has an image now.
        if only is not None and card_id not in only and art_id not in state['items']:
            continue
        url = art_url if KIND == 'art' else card_url
        # Some card_url point to Yugipedia and are square official artwork, not a card
        # image; keep to the source whose image guide this downloader follows.
        if KIND == 'card' and not url.startswith(KINDS['card'][3]):
            continue
        item = state['items'].setdefault(art_id, {})
        item.update(card_id=card_id, image_source_id=str(source_id), url=url, card_url=card_url,
                    path=folder + url.rsplit('/', 1)[-1], pilot=card_id in pilot)
        item.setdefault('status', 'pending')
    return sorted(state['items'].items(), key=lambda kv: (not kv[1]['pilot'], kv[0]))


def verified(item):
    dest = OUT / item['path']
    if item.get('status') != 'ok' or not dest.exists():
        return False
    data = dest.read_bytes()
    return len(data) == item.get('bytes') and hashlib.sha256(data).hexdigest() == item.get('sha256')


def fetch(item, limiter):
    dest = OUT / item['path']
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        limiter.wait()
        try:
            request = urllib.request.Request(item['url'], headers={'User-Agent': AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
                content_type = response.headers.get('Content-Type', '')
            # A few files are PNG served under a .jpg name; keep the bytes as served.
            if not (data.startswith(b'\xff\xd8') or data.startswith(b'\x89PNG\r\n\x1a\n')) or 'image' not in content_type:
                raise ValueError('Not a JPEG/PNG image: ' + content_type)
            dest.write_bytes(data)
            item.update(status='ok', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                        fetched_at=time.strftime('%Y-%m-%dT%H:%M:%S'), error=None)
            return item
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                item.update(status='missing', http=404, error='HTTP 404', fetched_at=time.strftime('%Y-%m-%dT%H:%M:%S'))
                return item
            if exc.code == 429 or exc.code >= 500:
                time.sleep(5 * (attempt + 1))
                item.update(error=f'HTTP {exc.code}')
                continue
            item.update(status='error', http=exc.code, error=f'HTTP {exc.code}')
            return item
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            item.update(error=str(exc))
            time.sleep(2 * (attempt + 1))
    item['status'] = 'error'
    return item


def audit(state):
    import cv2
    import numpy as np
    counts = {'ok': 0, 'missing': 0, 'error': 0, 'pending': 0, 'corrupt': 0}
    sizes = {}
    for art_id, item in state['items'].items():
        status = item.get('status', 'pending')
        if status == 'ok':
            if not verified(item):
                counts['corrupt'] += 1
                continue
            image = cv2.imdecode(np.frombuffer((OUT / item['path']).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                counts['corrupt'] += 1
                continue
            sizes[image.shape[:2]] = sizes.get(image.shape[:2], 0) + 1
        counts[status] = counts.get(status, 0) + 1
    report = {'counts': counts, 'dimensions': {f'{h}x{w}': n for (h, w), n in sorted(sizes.items(), key=lambda kv: -kv[1])[:10]},
              'audited_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    (OUT / 'audit.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit', type=int, default=0, help='Stop after this many new downloads (0 = all)')
    parser.add_argument('--rate', type=float, default=6.0, help='Requests per second, shared by all threads (site limit is 20)')
    parser.add_argument('--threads', type=int, default=4)
    parser.add_argument('--audit', action='store_true', help='Verify hashes and image decoding, then exit')
    parser.add_argument('--kind', choices=sorted(KINDS), default='art', help='art: cropped artwork; card: whole card image')
    parser.add_argument('--only-missing', action='store_true', help='Only cards without a catalog image the pilot can use')
    args = parser.parse_args()
    global OUT, STATE, KIND
    KIND = args.kind; OUT = KINDS[KIND][0]; STATE = OUT / 'manifest.json'
    OUT.mkdir(parents=True, exist_ok=True)
    state = load_state()
    if args.audit:
        audit(state)
        return
    items = registry_items(state, cards_without_pilot_image() if args.only_missing else None)
    todo = [item for _, item in items if not verified(item) and item.get('status') != 'missing']
    print(f'{len(items)} illustrations in registry; {len(todo)} to download ({sum(i["pilot"] for i in todo)} pilot first)', flush=True)
    if args.limit:
        todo = todo[:args.limit]
    limiter = Limiter(args.rate)
    done = 0
    started = time.monotonic()
    save(state)
    with cf.ThreadPoolExecutor(args.threads) as pool:
        pending = set()
        queue = iter(todo)
        while True:
            while len(pending) < args.threads * 2:
                if (OUT / 'STOP').exists():
                    break
                item = next(queue, None)
                if item is None:
                    break
                pending.add(pool.submit(fetch, item, limiter))
            if not pending:
                break
            finished, pending = cf.wait(pending, return_when=cf.FIRST_COMPLETED)
            done += len(finished)
            if done % 50 == 0 or done == len(todo):
                save(state)
                counts = {}
                for _, item in items:
                    counts[item.get('status', 'pending')] = counts.get(item.get('status', 'pending'), 0) + 1
                elapsed = time.monotonic() - started
                print(f'{done}/{len(todo)} this run, {elapsed:.0f} s, {done / max(elapsed, 1e-9):.1f}/s; totals {counts}', flush=True)
    save(state)
    counts = {}
    for _, item in items:
        counts[item.get('status', 'pending')] = counts.get(item.get('status', 'pending'), 0) + 1
    print('DONE', json.dumps(counts), 'STOP present' if (OUT / 'STOP').exists() else '', flush=True)


if __name__ == '__main__':
    main()
