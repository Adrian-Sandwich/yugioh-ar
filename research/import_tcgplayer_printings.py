"""Import TCGplayer printings (set code, rarity, edition, scan) into the registry as their own source.

After the full set crawl (27/09/2026) reconstructed.json holds, for 46,208
products, the exact printing number from TCGplayer's search plus a card
identity matched by name. The registry's `printings` table only knew YGOJSON,
Neuron and TDOANE observations; set codes that TCGplayer sells but those
sources lack made the set-code OCR answer "not in registry". This adds one
printing observation per product with source `tcgplayer:...`, evidence
(product id, local scan path, how the identity was matched) and the CDN
image URL. Only products with exactly one reconstructed identity and a
search-sourced number are imported; nothing existing is modified.

A consistent backup of the registry is written first with the SQLite backup
API (research/database-audit/registry-before-tcgplayer-<ts>.sqlite, ignored
by Git). Rollback: DELETE FROM printings WHERE source=<sid>; DELETE FROM
sources WHERE id=<sid>.

    .venv-eval/Scripts/python.exe -X utf8 research/import_tcgplayer_printings.py --dry-run
    .venv-eval/Scripts/python.exe -X utf8 research/import_tcgplayer_printings.py
"""
import argparse, collections, json, re, sqlite3, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from registry import DB, ROOT, connect, printing, source

BASE = ROOT / 'downloads/tcgplayer-sample'
LOCALES = {'EN': 'en', 'SP': 'es', 'DE': 'de', 'FR': 'fr', 'PT': 'pt', 'IT': 'it', 'JP': 'ja', 'KR': 'ko', 'AE': 'en', 'E': 'en', 'S': 'es', 'G': 'de', 'F': 'fr', 'P': 'pt', 'I': 'it', 'C': 'zh-CN', 'TC': 'zh-TW'}
CODE = re.compile(r'^([A-Z0-9]{2,10})-([A-Z]{1,2})?([0-9]{2,4})$')


def parse_code(code):
    m = CODE.match(code or '')
    if not m:
        return None, None
    locale = m.group(2)
    return locale, LOCALES.get(locale) if locale else None


def backup(db_path):
    out = ROOT / 'research/database-audit' / f"registry-before-tcgplayer-{time.strftime('%Y%m%d-%H%M%S')}.sqlite"
    out.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as src, sqlite3.connect(out) as dst:
        src.backup(dst)
    with sqlite3.connect(out) as check:
        assert check.execute('PRAGMA quick_check').fetchone()[0] == 'ok'
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    manifest_path = BASE / 'manifest.json'; rec_path = BASE / 'reconstructed.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))['items']
    rec = json.loads(rec_path.read_text(encoding='utf-8'))['items']
    sid = f"tcgplayer:reconstructed-{time.strftime('%Y%m%d')}"
    db = connect(DB)
    cards = {r[0] for r in db.execute('SELECT id FROM cards')}
    known_codes = {r[0] for r in db.execute('SELECT DISTINCT set_code FROM printings WHERE set_code IS NOT NULL')}
    stats = collections.Counter(); new_codes = set(); rows = []
    for key, r in rec.items():
        item = manifest.get(key) or {}
        ids = r.get('card_ids') or []
        if len(ids) != 1: stats['skip_identity'] += 1; continue
        if r.get('number_source') != 'search' or not r.get('number'): stats['skip_number'] += 1; continue
        if ids[0] not in cards: stats['skip_unknown_card'] += 1; continue
        locale, language = parse_code(r['number'])
        if locale is None and language is None and not CODE.match(r['number']): stats['skip_code_format'] += 1; continue
        if r['number'] not in known_codes: new_codes.add(r['number'])
        rows.append((key, ids[0], language, locale, r['number'], item.get('rarity') or r.get('rarity'), r.get('set_name') or item.get('set_name'),
                     item.get('image_url'), item.get('path'), r.get('card_source') or 'name', item.get('name') or r.get('card_name')))
        stats['import'] += 1
    stats['new_set_codes'] = len(new_codes)
    stats['by_language'] = dict(collections.Counter(x[2] or 'unknown' for x in rows))
    print(json.dumps({'source': sid, **{k: v for k, v in stats.items()}}, ensure_ascii=False, indent=1), flush=True)
    if args.dry_run:
        return
    saved = backup(DB)
    print('backup', saved, flush=True)
    source(db, sid, 'https://www.tcgplayer.com/search/yugioh/product', rec_path,
           {'products': len(rec), 'imported': len(rows), 'note': 'Printing observations from TCGplayer search metadata; identity matched by name (reconstructed.json). Scans stay local.'})
    for key, card, language, locale, code, rarity, set_name, image, path, how, name in rows:
        printing(db, sid, key, card, language=language, locale=locale, code=code, rarity=rarity, edition=None, image=image,
                 evidence={'product_id': int(key), 'set_name': set_name, 'scan_path': path, 'identity_source': how, 'product_name': name})
    db.commit()
    after = db.execute('SELECT COUNT(*) FROM printings WHERE source=?', (sid,)).fetchone()[0]
    print(json.dumps({'inserted': after, 'backup': str(saved.relative_to(ROOT))}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
