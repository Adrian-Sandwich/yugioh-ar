"""TCGplayer Yu-Gi-Oh! product scans: bounded sample or full, rate-limited crawl.

Two sources, both resumable through one manifest (downloads/tcgplayer-sample/manifest.json):
- `--pages N` / `--all`: the search endpoint the public grid page calls, filtered
  to single cards with live listings. Gives metadata (product id, name, set,
  printing number, rarity, listed editions, prices). One request every
  `--delay` seconds (default 10, the Crawl-Delay published in robots.txt).
- `--sitemap`: product ids from sitemap/yugioh.0.xml and yugioh.1.xml, the
  crawler-facing list TCGplayer publishes (all products, including sealed and
  out-of-stock). Only the URL slug is known for those.

Images come from the CDN pattern `product/<id>_in_1000x1000.jpg` through a
small worker pool paced by `--image-rate` requests per second, in parallel
with the page crawl. Files that verified by hash are never fetched again; a
STOP file pauses everything. Scans belong to TCGplayer/Konami and stay local.

    .venv-eval/Scripts/python.exe research/download_tcgplayer_sample.py --pages 5
    .venv-eval/Scripts/python.exe research/download_tcgplayer_sample.py --all --image-rate 3
    .venv-eval/Scripts/python.exe research/download_tcgplayer_sample.py --sitemap --image-rate 3
    .venv-eval/Scripts/python.exe research/download_tcgplayer_sample.py --audit
"""
import argparse
import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'downloads' / 'tcgplayer-sample'
STATE = OUT / 'manifest.json'
SEARCH = 'https://mp-search-api.tcgplayer.com/v1/search/request?q=&isList=false'
SITEMAPS = ['https://www.tcgplayer.com/sitemap/yugioh.0.xml', 'https://www.tcgplayer.com/sitemap/yugioh.1.xml']
IMAGE = 'https://tcgplayer-cdn.tcgplayer.com/product/{id}_in_1000x1000.jpg'
PAGE = 24
AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) yugioh-ar-lab/0.1 (research sample; robots crawl-delay respected)'
LOCK = threading.Lock()


def request(url, data=None):
    headers = {'User-Agent': AGENT, 'Referer': 'https://www.tcgplayer.com/', 'Origin': 'https://www.tcgplayer.com'}
    if data is not None:
        headers['Content-Type'] = 'application/json'
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=60)


def search(page):
    body = {'algorithm': 'sales_synonym_v2', 'from': page * PAGE, 'size': PAGE,
            'filters': {'term': {'productLineName': ['yugioh'], 'productTypeName': ['Cards']}, 'range': {}, 'match': {}},
            'listingSearch': {'context': {'cart': {}}, 'filters': {'term': {'sellerStatus': 'Live', 'channelId': 0},
                              'range': {'quantity': {'gte': 1}}, 'exclude': {'channelExclusion': 0}}},
            'context': {'cart': {}, 'shippingCountry': 'US'}, 'settings': {'useFuzzySearch': True, 'didYouMean': {}}, 'sort': {}}
    for attempt in range(4):
        try:
            with request(SEARCH, json.dumps(body).encode()) as response:
                payload = json.load(response)
            result = payload['results'][0]
            return result.get('totalResults'), result['results']
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError) as exc:
            print(f'search page {page} attempt {attempt + 1}: {exc}', flush=True)
            time.sleep(30 * (attempt + 1))
    raise RuntimeError(f'search page {page} failed repeatedly')


def record(product):
    attributes = product.get('customAttributes') or {}
    listings = product.get('listings') or []
    pid = int(product['productId'])
    return {'product_id': pid, 'name': product.get('productName'), 'clean_name': product.get('productUrlName'),
            'set_name': product.get('setName'), 'set_code': product.get('setCode'), 'number': attributes.get('number'),
            'rarity': product.get('rarityName'), 'card_type': attributes.get('cardType'), 'release_date': attributes.get('releaseDate'),
            'printings_listed': sorted({l.get('printing') for l in listings if l.get('printing')}),
            'conditions_listed': sorted({l.get('condition') for l in listings if l.get('condition')}),
            'market_price': product.get('marketPrice'), 'lowest_price': product.get('lowestPrice'), 'total_listings': product.get('totalListings'),
            'url': f"https://www.tcgplayer.com/product/{pid}/{product.get('productLineUrlName', 'yugioh').lower()}-{product.get('setUrlName', '').lower().replace(' ', '-')}-{product.get('productUrlName', '').lower().replace(' ', '-')}",
            'source': 'search', 'image_url': IMAGE.format(id=pid), 'path': f'scans/{pid}.jpg'}


