"""Millennium shield: the two usable views of the user's sheet -> web/fx/shield-millennium-{front,back}.png.

The sheet (15 poses on black) is not one steady turn (research/analyze_shield_sheet.py,
28/09/2026): steps of 35, 9 and 22 degrees, three poses stuck near 100 degrees (one going back),
a jump of about 80 degrees, poses 2 and 3 turning opposite ways, pose 5 showing face and back at
once, heights drifting from 295 to 314 px, and pose 1 not facing (about 22 degrees). Played in
order it stutters. Only the true front (pose 15) and the full back (pose 8) are kept; the duel
view turns them itself (width = |cos angle|, rim thickness at the edge, shading), which is smooth
at any speed and needs two images instead of fifteen.

Each pose is cut out without eating the dark wood of the back (silhouette with holes filled,
not a brightness key) and scaled to one height.

    python research/make_shield_strip.py "<sheet.png>"
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/fx'
HEIGHT = 256
FRONT, BACK = 15, 8   # 1-based pose numbers in reading order (row 1 left to right, then row 2)


def poses(sheet):
    bright = sheet.max(axis=2)
    mask = (bright > 18).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes = [tuple(stats[i][:4]) for i in range(1, n) if stats[i][cv2.CC_STAT_AREA] > 3000]
    split = np.mean([b[1] for b in boxes])
    top = sorted([b for b in boxes if b[1] < split], key=lambda b: b[0]); bottom = sorted([b for b in boxes if b[1] >= split], key=lambda b: b[0])
    return top + bottom


def cutout(sheet, box):
    x, y, w, h = box; pad = 6
    crop = sheet[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
    solid = (crop.max(axis=2) > 18).astype(np.uint8)
    solid = cv2.morphologyEx(solid, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    # Fill holes: everything not reachable from the border through background belongs to the shield.
    flood = (1 - solid).copy(); ff = np.zeros((flood.shape[0] + 2, flood.shape[1] + 2), np.uint8)
    cv2.floodFill(flood, ff, (0, 0), 2)
    shape = np.where(flood == 2, 0, 1).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(shape, 8)
    keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) if n > 1 else 1
    alpha = (labels == keep).astype(np.float32)
    alpha = cv2.GaussianBlur(cv2.erode(alpha, np.ones((2, 2), np.uint8)), (3, 3), 0)
    rgba = np.dstack([crop, (alpha * 255).astype(np.uint8)])
    ys, xs = np.nonzero(alpha > .05)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def main():
    sheet = cv2.imread(sys.argv[1]); found = poses(sheet)
    if len(found) != 15: raise SystemExit(f'Se esperaban 15 poses, hay {len(found)}')
    OUT.mkdir(parents=True, exist_ok=True); meta = {}
    for name, number in (('front', FRONT), ('back', BACK)):
        view = cutout(sheet, found[number - 1])
        view = cv2.resize(view, (round(view.shape[1] * HEIGHT / view.shape[0]), HEIGHT), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(OUT / f'shield-millennium-{name}.png'), view, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        meta[name] = {'pose': number, 'width': view.shape[1], 'height': HEIGHT}
    (OUT / 'shield-millennium.json').write_text(json.dumps({**meta, 'source': 'Hoja generada por el usuario con ChatGPT, 28/09/2026',
        'note': 'Sólo las vistas de frente y reverso; el giro lo calcula web/duel.js'}, indent=2), encoding='utf-8')
    print('ok', meta)


if __name__ == '__main__':
    main()
