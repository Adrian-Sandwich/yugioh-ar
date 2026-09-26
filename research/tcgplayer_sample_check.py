"""Exercise: run the local readers on the TCGplayer sample scans and cross-check the registry.

Each scan carries a known printing number (set code) and name from the listing
metadata. The readers get the whole scan resized to the rectified card size, so
this measures reading on clean, frontal, well-lit prints: an upper bound, not
camera performance. Output: qa/tcgplayer-sample/check.json.
"""
import json, sqlite3, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2, numpy as np
from passcode_ocr import NumberReader, SIZE, DB
from name_ocr import name_key

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'downloads/tcgplayer-sample'
OUT = ROOT / 'research/qa/tcgplayer-sample'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))['items']
    db = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=2)
    reader = NumberReader()
    rows = []; stats = {'scans': 0, 'set_code_read_exact': 0, 'set_code_in_registry': 0, 'name_matched_registry': 0, 'name_agrees_listing': 0,
                        'passcode_read': 0, 'passcode_consistent_with_registry': 0, 'ms': []}
    for key, item in items.items():
        if item.get('status') != 'ok':
            continue
        image = cv2.imread(str(BASE / item['path']))
        card = cv2.resize(image, SIZE, interpolation=cv2.INTER_AREA)
        started = time.perf_counter()
        best, ambiguous, _ = reader.read(card)
        title = reader.read_name(card)
        printing = reader.read_set(card)
        ms = round((time.perf_counter() - started) * 1000)
        number = item.get('number') or ''
        registry_cards = [r[0] for r in db.execute('SELECT DISTINCT card_id FROM printings WHERE set_code=?', (number,))]
        listing_key = name_key(item['name'] or '')
        title_ids = {m['card_id'] for m in title.get('matches', [])}
        passcode = best['passcode'] if best and best['score'] >= .85 and not ambiguous else None
        passcode_ids = [r[0] for r in db.execute("SELECT DISTINCT card_id FROM identifiers WHERE kind='passcode' AND value=?", (passcode,))] if passcode else []
        row = {'product_id': item['product_id'], 'name': item['name'], 'number': number, 'rarity': item['rarity'],
               'set_read': printing.get('code'), 'set_status': printing.get('status'), 'set_exact': printing.get('code') == number,
               'number_in_registry': bool(registry_cards),
               'name_read': title.get('text'), 'name_status': title.get('status'), 'name_agrees_listing': name_key(title.get('text') or '') == listing_key,
               'passcode_read': passcode, 'passcode_score': best['score'] if best else None,
               'passcode_consistent': bool(passcode_ids) and (not registry_cards or bool(set(passcode_ids) & set(registry_cards))), 'ms': ms}
        stats['scans'] += 1; stats['set_code_read_exact'] += row['set_exact']; stats['set_code_in_registry'] += row['number_in_registry']
        stats['name_matched_registry'] += title.get('status') == 'matched'; stats['name_agrees_listing'] += row['name_agrees_listing']
        stats['passcode_read'] += passcode is not None; stats['passcode_consistent_with_registry'] += row['passcode_consistent']; stats['ms'].append(ms)
        rows.append(row); print(json.dumps({k: row[k] for k in ('number', 'set_read', 'set_status', 'name_read', 'name_status', 'passcode_read', 'passcode_consistent', 'ms')}, ensure_ascii=False), flush=True)
    ms = sorted(stats['ms']); stats['ms'] = {'min': ms[0], 'median': ms[len(ms) // 2], 'max': ms[-1]} if ms else None
    stats['note'] = 'Clean frontal scans resized to the rectified card size; registry snapshot from YGOJSON April 2026 lacks recent sets.'
    print('STATS', json.dumps(stats, ensure_ascii=False, indent=1))
    (OUT / 'check.json').write_text(json.dumps({'stats': stats, 'rows': rows}, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
