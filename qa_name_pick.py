"""Title OCR as a second vote: name_ocr.pick_by_name and vision_onnx.promote_by_name."""
import json, time
from pathlib import Path
from name_ocr import name_key, pick_by_name
from vision_onnx import promote_by_name

ROOT = Path(__file__).resolve().parent


class Registry:
    """The fields of name_ocr.NameRegistry that pick_by_name reads."""
    def __init__(self, names):
        self.by_id, self.owners = {}, {}
        for cid, name in names:
            key = name_key(name, True); self.by_id.setdefault(cid, set()).add(key); self.owners.setdefault(key, set()).add(cid)
        self.all_keys = list(self.owners)
    def refresh(self): return True


REG = Registry([('barkion', 'Naturia Barkion'), ('barkion', 'Naturia Barkion'), ('stungray', 'Abyss Stungray'), ('brionac', 'Brionac, the Magical Ice Dragon'),
                ('vision', 'Vision with Eyes of Blue'), ('bark', "Barkion's Bark"), ('garden', 'Aroma Garden'), ('gardening', 'Aroma Gardening'), ('jasmine', 'Aromage Jasmine')])


def main():
    checks = []
    # The live misreading: Barkion is 5th visually; the title picks it among the candidates.
    pick = pick_by_name(REG, 'NČHIRIA BARKION', ['stungray', 'vision', 'brionac', 'bark', 'barkion'])
    assert pick and pick['card_id'] == 'barkion' and pick['similarity'] > .75, pick
    checks.append('misread title (NČHIRIA BARKION) picks the 5th visual candidate')
    # Only among the candidates: absent from them, nothing is picked.
    assert pick_by_name(REG, 'NČHIRIA BARKION', ['stungray', 'vision', 'brionac']) is None
    # A closer name outside the candidates vetoes the pick (Aroma Gardening misread, only Aroma Garden offered).
    assert pick_by_name(REG, 'AROJA GARDENIG', ['garden', 'jasmine']) is None
    assert pick_by_name(REG, 'AROJA GARDENIG', ['garden', 'gardening', 'jasmine']) is None, 'two close candidates: no clear winner'
    assert pick_by_name(REG, 'AROMA GARDENIN', ['gardening', 'jasmine'])['card_id'] == 'gardening'
    checks.append('a closer registry name outside the candidates, or two close candidates, pick nothing')
    assert pick_by_name(REG, 'XQ', ['barkion']) is None and pick_by_name(REG, '', ['barkion']) is None
    checks.append('short or empty titles pick nothing')
    # Promotion: overlapping, recent, among top5 -> accepted with that identity first.
    corners = [[0, 0], [100, 0], [100, 140], [0, 140]]
    now = time.time()
    candidate = {'accepted': False, 'card_id': 'stungray', 'corners': corners, 'score': .385,
                 'top5': [{'card_id': c, 'score': s} for c, s in (('stungray', .385), ('vision', .28), ('brionac', .27), ('bark', .25), ('barkion', .228))]}
    evidence = [{'evidence': 'name', 'card_id': 'barkion', 'corners': corners, 'captured_at': now, 'similarity': .86, 'text': 'NČHIRIA BARKION'}]
    assert promote_by_name([dict(candidate)], evidence[:0], now) == 0
    promoted = dict(candidate); assert promote_by_name([promoted], evidence, now) == 1
    assert promoted['accepted'] and promoted['card_id'] == 'barkion' and promoted['acceptance'] == 'name_ocr' and promoted['top5'][0]['card_id'] == 'barkion', promoted
    checks.append('promotion: the named candidate becomes the identity, first in top5, marked name_ocr')
    far = [{**evidence[0], 'corners': [[500, 500], [600, 500], [600, 640], [500, 640]]}]
    old = [{**evidence[0], 'captured_at': now - 30}]
    other = [{**evidence[0], 'card_id': 'jasmine'}]
    assert all(promote_by_name([dict(candidate)], e, now) == 0 for e in (far, old, other))
    checks.append('no promotion from another card, an old frame, or an identity outside top5')
    sim = json.loads((ROOT / 'research/qa/name-pick.json').read_text(encoding='utf-8')) if (ROOT / 'research/qa/name-pick.json').exists() else None
    print(json.dumps({'status': 'passed', 'checks': checks, 'simulation': sim and {k: {x: v[x] for x in ('found', 'wrong')} for k, v in sim['by_errors'].items()}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
