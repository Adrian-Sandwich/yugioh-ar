"""Link TCGplayer products (from the crawl manifest) to the registry by printing number.

Read-only on the registry. For every product with metadata: does its printing
number (`number`, e.g. MAMO-EN003) exist in `printings.set_code`? Does the
listed name match a registry name? Which set prefixes are unknown to the
registry (a direct measure of how stale the YGOJSON snapshot is)? Runs on a
partial manifest while the crawl continues. Output: qa/tcgplayer-sample/link.json.

    .venv-eval/Scripts/python.exe research/tcgplayer_registry_link.py
"""
import collections, json, sqlite3, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from name_ocr import name_key

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'downloads/tcgplayer-sample/manifest.json'
DB = ROOT / 'data/registry/registry.sqlite'
OUT = ROOT / 'research/qa/tcgplayer-sample'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    items = json.loads(MANIFEST.read_text(encoding='utf-8'))['items']
    db = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True, timeout=5)
    printings = collections.defaultdict(set)
    for code, card in db.execute('SELECT set_code, card_id FROM printings WHERE set_code IS NOT NULL'):
        printings[code].add(card)
    names = collections.defaultdict(set)
    for card, name in db.execute("SELECT card_id, name FROM names WHERE language='en'"):
        names[name_key(name)].add(card)
    prefixes_known = {code.split('-')[0] for code in printings}
    stats = {'products_total': len(items), 'with_metadata': 0, 'number_in_registry': 0, 'name_in_registry': 0, 'both_agree': 0,
             'number_unknown': 0, 'name_unknown': 0, 'unknown_prefixes': collections.Counter(), 'known_prefix_missing_number': collections.Counter(),
             'rarities': collections.Counter(), 'products_per_card': collections.Counter()}
    unknown_examples = []
    for item in items.values():
        number = item.get('number')
        if not number:
            continue
        stats['with_metadata'] += 1; stats['rarities'][item.get('rarity')] += 1
        cards_by_number = printings.get(number, set())
        cards_by_name = names.get(name_key(item.get('name') or ''), set())
        if cards_by_number:
            stats['number_in_registry'] += 1
            for card in cards_by_number:
                stats['products_per_card'][card] += 1
        else:
            stats['number_unknown'] += 1
            prefix = number.split('-')[0]
            if prefix in prefixes_known:
                stats['known_prefix_missing_number'][prefix] += 1
            else:
                stats['unknown_prefixes'][prefix] += 1
                if len(unknown_examples) < 12:
                    unknown_examples.append({'number': number, 'name': item.get('name'), 'set': item.get('set_name'), 'release': item.get('release_date')})
        if cards_by_name:
            stats['name_in_registry'] += 1
        else:
            stats['name_unknown'] += 1
        if cards_by_number and cards_by_name and cards_by_number & cards_by_name:
            stats['both_agree'] += 1
    per_card = stats.pop('products_per_card')
    report = {**{k: (dict(v.most_common(25)) if isinstance(v, collections.Counter) else v) for k, v in stats.items()},
              'cards_with_scan': len(per_card), 'products_per_card_max': max(per_card.values()) if per_card else 0,
              'unknown_examples': unknown_examples,
              'note': 'Partial while the crawl runs; number match is exact on set_code (registry snapshot YGOJSON 2026-04-07 plus Neuron).'}
    (OUT / 'link.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rarities',)}, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
