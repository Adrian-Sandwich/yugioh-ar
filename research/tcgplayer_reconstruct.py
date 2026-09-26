"""Reconstruct TCGplayer product metadata offline after the manifest loss of 2026-09-26.

Sources that survive without any request:
- the sitemap slug of every product (`yugioh-<set>-<card name>[-<rarity>]`);
- the registry: card names (EN) → card_id, and printings (card_id, product) →
  set code / printing number;
- the search metadata that was salvaged for a minority of products.

For each product: set name (matched against the 618 set names of the search
aggregation), card name and rarity from the slug, candidate card_ids by name,
and the printing number when the registry knows exactly one printing of that
card in that set. Fields the API alone provides (listed editions, prices)
stay empty. Output: downloads/tcgplayer-sample/reconstructed.json plus a
summary in research/qa/tcgplayer-sample/reconstruct.json.

    .venv-eval/Scripts/python.exe research/tcgplayer_reconstruct.py
"""
import collections, json, re, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from name_ocr import name_key

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'downloads/tcgplayer-sample'
OUT = ROOT / 'research/qa/tcgplayer-sample'
DB = ROOT / 'data/registry/registry.sqlite'
RARITIES = ['quarter century secret rare', 'prismatic secret rare', 'prismatic collectors rare', 'prismatic ultimate rare', 'platinum secret rare',
            'duel terminal technology ultra rare', 'duel terminal technology common', 'duel terminal normal parallel rare', 'duel terminal ultra parallel rare',
            'duel terminal super parallel rare', 'duel terminal rare parallel rare', 'premium gold rare', 'gold secret rare', 'collectors rare',
            'starlight rare', 'ultimate rare', 'ghost rare', 'secret rare', 'ultra rare', 'super rare', 'shatterfoil rare', 'starfoil rare',
            'mosaic rare', 'gold rare', 'platinum rare', 'parallel rare', 'short print', 'rare', 'common', 'ur', 'sr', 'scr', 'qcsr', 'pscr',
            'ghr', 'utr', 'cr', 'str', 'gr', 'ptr', 'shr', 'spr', 'mr', 'c', 'r']
