"""Simulated check of name_ocr.pick_global: a damaged title searched in the whole registry.

Same damage as eval_name_pick.py (letters replaced, dropped or doubled, accents added) on 300
English names, seed 5. Unlike the in-candidates pick there is no candidate list to protect it:
every pick that is not the true card is a wrong acceptance, so `wrong` is the number to watch.
Also measured on near-twin names (one registry name contained in another, "Aroma Garden" /
"Aroma Gardening"), the hard case.

    python research/eval_name_global.py -> research/qa/name-global.json
"""
import json, random, sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'research'))
from eval_name_pick import damage
from identity_resolution import canonical
from name_ocr import NAME_GLOBAL_MARGIN, NAME_GLOBAL_MIN, NameRegistry, name_key, pick_global


def measure(registry, english, ids, rng, errors):
    found = wrong = 0; examples = []
    for cid in ids:
        text = damage(english[cid], errors, rng) if errors else english[cid].upper()
        pick = pick_global(registry, text)
        if pick and canonical(pick['card_id']) == cid: found += 1
        elif pick:
            wrong += 1; examples.append({'title': text, 'true': english[cid], 'picked': english.get(canonical(pick['card_id'])), 'similarity': pick['similarity']})
    return {'n': len(ids), 'found': round(found / len(ids), 3), 'wrong': round(wrong / len(ids), 4), 'wrong_examples': examples[:5]}


def main():
    rng = random.Random(5); registry = NameRegistry(); registry.refresh(); started = time.time()
    db = sqlite3.connect((ROOT / 'data/registry/registry.sqlite').as_uri() + '?mode=ro', uri=True)
    english = {}
    for uid, name in db.execute("SELECT card_id, name FROM names WHERE language='en'"): english.setdefault(canonical(uid), name)
    ids = sorted(english); sample = rng.sample(ids, 300)
    # Near twins: names that contain another card's whole name (the case the margin must stop).
    keys = {cid: name_key(english[cid], True) for cid in ids}
    by_len = sorted(ids, key=lambda c: len(keys[c]))
    twins = [c for c in random.Random(7).sample(ids, 4000) if len(keys[c]) >= 8 and any(o != c and keys[c] in keys[o] for o in by_len[-3000:])][:150]
    out = {'date': time.strftime('%Y-%m-%d'), 'min_similarity': NAME_GLOBAL_MIN, 'margin': NAME_GLOBAL_MARGIN, 'random': {}, 'near_twins': {}}
    for errors in (0, 1, 2, 3, 4):
        out['random'][errors] = measure(registry, english, sample, rng, errors)
        out['near_twins'][errors] = measure(registry, english, twins, rng, errors) if twins else None
        print(errors, 'errores', {k: v for k, v in out['random'][errors].items() if k != 'wrong_examples'},
              'gemelos', {k: v for k, v in (out['near_twins'][errors] or {}).items() if k != 'wrong_examples'}, round(time.time() - started), 's', flush=True)
    (ROOT / 'research/qa/name-global.json').write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
