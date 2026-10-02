"""card_backs.ZoneOccupancy: a face-down card in any sleeve, without teaching, on a synthetic table.

Built like the live table of 02/10/2026: portrait zones narrower than a card, a card in defence
wider than its zone, a deck right next to a Spell & Trap Zone, a face-up card the detector boxed.
"""
import json

import cv2
import numpy as np

import card_backs as cb


def table(seed=3):
    """A cork-like table: brown with grain, 1280x720."""
    rng = np.random.default_rng(seed)
    base = np.full((720, 1280, 3), (90, 140, 180), np.int16)
    noise = cv2.GaussianBlur(rng.integers(-40, 40, (720, 1280), dtype=np.int16).astype(np.float32), (0, 0), 2)
    return np.clip(base + noise.astype(np.int16)[..., None], 0, 255).astype(np.uint8)


CARD = (110, 160)   # width, height of a card at this scale


def put(image, colour, centre, sideways):
    w, h = CARD[::-1] if sideways else CARD
    x, y = centre; image[y - h // 2:y + h // 2, x - w // 2:x + w // 2] = colour


def zone(cx, cy, w=96, h=140):   # narrower than a card, like the virtual board
    return [[cx - w // 2, cy - h // 2], [cx + w // 2, cy - h // 2], [cx + w // 2, cy + h // 2], [cx - w // 2, cy + h // 2]]


def main():
    checks = []
    zones = {f'monster:{i}': zone(160 + 200 * i, 200) for i in range(5)} | {f'spell:{i}': zone(160 + 200 * i, 480) for i in range(5)}
    scene = table()
    put(scene, (12, 12, 12), (360, 200), sideways=True)        # black sleeve in defence: monster:1
    put(scene, (140, 220, 40), (560, 480), sideways=False)     # green sleeve set: spell:2
    put(scene, (200, 60, 230), (960, 200), sideways=True)      # pink sleeve in defence: monster:4
    put(scene, (30, 160, 60), (560, 200), sideways=False)      # face-up card, boxed by the detector: monster:2
    cv2.circle(scene, (760, 200), 55, (70, 80, 90), -1)        # a hand-like blob: monster:3
    scene[400:560, 1050:1170] = (12, 12, 12)                   # a deck beside spell:4 (only its edge enters the zone)
    faces = {'monster:2'}

    occ = cb.ZoneOccupancy()
    def run(img, now):
        labs = {z: cb.zone_lab(img, cb.grown(p)) for z, p in zones.items()}
        colour = occ.table_colour(list(labs.values()))
        return {z: occ.update(z, labs[z], colour, z in faces, now) for z in zones}
    first = run(scene, 0.)
    assert not any(r['occupied'] for r in first.values()), 'nothing counts before OCC_HOLD_S'
    later = run(scene, cb.OCC_HOLD_S + .1)
    got = {z for z, r in later.items() if r['occupied']}
    assert got == {'monster:1', 'spell:2', 'monster:4'}, got
    assert later['monster:1']['sideways'] and later['monster:4']['sideways'] and not later['spell:2']['sideways'], later
    checks += ['black, green and pink sleeves found without teaching, after the hold', 'cards wider than their zone',
               'orientation: defence vs set', 'face-up card boxed by the detector excluded', 'hand-like blob ignored',
               'a deck beside a zone does not count']
    clear = table()
    assert not any(r['occupied'] for r in run(clear, 5.).values()), 'clear table: nothing'
    assert not any(r['occupied'] for r in run(cv2.convertScaleAbs(clear, alpha=.85, beta=-10), 6.).values()), 'dimmer light: nothing'
    checks += ['clear table: nothing', 'dimmer light: nothing']
    # No empty picture to take: a duel started with cards already down finds them all the same.
    fresh = cb.ZoneOccupancy()
    labs = {z: cb.zone_lab(scene, cb.grown(p)) for z, p in zones.items()}; colour = fresh.table_colour(list(labs.values()))
    for now in (0., cb.OCC_HOLD_S + .1): result = {z: fresh.update(z, labs[z], colour, z in faces, now) for z in zones}
    assert {z for z, r in result.items() if r['occupied']} == got
    checks.append('cards already down when watching starts are found too')
    print(json.dumps({'status': 'passed', 'checks': checks}))


if __name__ == '__main__':
    main()
