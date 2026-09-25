"""Copy useful local reference assets and inspect SQLite catalogs read-only."""
import collections
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path('C:/Yu-Gi-Oh! The Dawn of a New Era - YGOPRO 2')
GAME = SOURCE / 'YGOPRO'
OUT = ROOT / 'downloads' / 'tdoane-reference'
REPORT = ROOT / 'research' / 'tdoane'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    REPORT.mkdir(parents=True, exist_ok=True)
    selected = [p for p in (GAME / 'picture').rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg', '.png')]
    selected += list(GAME.rglob('*.cdb'))
    selected += [SOURCE / 'READ ME.txt', SOURCE / 'LICENSE.txt', GAME / 'LICENSE.txt', GAME / 'READ ME.txt', GAME / 'pack/pack.db']
    manifest = []
    dimensions = collections.defaultdict(collections.Counter)
    alpha = collections.Counter()
    decode_errors = []
    for index, src in enumerate(selected, 1):
        relative = src.relative_to(SOURCE)
        target = OUT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        original = src.read_bytes()
        digest = hashlib.sha256(original).hexdigest()
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            shutil.copy2(src, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise RuntimeError('Copy verification failed: ' + str(relative))
        entry = {'path': relative.as_posix(), 'bytes': len(original), 'sha256': digest}
        if src.suffix.lower() in ('.jpg', '.png'):
            image = cv2.imdecode(np.frombuffer(original, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
            if image is None:
                decode_errors.append(str(relative))
            else:
                h, w = image.shape[:2]
                entry.update(width=w, height=h)
                group = src.parent.name
                dimensions[group][f'{w}x{h}'] += 1
                if image.ndim == 3 and image.shape[2] == 4 and np.any(image[:, :, 3] < 255):
                    alpha[group] += 1
        manifest.append(entry)
        if index % 2000 == 0:
            print('COPIED AND VERIFIED', index, '/', len(selected), flush=True)
    databases = {}
    texts_by_lang = {}
    for dbpath in sorted(OUT.rglob('*.cdb')):
        with sqlite3.connect(dbpath.as_uri() + '?mode=ro', uri=True) as conn:
            names = dict(conn.execute('select id,name from texts'))
            ids = set(names)
            aliases = conn.execute('select id,alias from datas where alias<>0').fetchall()
            key = dbpath.relative_to(OUT).as_posix()
            databases[key] = {
                'texts_count': len(names), 'integrity': conn.execute('pragma quick_check').fetchone()[0],
                'nonzero_alias_count': len(aliases), 'alias_targets_absent': sum(a not in ids for _, a in aliases),
                'blue_eyes_name': names.get(89631139),
                'blue_eyes_aliases': [{'id': i, 'alias': a, 'name': names.get(i)} for i, a in aliases if a == 89631139],
            }
            if dbpath.parent.parent.name == 'MultiLanguage' and dbpath.parent.name != 'DeckEditor':
                texts_by_lang[dbpath.parent.name] = {row[0]: {'name': row[1], 'description': row[2]} for row in conn.execute('select id,name,desc from texts')}
    english = texts_by_lang['English']
    coverage = {}
    for language, items in texts_by_lang.items():
        common = set(english) & set(items)
        coverage[language] = {
            'ids': len(items), 'ids_shared_with_english': len(common),
            'names_equal_to_english': sum(items[i]['name'] == english[i]['name'] for i in common),
            'descriptions_equal_to_english': sum(items[i]['description'] == english[i]['description'] for i in common),
            'empty_names': sum(not v['name'] for v in items.values()),
        }
    image_ids = {int(p.stem) for p in (GAME / 'picture/card').iterdir() if p.is_file() and p.stem.isdigit()}
    all_ids = sorted(set().union(*(set(v) for v in texts_by_lang.values())))
    catalog = [{'source_id': i, 'localizations': {lang: items[i] for lang, items in texts_by_lang.items() if i in items}} for i in all_ids]
    report = {
        'source': str(SOURCE), 'copied_files': len(manifest), 'copied_bytes': sum(i['bytes'] for i in manifest),
        'image_dimensions': {k: dict(v.most_common()) for k, v in dimensions.items()},
        'images_with_transparency': dict(alpha), 'decode_errors': decode_errors, 'databases': databases,
        'language_coverage': coverage, 'portuguese_database_found': False,
        'card_image_numeric_ids': len(image_ids), 'card_image_ids_in_english': len(image_ids & set(english)),
        'card_image_ids_not_in_english': sorted(image_ids - set(english)),
        'english_ids_without_card_image': sorted(set(english) - image_ids),
        'note': 'Equal strings do not by themselves prove missing translations. Alias is simulator metadata, not a verified artwork or rarity label. Images are not validated as multilingual or official printings.',
    }
    for name, data in [('manifest.json', manifest), ('inspection.json', report), ('catalog-localized.json', catalog)]:
        (REPORT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('image_dimensions','databases','card_image_ids_not_in_english','english_ids_without_card_image')}, ensure_ascii=True), flush=True)
    print('COMMON DIMENSIONS', {k:v.most_common(3) for k,v in dimensions.items()}, flush=True)


if __name__ == '__main__':
    main()
