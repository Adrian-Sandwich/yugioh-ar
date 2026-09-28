"""Card backs by zone (card_backs.BackChecker) with the real encoder, on a live capture:
official back upright and sideways, empty zones, a face-up card, and a taught sleeve."""
import glob
import json
import shutil
import time
from pathlib import Path

import cv2
import numpy as np

import card_backs
import vision_onnx as v

ROOT = Path(__file__).resolve().parent


def paste(image, card, quad):
    h, w = card.shape[:2]
    m = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), np.float32(quad))
    warped = cv2.warpPerspective(card, m, (image.shape[1], image.shape[0]))
    mask = cv2.warpPerspective(np.full((h, w), 255, np.uint8), m, (image.shape[1], image.shape[0]))
    image[mask > 0] = warped[mask > 0]


def zone(x, y, size, skew=.08):
    """A square zone seen with some perspective (far edge narrower), TL TR BR BL."""
    d = size * skew
    return [[x + d, y], [x + size - d, y], [x + size, y + size], [x, y + size]]


def inset(quad, sideways, fill=.86):
    """Card placement inside a zone: card proportions, upright or sideways, a bit off-centre."""
    q = np.float32(quad); c = q.mean(0) + [4, -3]
    a, b = (421 / 614 * fill / 2, fill / 2) if not sideways else (fill / 2, 421 / 614 * fill / 2)
    u = (q[1] - q[0] + q[2] - q[3]) / 2; w = (q[3] - q[0] + q[2] - q[1]) / 2
    return [(c - a * u - b * w).tolist(), (c + a * u - b * w).tolist(), (c + a * u + b * w).tolist(), (c - a * u + b * w).tolist()]


def main():
    real = card_backs.FOLDER; card_backs.ensure_official()
    tmp = ROOT / 'research/qa/card-backs-tmp'; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir(parents=True)
    for name, _ in card_backs.OFFICIAL: shutil.copy(real / name, tmp / name)
    # Only the official backs: the user's taught sleeves stay out of the test.
    official = [e for e in json.loads((real / 'backs.json').read_text(encoding='utf-8')) if e.get('kind') == 'official']
    (tmp / 'backs.json').write_text(json.dumps(official), encoding='utf-8')
    card_backs.FOLDER, card_backs.INDEX = tmp, tmp / 'backs.json'
    try:
        official = cv2.imread(str(tmp / card_backs.OFFICIAL[1][0]))
        face = cv2.imread(str(v.REFS / json.loads((v.REFS / 'catalog.json').read_text(encoding='utf-8'))[0]['source']))
        # A sleeve: a solid colour with a printed emblem, nothing like the official back.
        sleeve = np.full((614, 421, 3), (40, 90, 20), np.uint8); cv2.circle(sleeve, (210, 307), 120, (200, 220, 240), 18)
        cv2.putText(sleeve, 'AR', (140, 340), cv2.FONT_HERSHEY_SIMPLEX, 3, (230, 240, 250), 10)
        scene = cv2.imread(sorted(glob.glob(str(ROOT / 'data/captures/*.jpg')))[-1])
        zones = {'back_up': zone(150, 150, 260), 'back_side': zone(450, 160, 250), 'empty_a': zone(1300, 100, 240), 'empty_b': zone(150, 700, 250),
                 'face': zone(800, 700, 260), 'sleeve': zone(1500, 720, 250), 'sleeve_up': zone(1150, 400, 250)}
        paste(scene, official, inset(zones['back_up'], False)); paste(scene, official, inset(zones['back_side'], True))
        paste(scene, face, inset(zones['face'], False)); paste(scene, sleeve, inset(zones['sleeve'], True))
        paste(scene, sleeve, inset(zones['sleeve_up'], False))   # same printed sleeve, upright
        encoder = v.Encoder(); checker = card_backs.BackChecker(encoder)
        items = [{'id': k, 'polygon': q} for k, q in zones.items()]
        started = time.perf_counter(); scores = {s['id']: s['score'] for s in checker.check(scene, items)}
        first_ms = round((time.perf_counter() - started) * 1000, 1)
        started = time.perf_counter(); checker.check(scene, items); check_ms = round((time.perf_counter() - started) * 1000, 1)
        t = card_backs.THRESHOLD
        assert scores['back_up'] >= t and scores['back_side'] >= t, scores
        assert all(scores[k] < t for k in ('empty_a', 'empty_b', 'face', 'sleeve', 'sleeve_up')), scores
        # A detected card's centre inside a zone skips it.
        occupied = checker.check(scene, items, occupied=[np.float32(zones['face']).mean(0)])
        assert 'face' not in {s['id'] for s in occupied} and len(occupied) == len(items) - 1
        # Teaching the sleeve: the checker reloads the references and the sleeve counts as a back.
        card_backs.teach(scene, zones['sleeve'], 0, 'spell:2')
        after = {s['id']: s['score'] for s in checker.check(scene, items)}
        assert after['sleeve'] >= t and all(after[k] < t for k in ('empty_a', 'empty_b', 'face')), after
        # Taught sideways, recognised upright: printed sleeves change with the turn (all four are kept).
        assert after['sleeve_up'] >= t, after
        assert card_backs.summary()['taught'] == 1 and card_backs.forget_taught() == 1
        forgotten = {s['id']: s['score'] for s in checker.check(scene, items)}
        assert forgotten['sleeve'] < t, forgotten
        result = {'status': 'passed', 'date': time.strftime('%Y-%m-%d'), 'encoder': encoder.variant, 'threshold': t,
                  'scores': scores, 'sleeve_after_teaching': after['sleeve'], 'sleeve_turned_after_teaching': after['sleeve_up'], 'zones_checked': len(items),
                  'first_check_ms_with_reference_encoding': first_ms, 'check_ms': check_ms,
                  'limits': 'Escena sintética: reversos pegados en una captura en vivo, sin reflejos ni manos. Falta calibrar el umbral con capturas reales.'}
        (ROOT / 'research/qa/card-backs.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        card_backs.FOLDER, card_backs.INDEX = real, real / 'backs.json'
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
