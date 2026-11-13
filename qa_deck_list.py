"""The duel's deck list (deck_list.py) and the recognizer's rule for its cards (vision_onnx.DECK_ACCEPTANCE),
with a made-up index: no models, no data."""
import tempfile

import numpy as np

import deck_list
import vision_onnx
from table_duel import TableDuel

REFS = [{'id': 'tdoane:card:32274490.jpg', 'card_id': 'skull', 'name': 'Sirviente de la Calavera', 'name_en': 'Skull Servant', 'source': 'x/32274490.jpg'},
        {'id': 'ygoprodeck:card:abc', 'card_id': 'king', 'name': 'Rey de los Sirvientes de la Calavera', 'source': '../cards/36021814.jpg'},
        {'id': 'tdoane:card:24299458.jpg', 'card_id': 'drop', 'name': 'Gotas Prohibidas', 'name_en': 'Forbidden Droplet', 'source': 'x/24299458.jpg'},
        {'id': 'tdoane:card:00000099.jpg', 'card_id': 'other', 'name': 'Otra', 'source': 'x/00000099.jpg'}]


def main():
    checks = []
    # A .ydk as it is, names with copies in front, accents and case aside; each card once; what is not found is said.
    deck = deck_list.parse('#created by x\n#main\n32274490\n32274490\n036021814\n#extra\n!side\n3x gotas prohibidas\n2 Skull Servant\nNo Existe\n77777777\n', REFS)
    assert deck['cards'] == ['skull', 'king', 'drop'] and deck['unknown'] == ['No Existe', '77777777'], deck
    assert deck['names']['king'] == 'Rey de los Sirvientes de la Calavera'
    assert deck_list.parse('', REFS)['cards'] == []
    checks.append('a .ydk and names with copies read as one list; unknown lines reported')
    # The duel keeps the list across restarts and hands it to every analysis.
    with tempfile.TemporaryDirectory() as folder:
        table = TableDuel(folder=folder)
        assert table.deck['cards'] == [] and table.set_deck('32274490\nGotas Prohibidas', REFS)['cards'] == ['skull', 'drop']
        assert TableDuel(folder=folder).deck['cards'] == ['skull', 'drop']
        assert table.set_deck('', REFS)['cards'] == [] and TableDuel(folder=folder).deck['cards'] == []
    checks.append('the list is saved with the duel, and emptied with an empty text')
    # The rule: the margin over the best OTHER card of the list, whatever else the catalogue holds.
    model = vision_onnx.ResearchRecognizer.__new__(vision_onnx.ResearchRecognizer)
    unit = lambda v: np.float32(v) / np.linalg.norm(v)
    model.rows = [{'card_id': 'skull'}, {'card_id': 'skull'}, {'card_id': 'king'}, {'card_id': 'drop'}, {'card_id': 'twin'}]
    model.vectors = np.stack([unit([1, 0, 0, 0]), unit([.9, .1, 0, 0]), unit([0, 1, 0, 0]), unit([0, 0, 1, 0]), unit([.95, 0, 0, .3])])
    z = unit([1, .15, 0, .1])
    catalogue = sorted(model.vectors @ z)[::-1]
    assert catalogue[0] - catalogue[2] < .05  # 'twin', a look-alike outside the list, sits right behind in the catalogue
    margin = model.deck_margin(z, 'skull', ['skull', 'king', 'drop'])
    assert margin > .8 and abs(margin - (float((model.vectors[:2] @ z).max()) - float(model.vectors[2] @ z))) < 1e-6, margin
    assert model.deck_margin(z, 'twin', ['skull', 'king', 'drop']) is None, 'a card outside the list has no deck margin'
    assert model.deck_margin(z, 'skull', ['skull', 'twin']) < .05, 'with its look-alike on the list the margin is the small one'
    assert model.deck_margin(z, 'skull', ['skull']) > .9 and model.deck_margin(z, 'skull', []) is None
    assert 0 < vision_onnx.DECK_ACCEPTANCE[0] < vision_onnx.ACCEPTANCE['embedding'][0]
    checks.append('deck margin: against the other cards of the list only; none for a card outside it')
    for c in checks: print('ok', c)


if __name__ == '__main__':
    main()