ABBREV = {'ur': 'Ultra Rare', 'sr': 'Super Rare', 'scr': 'Secret Rare', 'qcsr': 'Quarter Century Secret Rare', 'pscr': 'Prismatic Secret Rare',
          'ghr': 'Ghost Rare', 'utr': 'Ultimate Rare', 'cr': "Collector's Rare", 'str': 'Starlight Rare', 'gr': 'Gold Rare', 'ptr': 'Platinum Rare',
          'shr': 'Shatterfoil Rare', 'spr': 'Starfoil Rare', 'mr': 'Mosaic Rare', 'c': 'Common', 'r': 'Rare'}


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))
    items = manifest['items']
    set_names = sorted({v['set_name'] for v in items.values() if v.get('set_name')})
    aggregation = ROOT / 'research/qa/tcgplayer-sample/set-names.json'
    if aggregation.exists():
        set_names = sorted(set(set_names) | set(json.loads(aggregation.read_text(encoding='utf-8'))))
    set_by_slug = {slugify(s): s for s in set_names}
    set_slugs = sorted(set_by_slug, key=len, reverse=True)
    rarity_suffixes = sorted(RARITIES, key=len, reverse=True)

    db = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=5)
    cards_by_name = collections.defaultdict(set)
    for card, name in db.execute("SELECT card_id, name FROM names WHERE language='en'"):
        cards_by_name[name_key(name)].add(card)
    # Set name → registry products (YGOJSON sets carry English names in names_json).
    products_by_set = collections.defaultdict(set)
    for pid, names_json in db.execute('SELECT id, names_json FROM products'):
        try:
            names = json.loads(names_json or '{}')
        except ValueError:
            continue
        for value in ([names] if isinstance(names, str) else names.values() if isinstance(names, dict) else []):
            if isinstance(value, str):
                products_by_set[slugify(value)].add(pid)
    numbers = collections.defaultdict(set)   # (product_id, card_id) → set codes
    codes_by_card_prefix = collections.defaultdict(set)  # (card_id, prefix) → codes, fallback when the product is unknown
    for card, product, code in db.execute('SELECT card_id, product_id, set_code FROM printings WHERE set_code IS NOT NULL'):
        if product:
            numbers[(product, card)].add(code)
        codes_by_card_prefix[(card, code.split('-')[0])].add(code)
    prefixes_by_set = collections.defaultdict(collections.Counter)
    for product, card in numbers:
        for code in numbers[(product, card)]:
            prefixes_by_set[product][code.split('-')[0]] += 1

    stats = collections.Counter(); rows = {}
    for key, item in items.items():
        slug = item.get('slug') or item.get('url', '').rsplit('/', 1)[-1]
        rec = {'product_id': item['product_id'], 'slug': slug, 'source': 'search' if item.get('number') else 'slug'}
        if item.get('number'):
            rec.update(set_name=item.get('set_name'), card_name=item.get('name'), rarity=item.get('rarity'), number=item.get('number'), number_source='search')
        else:
            body = slug[len('yugioh-'):] if slug.startswith('yugioh-') else slug
            set_slug = next((s for s in set_slugs if body.startswith(s + '-')), None)
            if not set_slug:
                stats['set_unmatched'] += 1; rec['set_name'] = None; rows[key] = rec; continue
            rest = body[len(set_slug) + 1:]
            rarity = None
            for suffix in rarity_suffixes:
                if rest.endswith('-' + slugify(suffix)) or rest == slugify(suffix):
                    rarity = ABBREV.get(suffix, suffix.title().replace("Collectors", "Collector's")); rest = rest[:-(len(slugify(suffix)) + 1)]; break
            rec.update(set_name=set_by_slug[set_slug], card_name=rest.replace('-', ' '), rarity=rarity, number=None, number_source=None)
        stats['set_matched'] += 1
        # TCGplayer names may carry the rarity or a variant in parentheses: "Blue-Eyes Abyss Dragon (UR)".
        plain_name = re.sub(r'\s*\([^)]*\)\s*$', '', rec.get('card_name') or '')
        card_ids = cards_by_name.get(name_key(plain_name), set())
        rec['card_ids'] = sorted(card_ids)
        if card_ids:
            stats['card_matched'] += 1
        if not rec.get('number') and card_ids:
            products = products_by_set.get(slugify(rec['set_name']), set())
            codes = {c for p in products for card in card_ids for c in numbers.get((p, card), ())}
            if not codes and products:
                prefixes = {pre for p in products for pre in prefixes_by_set.get(p, {})}
                codes = {c for card in card_ids for pre in prefixes for c in codes_by_card_prefix.get((card, pre), ())}
            # TCGplayer sells the English market: keep EN printings when the set has several locales.
            english = {c for c in codes if re.match(r'^[A-Z0-9]+-EN\d', c)} or {c for c in codes if re.match(r'^[A-Z0-9]+-E?\d', c)}
            if english:
                codes = english
            if len(codes) == 1:
                rec['number'] = next(iter(codes)); rec['number_source'] = 'registry'; stats['number_from_registry'] += 1
            elif codes:
                rec['number_candidates'] = sorted(codes); stats['number_ambiguous'] += 1
            else:
                stats['number_unknown'] += 1
        elif rec.get('number'):
            stats['number_from_search'] += 1
        rows[key] = rec
    # Numbers and passcodes read from the scans themselves (tcgplayer_scan_numbers.py).
    scans = BASE / 'scan-numbers.jsonl'
    if '--with-scans' in sys.argv and scans.exists():
        cards_by_passcode = collections.defaultdict(set)
        for card, value in db.execute("SELECT card_id, value FROM identifiers WHERE kind='passcode'"):
            cards_by_passcode[value].add(card)
        for line in scans.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            rec = rows.get(str(row.get('product_id')))
            if not rec or row.get('error'):
                continue
            code = row.get('set_code_read')
            if code and not rec.get('number_source') == 'search':
                candidates = rec.get('number_candidates') or []
                if row.get('set_status') != 'matched':
                    # The reader is literal: one confused glyph (GB1-001 for GBI-001, DL1S-EN010 for
                    # DL15-EN010) yields a code the registry has never seen. Keep it as evidence only.
                    rec['number_read_unverified'] = code; stats['scan_code_unverified'] += 1
                elif not candidates or code in candidates:
                    if rec.get('number') != code:
                        stats['number_from_scan'] += 1
                        if rec.get('number_source') == 'registry':
                            stats['registry_number_corrected_by_scan'] += 1
                    rec['number'] = code; rec['number_source'] = 'scan'; rec.pop('number_candidates', None)
                else:
                    rec['number_read_outside_candidates'] = code; stats['scan_disagrees_with_registry'] += 1
            if row.get('passcode'):
                rec['passcode_read'] = row['passcode']
                ids = cards_by_passcode.get(row['passcode'], set())
                if ids and not rec.get('card_ids'):
                    rec['card_ids'] = sorted(ids); rec['card_source'] = 'passcode'; stats['card_from_passcode'] += 1
        stats['numbers_resolved_total'] = sum(1 for r in rows.values() if r.get('number'))
        stats['cards_resolved_total'] = sum(1 for r in rows.values() if r.get('card_ids'))
    summary = {'products': len(items), **stats, 'note': 'Slug + registry reconstruction; editions and prices are not recoverable offline; numbers marked registry are inferred, not read from TCGplayer.'}
    (BASE / 'reconstructed.json').write_text(json.dumps({'summary': summary, 'items': rows}, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'reconstruct.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
