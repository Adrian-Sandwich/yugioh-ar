"""Face-down cards: the card back (or a sleeve) as one more identity, checked zone by zone.

The card detector (ygo_yolo.onnx) was trained on card faces and finds no backs:
pasted into a live capture, two back images got no box while card faces in the
same spots did (0.96, 0.72). So backs are looked for where they can be: each
field zone of the calibrated board that holds no detected card is rectified to
224x224 and encoded with the recognizer's own encoder, then compared with the
back references. On synthetic zones over live captures the official back scored
0.61-0.93 and empty zones or face-up cards 0.02-0.14 (probe 27/09/2026); the
threshold sits between them until real captures calibrate it.

References live in data/card-backs (not versioned): the official back, downloaded
on first use, and backs taught from the camera ("Enseñar reverso": a sleeve is
what the camera sees). A monster zone with a back is a face-down Defense Position
monster; a Spell & Trap zone, a set card (playmat.battle_position).
"""
import json
import os
import time
import urllib.request
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
# YUGIOH_CARD_BACKS: another folder (tests; inherited by the recognizer's child process).
FOLDER = Path(os.environ.get('YUGIOH_CARD_BACKS') or ROOT / 'data/card-backs')
INDEX = FOLDER / 'backs.json'
OFFICIAL = [('official-ygoprodeck.jpg', 'https://images.ygoprodeck.com/images/cards/back_high.jpg'),
            ('official-yugipedia.png', 'https://ms.yugipedia.com//e/e5/Back-EN.png')]
THRESHOLD = .45
SIZE = 224


def zone_crop(image, polygon):
    """The zone (TL, TR, BR, BL image points) rectified to SIZE x SIZE, as the encoder sees it."""
    dst = np.float32([[0, 0], [SIZE - 1, 0], [SIZE - 1, SIZE - 1], [0, SIZE - 1]])
    return cv2.warpPerspective(image, cv2.getPerspectiveTransform(np.float32(polygon), dst), (SIZE, SIZE))


def official_crops(card):
    """A full back image as a zone would show it: upright and sideways, on a dark mat."""
    out = []
    for sideways in (False, True):
        zone = np.full((300, 300, 3), 40, np.uint8)
        c = cv2.rotate(card, cv2.ROTATE_90_CLOCKWISE) if sideways else card
        h, w = c.shape[:2]; s = 270 / max(h, w); c = cv2.resize(c, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        y0, x0 = (300 - c.shape[0]) // 2, (300 - c.shape[1]) // 2
        zone[y0:y0 + c.shape[0], x0:x0 + c.shape[1]] = c
        out.append(cv2.resize(zone, (SIZE, SIZE), interpolation=cv2.INTER_AREA))
    return out


def entries():
    return json.loads(INDEX.read_text(encoding='utf-8')) if INDEX.exists() else []


def _write(items):
    FOLDER.mkdir(parents=True, exist_ok=True)
    tmp = INDEX.with_suffix('.tmp'); tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding='utf-8'); tmp.replace(INDEX)


def ensure_official():
    """Download the official back once; offline it is simply missing (taught backs still work)."""
    items = entries(); known = {e['source'] for e in items}; changed = False
    for name, url in OFFICIAL:
        path = FOLDER / name
        if not path.exists():
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'yugioh-ar/1.0'})
                data = urllib.request.urlopen(request, timeout=20).read()
                FOLDER.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            except OSError as error:
                print(f'BACKS: no se pudo descargar {url}: {error}', flush=True); continue
        if name not in known:
            items.append({'id': name.rsplit('.', 1)[0], 'source': name, 'kind': 'official', 'url': url}); changed = True
    if changed: _write(items)
    return items


def teach(image, polygon, player=None, zone=None):
    """Keep this zone's crop as a back reference (a sleeve, or the back under this light)."""
    crop = zone_crop(image, polygon)
    stamp = time.strftime('%Y%m%d-%H%M%S'); name = f'taught-{stamp}-{len(entries())}.jpg'
    FOLDER.mkdir(parents=True, exist_ok=True); cv2.imwrite(str(FOLDER / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
    entry = {'id': name.rsplit('.', 1)[0], 'source': name, 'kind': 'taught', 'player': player, 'zone': zone, 'created': stamp}
    _write(entries() + [entry])
    return entry


def forget_taught():
    items = entries(); kept = [e for e in items if e.get('kind') != 'taught']
    for e in items:
        if e.get('kind') == 'taught': (FOLDER / e['source']).unlink(missing_ok=True)
    _write(kept)
    return len(items) - len(kept)


def summary():
    items = entries()
    return {'official': sum(e.get('kind') == 'official' for e in items), 'taught': sum(e.get('kind') == 'taught' for e in items), 'threshold': THRESHOLD}


class BackChecker:
    """Scores zones against the back references with the recognizer's encoder."""
    def __init__(self, encoder):
        self.encoder = encoder; self.signature = None; self.vectors = None; self.downloaded = False

    def _load(self):
        if not self.downloaded: ensure_official(); self.downloaded = True
        signature = INDEX.stat().st_mtime_ns if INDEX.exists() else None
        if signature == self.signature: return
        crops = []
        for e in entries():
            image = cv2.imread(str(FOLDER / e['source']), cv2.IMREAD_COLOR)
            if image is None: continue
            # Taught crops are zones already; a 180 degree turn is the same card seen from the other side.
            crops += [image, np.ascontiguousarray(np.rot90(image, 2))] if e.get('kind') == 'taught' else official_crops(image)
        self.vectors = np.stack([z for _, z in self.encoder.predict_batch(crops, classify=False)]) if crops else None
        self.signature = signature

    def check(self, image, zones, occupied=()):
        """`zones`: [{'id', 'polygon'}]; zones whose polygon contains a point of `occupied` (centres of
        detected cards) are skipped. Returns [{'id', 'score'}] for every zone checked."""
        self._load()
        if self.vectors is None or not zones: return []
        todo = [z for z in zones if not any(cv2.pointPolygonTest(np.float32(z['polygon']).reshape(-1, 1, 2), (float(x), float(y)), False) >= 0 for x, y in occupied)]
        if not todo: return []
        encoded = self.encoder.predict_batch([zone_crop(image, z['polygon']) for z in todo], classify=False)
        return [{'id': z['id'], 'score': round(float((self.vectors @ v).max()), 3)} for z, (_, v) in zip(todo, encoded)]


if __name__ == '__main__':
    print(json.dumps(ensure_official(), indent=2, ensure_ascii=False))
