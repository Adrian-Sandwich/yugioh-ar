"""Simulated check of name_ocr.pick_by_name: misread titles against five candidates.

No annotated photos exist yet, so titles are simulated from the registry's English names with
OCR-like damage (letters replaced, dropped or doubled, accents added: "Naturia Barkion" was read
as "NČHIRIA BARKION"). The four companions of the true card are its most similar names in the
registry, the hard case of a recognizer confused within an archetype. Two measures:
- found: the true card is among the five and gets picked (a correct promotion);
- wrong: the true card is NOT among the five and one of them gets picked (a wrong promotion).

    python research/eval_name_pick.py [--n 400] -> research/qa/name-pick.json
"""
import argparse, difflib, json, random, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from name_ocr import NameRegistry, name_key, pick_by_name
from identity_resolution import canonical

SUBS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZČÉÍÓÚÑ'


def damage(name, errors, rng):
    chars = list(name.upper())
    for _ in range(errors):
        letters = [i for i, c in enumerate(chars) if c.isalpha()]
        if not letters: break
        i = rng.choice(letters); op = rng.random()
        if op < .6: chars[i] = rng.choice(SUBS)
        elif op < .8: del chars[i]
        else: chars.insert(i, chars[i])
    return ''.join(chars)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--n', type=int, default=400); parser.add_argument('--seed', type=int, default=5)
    args = parser.parse_args(); rng = random.Random(args.seed)
    registry = NameRegistry(); registry.refresh()
    import sqlite3
    db = sqlite3.connect((ROOT / 'data/registry/registry.sqlite').as_uri() + '?mode=ro', uri=True)
    english = {}
    for uid, name in db.execute("SELECT card_id, name FROM names WHERE language='en'"): english.setdefault(canonical(uid), name)
    ids = sorted(english); folded = {cid: name_key(english[cid], True) for cid in ids}
    by_folded = {}
    for cid, f in folded.items(): by_folded.setdefault(f, []).append(cid)
    sample = rng.sample(ids, args.n); results = {}; started = time.time()
    for errors in (1, 2, 3, 4):
        found = wrong = present_total = absent_total = 0; examples = []
        for cid in sample:
            close = difflib.get_close_matches(folded[cid], list(by_folded), n=8, cutoff=.5)
            negatives = [o for f in close for o in by_folded[f] if o != cid and folded[o] != folded[cid]][:5]
            if len(negatives) < 4: continue
            text = damage(english[cid], errors, rng)
            pick = pick_by_name(registry, text, [cid] + negatives[:4]); present_total += 1
            found += bool(pick and pick['card_id'] == cid)
            bad = pick_by_name(registry, text, negatives[:5]); absent_total += 1
            if bad: wrong += 1; examples.append({'title': text, 'true': english[cid], 'picked': english.get(bad['card_id']), 'similarity': bad['similarity']})
        results[errors] = {'present': present_total, 'found': round(found / max(present_total, 1), 3),
                           'absent': absent_total, 'wrong': round(wrong / max(absent_total, 1), 4), 'wrong_examples': examples[:5]}
        print(errors, 'errores', {k: v for k, v in results[errors].items() if k != 'wrong_examples'}, round(time.time() - started), 's', flush=True)
    out = {'date': time.strftime('%Y-%m-%d'), 'n': args.n, 'min_similarity': __import__('name_ocr').NAME_PICK_MIN,
           'margin': __import__('name_ocr').NAME_PICK_MARGIN, 'by_errors': results,
           'limits': 'Títulos simulados desde nombres en inglés con daño tipo OCR; compañeros = nombres más parecidos del registro. Falta medir con fotos reales anotadas.'}
    (ROOT / 'research/qa/name-pick.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
