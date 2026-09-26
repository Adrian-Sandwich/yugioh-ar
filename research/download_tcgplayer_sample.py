"""Bounded exercise: product scans of Yu-Gi-Oh! singles currently listed for sale on TCGplayer.

Scope and manners, deliberately conservative:
- Uses the same search endpoint the public search page calls, filtered to
  single cards with live listings, a few pages only (`--pages`, default 5 x 24).
- Waits `--delay` seconds between search calls (default 10, the Crawl-Delay
  TCGplayer publishes in robots.txt) and about one image per second from the CDN.
- Keeps a resumable manifest with hashes and product metadata (product id, name,
  set, printing number, rarity, printing/edition of the listings, prices, url)
  and never rewrites a verified file. Creating STOP pauses the run.
- This is a research sample, not a mirror. Anything larger should go through
  TCGplayer's official API programme; see research/TCGPLAYER_MUESTRA.md.

    .venv-eval/Scripts/python.exe research/download_tcgplayer_sample.py [--pages 5] [--delay 10] [--audit]
"""
import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'downloads' / 'tcgplayer-sample'
STATE = OUT / 'manifest.json'
SEARCH = 'https://mp-search-api.tcgplayer.com/v1/search/request?q=&isList=false'
IMAGE = 'https://tcgplayer-cdn.tcgplayer.com/product/{id}_in_1000x1000.jpg'
PAGE = 24
AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) yugioh-ar-lab/0.1 (research sample; robots crawl-delay respected)'


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
    with request(SEARCH, json.dumps(body).encode()) as response:
        payload = json.load(response)
    result = payload['results'][0]
    return result.get('totalResults'), result['results']


def record(product):
    attributes = product.get('customAttributes') or {}
    listings = product.get('listings') or []
    return {'product_id': int(product['productId']), 'name': product.get('productName'), 'clean_name': product.get('productUrlName'),
            'set_name': product.get('setName'), 'set_code': product.get('setCode'), 'number': attributes.get('number'),
            'rarity': product.get('rarityName'), 'card_type': attributes.get('cardType'), 'release_date': attributes.get('releaseDate'),
            'printings_listed': sorted({l.get('printing') for l in listings if l.get('printing')}),
            'conditions_listed': sorted({l.get('condition') for l in listings if l.get('condition')}),
            'market_price': product.get('marketPrice'), 'lowest_price': product.get('lowestPrice'), 'total_listings': product.get('totalListings'),
            'url': f"https://www.tcgplayer.com/product/{int(product['productId'])}/{product.get('productLineUrlName', 'yugioh').lower()}-{product.get('setUrlName', '').lower().replace(' ', '-')}-{product.get('productUrlName', '').lower().replace(' ', '-')}",
            'image_url': IMAGE.format(id=int(product['productId'])), 'path': f"scans/{int(product['productId'])}.jpg"}


def save(state):
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
    try:
        with request(item['image_url']) as response:
            data = response.read()
        if not data.startswith(b'\xff\xd8'):
            raise ValueError('Not a JPEG')
        dest.write_bytes(data)
        item.update(status='ok', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), fetched_at=time.strftime('%Y-%m-%dT%H:%M:%S'), error=None)
    except urllib.error.HTTPError as exc:
        item.update(status='missing' if exc.code in (403, 404) else 'error', http=exc.code, error=f'HTTP {exc.code}')
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        item.update(status='error', error=str(exc))
    return item


def audit(state):
    import cv2
    import numpy as np
    counts = {}
    sizes = {}
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
    report = {'counts': counts, 'dimensions': {f'{h}x{w}': n for (h, w), n in sorted(sizes.items(), key=lambda kv: -kv[1])[:8]},
              'rarities': {}, 'sets': {}, 'audited_at': time.strftime('%Y-%m-%dT%H:%M:%S')}
    for item in state['items'].values():
        report['rarities'][item.get('rarity')] = report['rarities'].get(item.get('rarity'), 0) + 1
        report['sets'][item.get('set_code')] = report['sets'].get(item.get('set_code'), 0) + 1
    (OUT / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pages', type=int, default=5, help='Search pages of 24 in-stock singles to sample')
    parser.add_argument('--start', type=int, default=0, help='First page (0-based)')
    parser.add_argument('--delay', type=float, default=10.0, help='Seconds between search requests (robots.txt Crawl-Delay)')
    parser.add_argument('--image-delay', type=float, default=1.0)
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {
        'source': 'https://www.tcgplayer.com/search/yugioh/product?productLineName=yugioh&view=grid',
        'endpoint': SEARCH, 'image_pattern': IMAGE, 'robots_crawl_delay_s': 10,
        'note': 'Research sample of singles with live listings; product scans belong to TCGplayer/Konami and are not redistributed.',
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'pages': {}, 'items': {}}
    if args.audit:
        audit(state)
        return
    for page in range(args.start, args.start + args.pages):
        if (OUT / 'STOP').exists():
            print('STOP present; pausing', flush=True)
            break
        if str(page) in state['pages']:
            print(f'page {page} already sampled', flush=True)
        else:
            total, products = search(page)
            state['pages'][str(page)] = {'fetched_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'total_results_at_fetch': total,
                                        'product_ids': [int(p['productId']) for p in products]}
            for product in products:
                item = record(product)
                state['items'].setdefault(str(item['product_id']), {}).update(item)
                state['items'][str(item['product_id'])].setdefault('status', 'pending')
            save(state)
            print(f'page {page}: {len(products)} products, {total} in stock overall', flush=True)
        pending = [item for item in state['items'].values() if not verified(item) and item.get('status') != 'missing']
        for item in pending:
            if (OUT / 'STOP').exists():
                break
            fetch_image(item)
            time.sleep(args.image_delay)
        save(state)
        if page < args.start + args.pages - 1:
            time.sleep(args.delay)
    counts = {}
    for item in state['items'].values():
        counts[item.get('status')] = counts.get(item.get('status'), 0) + 1
    print('DONE', json.dumps(counts), flush=True)


if __name__ == '__main__':
    main()
