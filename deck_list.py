"""The decks on the table, as a list of cards: the recognizer accepts a card of the list on weaker
evidence than a card of the whole catalogue (vision_onnx.DECK_ACCEPTANCE), which is what a camera at
an angle, a sleeve's glare or a card far away need. The list never hides a card: one outside it is
still recognized by the catalogue's rule.

A list is text, one card per line: a passcode (a .ydk file as it is; #main, #extra and !side are
skipped) or a name, with or without copies in front ("3 Skull Servant", "3x Skull Servant"). Both
players' decks go in the same list.
"""
import json
import re
import unicodedata
from pathlib import Path

FILE = 'deck.json'


def plain(text):
    """A name as it is compared: no accents, case or punctuation."""
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+', ' ', text).strip()


def lookup(references):
    """({passcode: card_id}, {plain name: card_id}) of the recognizer's references."""
    codes, names = {}, {}
    for ref in references:
        for value in (ref.get('source'), ref.get('id')):
            stem = Path(str(value or '').rsplit(':', 1)[-1]).stem
            if stem.isdigit(): codes.setdefault(str(int(stem)), ref['card_id'])
        for key in ('name', 'name_en', 'name_es'):
            if ref.get(key): names.setdefault(plain(ref[key]), ref['card_id'])
    return codes, names


def parse(text, references):
    """{'cards': [card_id, ...] (each once), 'names': {card_id: name}, 'unknown': [lines not found]}."""
    codes, names = lookup(references); shown = {r['card_id']: r.get('name') or r['card_id'] for r in references}
    cards, unknown = [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in '#!': continue
        found = codes.get(str(int(line))) if line.isdigit() else None
        if found is None and not line.isdigit():
            found = names.get(plain(line)) or names.get(plain(re.sub(r'^\d+\s*x?\s+', '', line, flags=re.I)))
        if found is None: unknown += [line] if line not in unknown else []
        elif found not in cards: cards.append(found)
    return {'cards': cards, 'names': {c: shown[c] for c in cards}, 'unknown': unknown}


def load(folder):
    path = Path(folder) / FILE
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return {'cards': [], 'names': {}, 'unknown': []}


def save(folder, deck):
    Path(folder).mkdir(parents=True, exist_ok=True)
    (Path(folder) / FILE).write_text(json.dumps(deck, ensure_ascii=False, indent=1), encoding='utf-8')
