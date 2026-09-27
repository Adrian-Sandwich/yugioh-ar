"""Card sheet for a recognized identity, from the local registry (no network).

Game facts come from YGOJSON (`card_facts`): card type, attribute, monster type,
level/rank/link, ATK/DEF, classifications, legality (TCG, OCG, Speed, Genesys
points) and Master Duel / Duel Links rarity. Names and effect texts come from
`names` in five languages, preferring Konami's Neuron database over YGOJSON.
The duel engine takes ATK, DEF and level from the same sheet.
"""
import json
import sqlite3
import threading
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REGISTRY = ROOT / 'data/registry/registry.sqlite'
LANGS = ('es', 'en', 'de', 'fr', 'pt')

ATTRIBUTES = {'dark': 'OSCURIDAD', 'light': 'LUZ', 'earth': 'TIERRA', 'water': 'AGUA', 'fire': 'FUEGO', 'wind': 'VIENTO', 'divine': 'DIVINIDAD'}
TYPES = {'aqua': 'Aqua', 'beast': 'Bestia', 'beastwarrior': 'Guerrero-Bestia', 'creatorgod': 'Dios Creador', 'cyberse': 'Ciberso',
         'dinosaur': 'Dinosaurio', 'divinebeast': 'Bestia Divina', 'dragon': 'Dragón', 'fairy': 'Hada', 'fiend': 'Demonio', 'fish': 'Pez',
         'illusion': 'Ilusión', 'insect': 'Insecto', 'machine': 'Máquina', 'plant': 'Planta', 'psychic': 'Psíquico', 'pyro': 'Piro',
         'reptile': 'Reptil', 'rock': 'Roca', 'seaserpent': 'Serpiente Marina', 'spellcaster': 'Lanzador de Conjuros', 'thunder': 'Trueno',
         'warrior': 'Guerrero', 'wingedbeast': 'Bestia Alada', 'wyrm': 'Wyrm', 'zombie': 'Zombi'}
CLASSES = {'normal': 'Normal', 'effect': 'Efecto', 'fusion': 'Fusión', 'ritual': 'Ritual', 'synchro': 'Sincronía', 'xyz': 'Xyz',
           'pendulum': 'Péndulo', 'link': 'Link', 'tuner': 'Cantante', 'flip': 'Volteo', 'spirit': 'Espíritu', 'union': 'Unión',
           'gemini': 'Géminis', 'toon': 'Toon', 'token': 'Ficha', 'specialsummon': 'Invocación Especial'}
SUBCATEGORIES = {'normal': 'Normal', 'continuous': 'Continua', 'quickplay': 'de Juego Rápido', 'equip': 'de Equipo', 'field': 'de Campo',
                 'ritual': 'de Ritual', 'counter': 'de Contraefecto'}
LEGALITY = {'unlimited': 'Ilimitada', 'semilimited': 'Semilimitada', 'limited': 'Limitada', 'forbidden': 'Prohibida', 'unreleased': 'Sin publicar'}

_local = threading.local()


def _db():
    # One read-only connection per thread: the viewer serves requests from a thread pool.
    if getattr(_local, 'db', None) is None:
        _local.db = sqlite3.connect(REGISTRY.resolve().as_uri() + '?mode=ro', uri=True, timeout=5)
    return _local.db


def _key(value):
    return ''.join(ch for ch in str(value).lower() if ch.isalnum())


@lru_cache(maxsize=4096)
def card_sheet(card_id):
    """Sheet for one registry identity, or None if the registry does not know it."""
    db = _db()
    row = db.execute('SELECT facts_json FROM card_facts WHERE card_id=?', (card_id,)).fetchone()
    if row is None:
        return None
    facts = json.loads(row[0])
    texts = {}
    # Name and effect are chosen separately: some Neuron rows carry the name only.
    for language, name, description, source in db.execute(
            "SELECT language,name,description,source FROM names WHERE card_id=? ORDER BY CASE WHEN source LIKE 'neuron:%' THEN 0 ELSE 1 END,source", (card_id,)):
        if language not in LANGS: continue
        entry = texts.setdefault(language, {'name': name, 'effect': None, 'source': source.split(':')[0]})
        if entry['effect'] is None and (description or '').strip():
            # Sources mark line breaks (materials line, then effect) with <br>.
            entry['effect'] = description.replace('<br>', '\n').replace('\r', '').strip(); entry['effect_source'] = source.split(':')[0]
    kind = facts.get('cardType')
    line = []
    if kind == 'monster':
        # Summon types (synchro, xyz, link...) live in monsterCardTypes, the rest in classifications.
        classes = [CLASSES.get(_key(c), c) for c in facts.get('monsterCardTypes', []) + facts.get('classifications', [])]
        line = ['Monstruo ' + ' / '.join(classes) if classes else 'Monstruo', TYPES.get(_key(facts.get('type', '')), facts.get('type')),
                ATTRIBUTES.get(facts.get('attribute'), facts.get('attribute'))]
        if facts.get('linkArrows'): line.append(f"LINK-{len(facts['linkArrows'])}")
        elif facts.get('rank') is not None: line.append(f"Rango {facts['rank']}")
        elif facts.get('level') is not None: line.append(f"Nivel {facts['level']}")
        if facts.get('scale') is not None: line.append(f"Escala {facts['scale']}")
    elif kind in ('spell', 'trap'):
        line = [('Magia ' if kind == 'spell' else 'Trampa ') + SUBCATEGORIES.get(facts.get('subcategory'), facts.get('subcategory') or '')]
    else:
        line = [kind or 'Desconocida']
    legality = {}
    for fmt, value in (facts.get('legality') or {}).items():
        state = value.get('current') or value.get('currentLegality')
        legality[fmt] = {'estado': LEGALITY.get(state, state), 'puntos': value.get('currentPoints')}
    display = texts.get('es') or texts.get('en') or next(iter(texts.values()), {'name': card_id, 'effect': None})
    return {'card_id': card_id, 'name': display['name'], 'name_en': texts.get('en', {}).get('name'), 'effect': display['effect'],
            'texts': texts, 'card_type': kind, 'line': ' · '.join(p for p in line if p),
            'atk': facts.get('atk'), 'def': facts.get('def'), 'level': facts.get('level'), 'rank': facts.get('rank'),
            'link': len(facts['linkArrows']) if facts.get('linkArrows') else None,
            'passcodes': facts.get('passwords', []), 'legality': legality,
            'master_duel': (facts.get('masterDuel') or {}).get('rarity'), 'duel_links': (facts.get('duelLinks') or {}).get('rarity'),
            'source': 'YGOJSON (datos) y Neuron/YGOJSON (textos), registro local'}


if __name__ == '__main__':
    import sys
    print(json.dumps(card_sheet(sys.argv[1]), ensure_ascii=False, indent=2))
