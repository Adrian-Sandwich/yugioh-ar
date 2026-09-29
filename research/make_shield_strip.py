"""Millennium shield sprite sheet (black background, 15 poses of one turn) -> web/fx/shield-millennium.png.

The sheet is two rows (8 + 7 poses) of a shield turning 360 degrees on its vertical axis. Each
pose is cut out, its black background made transparent without eating the dark wood of the back
(the silhouette is the region connected to the pose, holes filled, not a brightness key), scaled
to one height (the later poses are drawn larger) and centred in equal cells of one horizontal strip.

    python research/make_shield_strip.py "<sheet.png>"  -> web/fx/shield-millennium.png + .json
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'web/fx'
HEIGHT = 256


def poses(sheet):
    bright = sheet.max(axis=2)
    mask = (bright > 18).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes = [tuple(stats[i][:4]) for i in range(1, n) if stats[i][cv2.CC_STAT_AREA] > 3000]
    rows = sorted(boxes, key=lambda b: b[1])
    split = np.mean([b[1] for b in rows])
    top = sorted([b for b in boxes if b[1] < split], key=lambda b: b[0]); bottom = sorted([b for b in boxes if b[1] >= split], key=lambda b: b[0])
    return top + bottom


def cutout(sheet, box):
    x, y, w, h = box; pad = 6
    crop = sheet[max(0, y - pad):y + h + pad, max(0, x - pad):x + w + pad]
    bright = crop.max(axis=2)
    solid = (bright > 18).astype(np.uint8)
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
    sheet = cv2.imread(sys.argv[1])
    frames = [cutout(sheet, b) for b in poses(sheet)]
    if len(frames) != 15: raise SystemExit(f'Se esperaban 15 poses, hay {len(frames)}')
    scaled = [cv2.resize(f, (max(1, round(f.shape[1] * HEIGHT / f.shape[0])), HEIGHT), interpolation=cv2.INTER_AREA) for f in frames]
    cell = max(f.shape[1] for f in scaled) + 4
    strip = np.zeros((HEIGHT, cell * len(scaled), 4), np.uint8)
    for i, f in enumerate(scaled):
        x0 = i * cell + (cell - f.shape[1]) // 2; strip[:, x0:x0 + f.shape[1]] = f
    OUT.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT / 'shield-millennium.png'), strip, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    (OUT / 'shield-millennium.json').write_text(json.dumps({'frames': len(scaled), 'cell_width': cell, 'height': HEIGHT,
        'widths': [f.shape[1] for f in scaled], 'source': 'Hoja generada por el usuario con ChatGPT, 28/09/2026'}, indent=2), encoding='utf-8')
    print('ok', len(scaled), 'cuadros; celda', cell, 'x', HEIGHT, '; anchos', [f.shape[1] for f in scaled])


if __name__ == '__main__':
    main()