def sitemap_records():
    items = {}
    for url in SITEMAPS:
        with request(url) as response:
            text = response.read().decode('utf-8')
        for loc, pid in re.findall(r'<loc>(https://www\.tcgplayer\.com/product/(\d+)/[^<]*)</loc>', text):
            pid = int(pid)
            items[pid] = {'product_id': pid, 'url': loc, 'slug': loc.rsplit('/', 1)[-1], 'source': 'sitemap',
                          'image_url': IMAGE.format(id=pid), 'path': f'scans/{pid}.jpg'}
    return items


def save(state):
    with LOCK:
        temp = STATE.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding='utf-8')
        temp.replace(STATE)


def verified(item):
    dest = OUT / item['path']
    if item.get('status') != 'ok' or not dest.exists():
        return False
    data = dest.read_bytes()
    return len(data) == item.get('bytes') and hashlib.sha256(data).hexdigest() == item.get('sha256')


def fetch_image(item):
    dest = OUT / item['path']
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with request(item['image_url']) as response:
                data = response.read()
            if not data.startswith(b'\xff\xd8'):
                raise ValueError('Not a JPEG')
            dest.write_bytes(data)
            item.update(status='ok', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), fetched_at=time.strftime('%Y-%m-%dT%H:%M:%S'), error=None)
            return item
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 404):
                item.update(status='missing', http=exc.code, error=f'HTTP {exc.code}')
                return item
            item.update(error=f'HTTP {exc.code}')
            time.sleep(10 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            item.update(error=str(exc))
            time.sleep(5 * (attempt + 1))
    item['status'] = 'error'
    return item


class ImagePool:
    """Background workers draining pending items at a shared rate."""
    def __init__(self, state, rate, workers=3):
        self.state = state; self.interval = 1.0 / rate; self.next_at = 0.0
        self.lock = threading.Lock(); self.stop = threading.Event(); self.done = 0
        self.threads = [threading.Thread(target=self.run, daemon=True) for _ in range(workers)]
        for t in self.threads:
            t.start()

    def take(self):
        with self.lock:
            for item in self.state['items'].values():
                if item.get('status', 'pending') == 'pending' and not item.get('_taken'):
                    item['_taken'] = True
                    return item
        return None

    def pace(self):
        with self.lock:
            start = max(time.monotonic(), self.next_at); self.next_at = start + self.interval
        time.sleep(max(0.0, start - time.monotonic()))

    def run(self):
        while not self.stop.is_set():
            if (OUT / 'STOP').exists():
                time.sleep(5); continue
            item = self.take()
            if item is None:
                time.sleep(2); continue
            self.pace(); fetch_image(item); item.pop('_taken', None)
            with self.lock:
                self.done += 1

    def idle(self):
        return not any(i.get('status', 'pending') == 'pending' for i in self.state['items'].values())


def audit(state):
    import cv2
    import numpy as np
    counts = {}; sizes = {}; sources = {}
    for item in state['items'].values():
        status = item.get('status', 'pending')
        if status == 'ok':
            if not verified(item):
                status = 'corrupt'
            else:
                image = cv2.imdecode(np.frombuffer((OUT / item['path']).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    status = 'corrupt'
                else:
                    sizes[image.shape[:2]] = sizes.get(image.shape[:2], 0) + 1
        counts[status] = counts.get(status, 0) + 1
        sources[item.get('source')] = sources.get(item.get('source'), 0) + 1
    report = {'counts': counts, 'sources': sources, 'with_metadata': sum(1 for i in state['items'].values() if i.get('number')),
              'dimensions': {f'{h}x{w}': n for (h, w), n in sorted(sizes.items(), key=lambda kv: -kv[1])[:8]},
              'rarities': {}, 'sets': {}, 'audited_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    for item in state['items'].values():
        if item.get('rarity'):
            report['rarities'][item['rarity']] = report['rarities'].get(item['rarity'], 0) + 1
        if item.get('set_code'):
            report['sets'][item['set_code']] = report['sets'].get(item['set_code'], 0) + 1
    report['sets'] = dict(sorted(report['sets'].items(), key=lambda kv: -kv[1])[:40])
    (OUT / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'sets'}, ensure_ascii=False, indent=2))


def summary(state):
    counts = {}
    for item in state['items'].values():
        counts[item.get('status', 'pending')] = counts.get(item.get('status', 'pending'), 0) + 1
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', type=int, default=5, help='Search pages of 24 in-stock singles to sample')
    parser.add_argument('--all', action='store_true', help='Crawl every search page of in-stock singles')
    parser.add_argument('--start', type=int, default=0, help='First page (0-based)')
    parser.add_argument('--sitemap', action='store_true', help='Add every product id from the Yu-Gi-Oh! sitemaps')
    parser.add_argument('--delay', type=float, default=10.0, help='Seconds between search requests (robots.txt Crawl-Delay)')
    parser.add_argument('--image-rate', type=float, default=1.0, help='CDN image requests per second')
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {
        'source': 'https://www.tcgplayer.com/search/yugioh/product?productLineName=yugioh&view=grid',
        'endpoint': SEARCH, 'sitemaps': SITEMAPS, 'image_pattern': IMAGE, 'robots_crawl_delay_s': 10,
        'note': 'Research sample of product scans; scans belong to TCGplayer/Konami and are not redistributed.',
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'pages': {}, 'items': {}}
    for item in state['items'].values():
        item.pop('_taken', None)
    if args.audit:
        audit(state); return
    if args.sitemap:
        added = 0
        for pid, item in sitemap_records().items():
            current = state['items'].setdefault(str(pid), {})
            if not current:
                current.update(item); current['status'] = 'pending'; added += 1
            else:
                current.setdefault('url', item['url']); current.setdefault('slug', item['slug'])
        save(state); print(f'sitemap: {added} new products, {len(state["items"])} total', flush=True)
    pool = ImagePool(state, args.image_rate)
    started = time.monotonic(); last_save = time.monotonic()
    try:
        if args.all or args.pages:
            page = args.start
            while True:
                if (OUT / 'STOP').exists():
                    print('STOP present; pausing crawl', flush=True); break
                if not args.all and page >= args.start + args.pages:
                    break
                if str(page) in state['pages']:
                    page += 1; continue
                total, products = search(page)
                state['pages'][str(page)] = {'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'total_results_at_fetch': total,
                                            'product_ids': [int(p['productId']) for p in products]}
                with LOCK:
                    for product in products:
                        item = record(product)
                        current = state['items'].setdefault(str(item['product_id']), {})
                        current.update({k: v for k, v in item.items() if k not in ('status',)})
                        current.setdefault('status', 'pending')
                save(state)
                print(f'page {page}: {len(products)} products, {total} in stock; images done {pool.done}, {summary(state)}, {(time.monotonic() - started) / 60:.0f} min', flush=True)
                if not products or (total is not None and (page + 1) * PAGE >= total):
                    break
                page += 1
                time.sleep(args.delay)
        while not pool.idle() and not (OUT / 'STOP').exists():
            time.sleep(15)
            if time.monotonic() - last_save > 60:
                save(state); last_save = time.monotonic()
                print(f'images done {pool.done}, {summary(state)}, {(time.monotonic() - started) / 60:.0f} min', flush=True)
    finally:
        pool.stop.set()
        for item in state['items'].values():
            item.pop('_taken', None)
        save(state)
    print('DONE', json.dumps(summary(state)), 'STOP present' if (OUT / 'STOP').exists() else '', flush=True)


if __name__ == '__main__':
    main()
