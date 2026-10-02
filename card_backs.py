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
import time
import urllib.request

import cv2
import numpy as np

import settings
from util import atomic_write
ROOT = settings.ROOT
# YUGIOH_CARD_BACKS: another folder (tests; inherited by the recognizer's child process).
FOLDER = settings.CARD_BACKS
INDEX = FOLDER / 'backs.json'
OFFICIAL = [('official-ygoprodeck.jpg', 'https://images.ygoprodeck.com/images/cards/back_high.jpg'),
            ('official-yugipedia.png', 'https://ms.yugipedia.com//e/e5/Back-EN.png')]
THRESHOLD = .45
# A back this clear wins over a face the recogniser accepted in the same zone (vision_onnx):
# face-up cards score <= 0.15 against the backs, taught and official backs 0.75-0.999.
STRONG = .75
# Taught sleeves need more: on 02/10/2026 a sleeve taught with its whole zone (card plus a margin of
# table) matched empty cork zones at 0.45-0.55 and the duel recorded five face-down cards that were
# not there. Now only the card is kept (teach), and a taught match must reach TAUGHT_THRESHOLD; its
# score is reported shifted down by the difference, so it also needs more to be STRONG.
TAUGHT_THRESHOLD = .60
TAUGHT_SHIFT = TAUGHT_THRESHOLD - THRESHOLD
SIZE = 224
# A zone's score is reused while its 16x16 grey thumbnail stays within this mean difference (camera
# noise is 1-2 levels; a card set or lifted changes it by tens), for at most REUSE_MAX_S.
REUSE_MAX_DIFF = 4.0
REUSE_MAX_S = 2.0


def zone_crop(image, polygon):
    """The zone (TL, TR, BR, BL image points) rectified to SIZE x SIZE, as the encoder sees it."""
    dst = np.float32([[0, 0], [SIZE - 1, 0], [SIZE - 1, SIZE - 1], [0, SIZE - 1]])
    return cv2.warpPerspective(image, cv2.getPerspectiveTransform(np.float32(polygon), dst), (SIZE, SIZE))


