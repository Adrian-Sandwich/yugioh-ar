"""Local canonical catalog, explicit candidate links, and durable human reviews."""
import json
import re
import sqlite3
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data/catalog'
DB = DATA / 'catalog.sqlite'
REVIEWS = DATA / 'reviews.sqlite'
LANGS = ('es', 'en', 'de', 'fr', 'pt')


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def normalized(value):
    text = unicodedata.normalize('NFKD', value).casefold()
    return ''.join(c for c in text if c.isalnum())


def connect():
    conn = sqlite3.connect(DB.as_uri() + '?mode=ro', uri=True,factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute('ATTACH DATABASE ? AS review', (str(REVIEWS),))
    return conn


def init_reviews():
    DATA.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(REVIEWS,factory=ClosingConnection) as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS decisions (
            ref_id TEXT PRIMARY KEY, action TEXT NOT NULL, card_id TEXT,
            artwork_id TEXT, language TEXT, rarity TEXT, note TEXT, updated TEXT)''')


EFFECTIVE = '''SELECT r.*, CASE WHEN d.action='reject' THEN 'rejected'
 WHEN d.action='approve' THEN 'approved' ELSE r.status END AS effective_status,
 CASE WHEN d.action='approve' THEN d.card_id ELSE r.card_id END AS effective_card_id,
 CASE WHEN d.action='approve' THEN d.artwork_id ELSE r.artwork_id END AS effective_artwork_id,
 d.language AS printed_language, d.rarity AS reviewed_rarity, d.note AS review_note
 FROM refs r LEFT JOIN review.decisions d ON d.ref_id=r.ref_id'''


def asset_path(ref):
    path = (ROOT / ref['path']).resolve()
    if not path.is_relative_to((ROOT / 'downloads').resolve()):
        raise ValueError('Asset outside downloaded collection')
    return path


def review_reference(payload):
    ref_id, action = payload.get('ref_id'), payload.get('action')
    if action not in ('approve', 'reject', 'reset'):
        raise ValueError('Acción inválida')
    with connect() as conn:
        if not conn.execute('SELECT 1 FROM refs WHERE ref_id=?', (ref_id,)).fetchone():
            raise ValueError('Referencia inexistente')
        if action == 'approve' and not conn.execute('SELECT 1 FROM cards WHERE id=?', (payload.get('card_id'),)).fetchone():
            raise ValueError('Selecciona una identidad válida')
    if payload.get('language') not in (*LANGS, None, ''):
        raise ValueError('Idioma inválido')
    with sqlite3.connect(REVIEWS,factory=ClosingConnection) as conn:
        if action == 'reset':
            conn.execute('DELETE FROM decisions WHERE ref_id=?', (ref_id,))
        else:
            conn.execute('''INSERT OR REPLACE INTO decisions VALUES (?,?,?,?,?,?,?,datetime('now'))''',
                         (ref_id, action, payload.get('card_id'), payload.get('artwork_id') or None,
                          payload.get('language') or None, payload.get('rarity') or None, str(payload.get('note', ''))[:2000]))


def card_detail(conn, card_id):
    card = conn.execute('SELECT * FROM cards WHERE id=?', (card_id,)).fetchone()
    if not card:
        raise ValueError('Carta inexistente')
    result = dict(card)
    result['texts'] = json.loads(result.pop('texts_json'))
    result['refs'] = [dict(r) for r in conn.execute('SELECT * FROM (' + EFFECTIVE + ') WHERE effective_card_id=? ORDER BY kind,source,ref_id', (card_id,))]
    result['localizations'] = [dict(r) for r in conn.execute('SELECT * FROM localizations WHERE card_id=?', (card_id,))]
    return result


PILOT_REFS="r.kind='card' AND r.effective_status IN ('linked','approved') AND r.width>=200 AND r.height>=290"


def pilot_eligible(conn,card_id):
    """True if the card has a reference export_pilot accepts (the catalog UI disables the rest)."""
    return conn.execute('SELECT 1 FROM ('+EFFECTIVE+') r WHERE r.effective_card_id=? AND '+PILOT_REFS+' LIMIT 1',(card_id,)).fetchone() is not None


def export_full(target=ROOT/'data/full'):
    """Every identity the pilot could hold, one reference per artwork, in the pilot's
    format, for recognizing the whole catalog (vision_onnx with YUGIOH_SCOPE=full).

    Same filter and artwork rule as export_pilot; sprites are resolved with two
    queries instead of two per reference (~16k references).
    """
    import os
    init_reviews()
    with connect() as conn:
        available = [dict(r) for r in conn.execute('''SELECT c.id,c.name_en,c.name_es,c.category,r.ref_id,r.path,r.source_id,r.effective_artwork_id
            FROM (''' + EFFECTIVE + ''') r CROSS JOIN cards c
            WHERE c.id=r.effective_card_id AND ''' + PILOT_REFS + ''' ORDER BY r.width DESC,r.ref_id''')]
        sprites = conn.execute("SELECT effective_card_id,source_id,ref_id FROM (" + EFFECTIVE + ") WHERE kind='sprite' AND effective_status IN ('linked','approved') ORDER BY ref_id").fetchall()
    first_sprite, exact_sprite = {}, {}
    for card, source, ref in sprites:
        first_sprite.setdefault(card, ref); exact_sprite.setdefault((card, source), ref)
    catalog, cards, seen = [], {}, set()
    for ref in available:
        key = ref['id']; art = ref['effective_artwork_id'] or ref['ref_id']
        if (key, art) in seen:
            continue
        seen.add((key, art))
        name = ref['name_es'] or ref['name_en']
        cards.setdefault(key, {'card_id': key, 'name': name, 'category': ref['category']})
        catalog.append({'id': ref['ref_id'], 'card_id': key, 'artwork_id': art, 'name': name,
                        'source': os.path.relpath(ROOT / ref['path'], target).replace('\\', '/'),
                        'sprite_ref': exact_sprite.get((key, ref['source_id'])) or first_sprite.get(key), 'category': ref['category']})
    target.mkdir(parents=True, exist_ok=True)
    (target/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding='utf-8')
    (target/'selection.json').write_text(json.dumps(list(cards.values()), ensure_ascii=False, indent=1), encoding='utf-8')
    return {'cards': len(cards), 'references': len(catalog)}


def export_pilot(ids=None,max_artworks=None):
    """Only source-linked or human-approved references; never filename suggestions.

    `max_artworks` caps the distinct illustrations per identity (None: all).
    Foil printings of an alternate artwork scored 0.66-0.76 against a pilot
    that held only two of the six Dark Magician artworks (26/09/2026).
    """
    init_reviews()
    with connect() as conn:
        available = [dict(r) for r in conn.execute('''SELECT c.id,c.name_en,c.name_es,c.category,r.ref_id,r.path,r.source_id,r.effective_artwork_id
            FROM (''' + EFFECTIVE + ''') r CROSS JOIN cards c
            WHERE c.id=r.effective_card_id AND ''' + PILOT_REFS + ''' ORDER BY r.width DESC,r.ref_id''')]
        grouped = {}
        for ref in available:
            grouped.setdefault(ref['id'], []).append(ref)
        if ids is None:
            # Reproducible varied pilot, with familiar anchor cards when available.
            seeds = ['Blue-Eyes White Dragon','Dark Magician','Red-Eyes Black Dragon','Dark Magician Girl',
                     'Summoned Skull','Kuriboh','Cyber Dragon','Elemental HERO Neos','Stardust Dragon',
                     'Number 39: Utopia','Decode Talker','Odd-Eyes Pendulum Dragon','Monster Reborn',
                     'Dark Hole','Raigeki','Pot of Greed','Mirror Force','Torrential Tribute','Solemn Judgment']
            ids = []
            for name in seeds:
                ids.extend(k for k,v in grouped.items() if v[0]['name_en']==name and k not in ids)
            buckets = {}
            for key in sorted(grouped, key=lambda k: (grouped[k][0]['name_en'], k)):
                buckets.setdefault(grouped[key][0]['category'], []).append(key)
            while len(ids)<50 and any(buckets.values()):
                for bucket in buckets.values():
                    while bucket and bucket[0] in ids:
                        bucket.pop(0)
                    if bucket and len(ids)<50:
                        ids.append(bucket.pop(0))
        ids = list(dict.fromkeys(ids))
        if not 1 <= len(ids) <= 50:
            raise ValueError(f'Selecciona entre 1 y 50 cartas (hay {len(ids)}).')
        missing = [i for i in ids if i not in grouped]
        if missing:
            # Name the offending cards: a generic message hid which pick blocked the whole save.
            names = [(lambda r: (r['name_es'] or r['name_en']) if r else i)(conn.execute('SELECT name_en,name_es FROM cards WHERE id=?', (i,)).fetchone()) for i in missing]
            raise ValueError('No se guardó. Estas cartas no tienen una imagen enlazada de al menos 200 × 290 y no pueden entrar al piloto: ' + ', '.join(names))
        catalog, cards = [], []
        for key in ids:
            card = grouped[key][0]
            sprite = conn.execute('SELECT ref_id FROM (' + EFFECTIVE + ") WHERE effective_card_id=? AND kind='sprite' AND effective_status IN ('linked','approved') ORDER BY ref_id LIMIT 1", (key,)).fetchone()
            cards.append({'card_id':key,'name':card['name_es'] or card['name_en'],'category':card['category']})
            seen_art = set()
            for ref in grouped[key]:
                art = ref['effective_artwork_id'] or ref['ref_id']
                if art in seen_art:
                    continue
                seen_art.add(art)
                path = ROOT / ref['path']
                exact_sprite = conn.execute('SELECT ref_id FROM (' + EFFECTIVE + ") WHERE effective_card_id=? AND source_id=? AND kind='sprite' AND effective_status IN ('linked','approved') LIMIT 1",(key,ref['source_id'])).fetchone()
                import os
                entry = {'id':ref['ref_id'],'card_id':key,'artwork_id':art,'name':card['name_es'] or card['name_en'],
                         'source':os.path.relpath(path, ROOT/'data/pilot').replace('\\','/'),
                         'sprite_ref':exact_sprite[0] if exact_sprite else (sprite[0] if sprite else None),'category':card['category']}
                catalog.append(entry)
                if max_artworks is not None and len(seen_art)>=max_artworks:
                    break
        target = ROOT/'data/pilot'
        target.mkdir(parents=True, exist_ok=True)
        (target/'catalog.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
        (target/'selection.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2),encoding='utf-8')
        return {'cards':len(cards),'references':len(catalog),'selection':cards}