def official_crops(card, turns=(0, 1)):
    """A full back image as a zone would show it, on a dark mat: upright and sideways by default
    (quarter turns; a printed sleeve keeps all four, its picture changes with the turn)."""
    out = []
    for k in turns:
        zone = np.full((300, 300, 3), 40, np.uint8)
        c = np.ascontiguousarray(np.rot90(card, -k)) if k else card
        h, w = c.shape[:2]; s = 270 / max(h, w); c = cv2.resize(c, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        y0, x0 = (300 - c.shape[0]) // 2, (300 - c.shape[1]) // 2
        zone[y0:y0 + c.shape[0], x0:x0 + c.shape[1]] = c
        out.append(cv2.resize(zone, (SIZE, SIZE), interpolation=cv2.INTER_AREA))
    return out


def entries():
    return json.loads(INDEX.read_text(encoding='utf-8')) if INDEX.exists() else []


def _write(items):
    FOLDER.mkdir(parents=True, exist_ok=True)
    atomic_write(INDEX, json.dumps(items, indent=2, ensure_ascii=False))


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


CARD_RATIO = 614 / 421   # height / width of a card


def card_in_zone(crop, sideways=None):
    """The card inside a rectified zone crop, upright (portrait), without the table around it.

    The largest card-shaped contour wins; without one, a centred card-sized crop, sideways in a
    Monster Zone (a face-down monster is in defence) and upright elsewhere.
    """
    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(cv2.Canny(cv2.GaussianBlur(grey, (5, 5), 0), 40, 120), np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = crop.shape[0] * crop.shape[1]; best = None
    for c in contours:
        (cx, cy), (w, h), angle = rect = cv2.minAreaRect(c)
        if not w or not h: continue
        ratio = max(w, h) / min(w, h)
        if .25 * area <= w * h <= .97 * area and abs(ratio - CARD_RATIO) < .25 and (best is None or w * h > best[1][0] * best[1][1]):
            best = rect
    if best is None:
        side = SIZE * .86; w, h = (side, side / CARD_RATIO) if sideways else (side / CARD_RATIO, side)
        best = ((SIZE / 2, SIZE / 2), (w, h), 0.)
    box = cv2.boxPoints(best)
    # Order the corners so the long side is vertical: the card comes out in portrait.
    box = box[np.argsort(box[:, 1])]; top = box[:2][np.argsort(box[:2, 0])]; bottom = box[2:][np.argsort(box[2:, 0])]
    tl, tr, br, bl = top[0], top[1], bottom[1], bottom[0]
    if np.linalg.norm(tr - tl) > np.linalg.norm(bl - tl): tl, tr, br, bl = bl, tl, tr, br   # landscape: turn it
    W, H = 300, round(300 * CARD_RATIO)
    m = cv2.getPerspectiveTransform(np.float32([tl, tr, br, bl]), np.float32([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]]))
    return cv2.warpPerspective(crop, m, (W, H))


def teach(image, polygon, player=None, zone=None):
    """Keep the card in this zone as a back reference (a sleeve, or the back under this light):
    only the card, so an empty zone of the same table does not look like it."""
    crop = card_in_zone(zone_crop(image, polygon), sideways=str(zone or '').startswith('monster'))
    stamp = time.strftime('%Y%m%d-%H%M%S'); name = f'taught-{stamp}-{len(entries())}.jpg'
    FOLDER.mkdir(parents=True, exist_ok=True); cv2.imwrite(str(FOLDER / name), crop, [cv2.IMWRITE_JPEG_QUALITY, 95])
    entry = {'id': name.rsplit('.', 1)[0], 'source': name, 'kind': 'taught', 'card_only': True, 'player': player, 'zone': zone, 'created': stamp}
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
        self.recent = {}   # zone id -> (polygon, 16x16 grey thumbnail, score, time): unchanged zones skip the encoder
        self.occupancy = ZoneOccupancy()

    def _load(self):
        if not self.downloaded: ensure_official(); self.downloaded = True
        signature = INDEX.stat().st_mtime_ns if INDEX.exists() else None
        if signature == self.signature: return
        crops = []; kinds = []
        for e in entries():
            image = cv2.imread(str(FOLDER / e['source']), cv2.IMREAD_COLOR)
            if image is None: continue
            # Official backs: upright and sideways on a dark mat. Taught sleeves: the card only, on the same
            # mat, in all four turns (a printed sleeve taught upright must still match sideways).
            if e.get('kind') != 'taught': crops += official_crops(image); kinds += ['official'] * 2
            elif e.get('card_only'): crops += official_crops(image, turns=range(4)); kinds += ['taught'] * 4
            else:  # taught before 02/10/2026: the whole zone, table included
                crops += [np.ascontiguousarray(np.rot90(image, k)) for k in range(4)]; kinds += ['taught'] * 4
        self.vectors = np.stack([z for _, z in self.encoder.predict_batch(crops, classify=False)]) if crops else None
        self.taught = np.array([k == 'taught' for k in kinds], bool)
        self.signature = signature; self.recent = {}

    def score(self, vector):
        """Best match against the backs; a taught sleeve's similarity counts TAUGHT_SHIFT lower."""
        sims = self.vectors @ vector
        if self.taught.any(): sims = np.where(self.taught, sims - TAUGHT_SHIFT, sims)
        return round(float(sims.max()), 3)

    def check(self, image, zones, occupied=(), faces=None):
        """`zones`: [{'id', 'polygon'}]; zones whose polygon contains a point of `occupied`
        (centres of detected cards) are skipped. `faces`: centres of every card box the detector found
        (recognised or not); given, zone occupancy runs too (ZoneOccupancy). Returns, for every zone
        checked, {'id', 'score'} plus 'occupancy' when it ran; an occupied zone scores at least OCC_SCORE."""
        self._load()
        if self.vectors is None or not zones: return []
        todo = [z for z in zones if not any(cv2.pointPolygonTest(np.float32(z['polygon']).reshape(-1, 1, 2), (float(x), float(y)), False) >= 0 for x, y in occupied)]
        if not todo: return []
        # A zone whose picture has not changed keeps its score: the encoder ran on all 22 zones every
        # analysis (27-40 ms live) though the table is still most of the time.
        now = time.monotonic(); scores = {}; fresh = []
        for z in todo:
            crop = zone_crop(image, z['polygon'])
            thumb = cv2.resize(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32)
            key = np.round(np.float32(z['polygon']))
            seen = self.recent.get(z['id'])
            if seen and np.array_equal(seen[0], key) and now - seen[3] <= REUSE_MAX_S and float(np.abs(seen[1] - thumb).mean()) <= REUSE_MAX_DIFF:
                scores[z['id']] = seen[2]
            else: fresh.append((z, crop, thumb, key))
        if fresh:
            for (z, _, thumb, key), (_, v) in zip(fresh, self.encoder.predict_batch([c for _, c, _, _ in fresh], classify=False)):
                scores[z['id']] = self.score(v); self.recent[z['id']] = (key, thumb, scores[z['id']], now)
        out = [{'id': z['id'], 'score': scores[z['id']]} for z in todo]
        if faces is not None:
            labs = [zone_lab(image, grown(z['polygon'])) for z in todo]
            table = self.occupancy.table_colour(labs)
            for item, z, lab in zip(out, todo, labs):
                polygon = np.float32(z['polygon']).reshape(-1, 1, 2)
                face = any(cv2.pointPolygonTest(polygon, (float(x), float(y)), False) >= 0 for x, y in faces)
                occ = self.occupancy.update(z['id'], lab, table, face, now)
                item['occupancy'] = occ
                if occ.get('occupied'): item['score'] = max(item['score'], OCC_SCORE)
        return out

# --- zone occupancy: any sleeve, no teaching ----------------------------------------------------
# A Monster or Spell & Trap Zone holds a face-down card when a card-shaped patch that is not the
# table's colour sits in its middle and the detector boxes no face-up card there: black, pink,
# green or printed sleeve, or the bare back. The table's colour is the median of every zone in the
# same analysis (mostly table even with cards down), so nothing has to be learned and the table need
# not be clear when the duel starts. A first version kept each zone's empty picture from the start
# of the duel; on 02/10/2026 the duel was started with two cards already down and they became part
# of "empty". Each zone is looked at 70 % larger than itself: a card in defence is wider than its
# portrait zone. A sleeve the colour of the table is missed (the back score still covers the
# official back and taught sleeves).
OCC_SIZE = 64                 # zone pictures compared at 64x64 (Lab, blurred)
OCC_GROW = 1.7                # zone enlarged around its centre: a sideways card fits, and a card larger than its zone (virtual boards)
OCC_PIXEL = 30.               # colour distance from the table (Lab, lightness weighted OCC_L) that is "not table"
OCC_L = .45                   # lightness weighs less than colour: shadows, glare and vignetting
OCC_MIN, OCC_MAX = .12, .85   # share of the enlarged zone a card covers
OCC_RATIO_TOL = .40           # card shape: long/short side within this of CARD_RATIO
OCC_CENTRE = .22              # the patch's centre within this share of the crop's middle (not a neighbour's card)
OCC_CORE = .30                # the middle of the zone (this share of the enlarged crop, each side) ...
OCC_CORE_FILL = .75           # ... must be this much not-table: a card covers its zone's middle, a neighbouring deck only an edge
OCC_HOLD_S = .8               # stays this long before it counts (a hand passing does not)
OCC_SCORE = .6                # reported as a back score: over THRESHOLD, under STRONG (a face still wins)


def grown(polygon, factor=OCC_GROW):
    q = np.float32(polygon); c = q.mean(0)
    return (c + (q - c) * factor).tolist()


def zone_lab(image, polygon):
    """The (enlarged) zone rectified with its own proportions, OCC_SIZE high, as blurred Lab.
    Not to a square: a portrait zone squeezed square makes an upright card look square."""
    q = np.float32(polygon)
    w = (np.linalg.norm(q[1] - q[0]) + np.linalg.norm(q[2] - q[3])) / 2; h = (np.linalg.norm(q[3] - q[0]) + np.linalg.norm(q[2] - q[1])) / 2
    W = max(8, round(OCC_SIZE * w / max(h, 1)))
    dst = np.float32([[0, 0], [W - 1, 0], [W - 1, OCC_SIZE - 1], [0, OCC_SIZE - 1]])
    small = cv2.warpPerspective(image, cv2.getPerspectiveTransform(q, dst), (W, OCC_SIZE), flags=cv2.INTER_AREA)
    return cv2.cvtColor(cv2.GaussianBlur(small, (5, 5), 0), cv2.COLOR_BGR2LAB).astype(np.float32)


def card_patch(mask):
    """(is a card, sideways) for the largest not-table region of an enlarged zone."""
    mask = cv2.morphologyEx(mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours: return False, None
    (cx, cy), (w, h), angle = cv2.minAreaRect(max(contours, key=cv2.contourArea))
    if not w or not h: return False, None
    H, W = mask.shape
    share = w * h / (W * H); ratio = max(w, h) / min(w, h)
    centred = abs(cx - W / 2) <= OCC_CENTRE * W and abs(cy - H / 2) <= OCC_CENTRE * H
    ok = OCC_MIN <= share <= OCC_MAX and abs(ratio - CARD_RATIO) <= OCC_RATIO_TOL and centred
    long_x = (w >= h) == (abs(angle) <= 45 or abs(angle) >= 135)
    return ok, long_x


class ZoneOccupancy:
    """Which zones hold a card-shaped, not-table-coloured patch that has lasted OCC_HOLD_S."""
    def __init__(self):
        self.since = {}

    def table_colour(self, labs):
        """Median colour of all zones of one analysis: the table, since cards cover the lesser part."""
        return np.median(np.concatenate([l.reshape(-1, 3) for l in labs]), axis=0)

    def update(self, zone_id, lab, table, face_box, now):
        """{'occupied', 'change', 'card', 'sideways'} for one zone. `lab`: zone_lab of its enlarged crop;
        `face_box`: the detector boxed a card here (a face-up card, recognised or not)."""
        not_table = (np.abs(lab - table) * (OCC_L, 1., 1.)).sum(2) > OCC_PIXEL
        share = float(not_table.mean())
        H, W = not_table.shape; ch, cw = round(H * OCC_CORE / 2), round(W * OCC_CORE / 2)
        core = float(not_table[H // 2 - ch:H // 2 + ch, W // 2 - cw:W // 2 + cw].mean())
        card, sideways = card_patch(not_table) if share >= OCC_MIN * .8 and core >= OCC_CORE_FILL else (False, None)
        if not card or face_box:
            self.since.pop(zone_id, None)
            return {'occupied': False, 'change': round(share, 2), 'card': card}
        first = self.since.setdefault(zone_id, now)
        return {'occupied': now - first >= OCC_HOLD_S, 'change': round(share, 2), 'card': True, 'sideways': sideways}

if __name__ == '__main__':
    print(json.dumps(ensure_official(), indent=2, ensure_ascii=False))
