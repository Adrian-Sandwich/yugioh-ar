"""Relief of the Millennium shield for its 3D mesh (web/shield3d.js): from its two drawings in web/fx
(front and back), a map per side that tells the 3D mesh how thick the shield is and the material how
each point catches the light.

    python tools/make_shield_relief.py            # writes web/fx/shield-millennium-{front,back}-relief.png
    python tools/make_shield_relief.py --preview .runtime/shield-preview.png   # also a lit preview to look at

Each map is twice the drawing's size, RGBA, linear (not colour):
    R, G  the surface normal's x and y (image right and down), 0.5 = facing the viewer
    B     how metallic the point is (gold and steel 1, lacquer, leather and wood low)
    A     height, 0 outside the shield and 1..255 inside it

The height is made up, not measured: a dome over the whole silhouette, a bevel at its edge, and the
gold (rim, eye, studs) and the gems raised over the field, each found by its colour.
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
FX = ROOT / 'web/fx'
SCALE = 2
# The mesh makes a height of 1 this many pixels of the map deep (shield3d.js: relief depth over the
# shield's height, times the map's height); the normals are baked for it, a little exaggerated.
DEPTH_PX = {'front': .05 * 256 * SCALE, 'back': .025 * 256 * SCALE}
EXAGGERATE = 1.6


def smooth(mask, sigma):
    return cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)


def relief(side):
    art = cv2.imread(str(FX / f'shield-millennium-{side}.png'), cv2.IMREAD_UNCHANGED)
    art = cv2.resize(art, None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    bgr, alpha = art[..., :3], art[..., 3]
    inside = alpha > 127
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV).astype(np.float32)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255
    dist = cv2.distanceTransform(inside.astype(np.uint8), cv2.DIST_L2, 5)
    dome = np.sqrt(dist / dist.max())
    bevel = np.clip(dist / (3. * SCALE), 0, 1); bevel = bevel * bevel * (3 - 2 * bevel)
    gold = inside & (hue >= 8) & (hue <= 30) & (sat > 95) & (val > 115)
    # Painted light and shade read as a little relief of their own.
    paint = gray - smooth(gray, 5 * SCALE)
    if side == 'front':
        gem = inside & (hue >= 95) & (hue <= 125) & (sat > 110)
        gem_dist = cv2.distanceTransform(gem.astype(np.uint8), cv2.DIST_L2, 5)
        gems = np.clip(gem_dist / max(gem_dist.max(), 1), 0, 1) ** .6
        height = .22 + .34 * dome + .26 * smooth(gold, 1.2 * SCALE) + .3 * smooth(gems, .8 * SCALE) + .5 * paint
        metal = np.maximum(smooth(gold, .8 * SCALE), .55 * smooth(gem, .8 * SCALE))
        metal = np.maximum(metal, .12)  # the red field: lacquer, a faint gloss
    else:
        steel = inside & (sat < 60) & (val > 105)                              # studs and plates
        leather = inside & (hue >= 3) & (hue <= 22) & (sat > 90) & (val <= 150) & ~gold  # the straps
        height = .3 + .22 * dome + .3 * smooth(gold, 1.2 * SCALE) + .28 * smooth(steel, 1. * SCALE) + .22 * smooth(leather, 1.5 * SCALE) + .2 * paint
        metal = np.maximum(smooth(gold, .8 * SCALE), .9 * smooth(steel, .8 * SCALE))
        metal = np.maximum(metal, .4 * (1 - smooth(leather, 1. * SCALE)))      # the dark boards: old iron
    height = smooth(np.clip(height, 0, None) * bevel, .7 * SCALE)
    height = np.where(inside, height / height.max(), 0)
    k = DEPTH_PX[side] * EXAGGERATE
    nx = -cv2.Sobel(height, cv2.CV_32F, 1, 0, ksize=3, scale=1 / 8) * k
    ny = -cv2.Sobel(height, cv2.CV_32F, 0, 1, ksize=3, scale=1 / 8) * k
    norm = np.sqrt(nx * nx + ny * ny + 1)
    out = np.zeros(art.shape[:2] + (4,), np.uint8)   # written as BGRA
    out[..., 2] = np.clip(np.round((nx / norm * .5 + .5) * 255), 0, 255)
    out[..., 1] = np.clip(np.round((ny / norm * .5 + .5) * 255), 0, 255)
    out[..., 0] = np.clip(np.round(metal * 255), 0, 255)
    out[..., 3] = np.where(inside, np.clip(np.round(height * 255), 1, 255), 0)
    return art, out


def preview(art, rel):
    """The shield lit from the top left, as the material does it (roughly): to judge the relief by eye."""
    n = np.dstack([rel[..., 2] / 127.5 - 1, rel[..., 1] / 127.5 - 1]); z = np.sqrt(np.clip(1 - (n ** 2).sum(-1), 0, 1))
    metal = rel[..., 0:1] / 255.; base = (art[..., :3] / 255.) ** 2.2
    light = np.float32([-.45, -.6, .66]); light /= np.linalg.norm(light)
    ndl = np.clip(n[..., 0] * light[0] + n[..., 1] * light[1] + z * light[2], 0, 1)[..., None]
    half = light + [0, 0, 1]; half /= np.linalg.norm(half)
    ndh = np.clip(n[..., 0] * half[0] + n[..., 1] * half[1] + z * half[2], 0, 1)[..., None]
    col = base * (1 - metal) * (.45 + .65 * ndl) + base * metal * (.25 + 1.1 * ndl) + (.04 + .96 * metal * base) * ndh ** 60 * 3
    col = np.clip(col, 0, 1) ** (1 / 2.2) * (rel[..., 3:4] > 0)
    return np.round(col * 255).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--preview', help='also write a lit preview of both sides to this PNG')
    a = ap.parse_args()
    views = []
    for side in ('front', 'back'):
        art, rel = relief(side)
        path = FX / f'shield-millennium-{side}-relief.png'
        cv2.imwrite(str(path), rel)
        print(f'{path.relative_to(ROOT)}: {rel.shape[1]}x{rel.shape[0]}, altura media {rel[..., 3][rel[..., 3] > 0].mean() / 255:.2f}')
        if a.preview:
            lit = preview(art, rel); views += [lit, np.dstack([rel[..., 3]] * 3), np.dstack([rel[..., 0]] * 3)]
    if a.preview:
        h = max(v.shape[0] for v in views)
        row = np.hstack([cv2.copyMakeBorder(v, 0, h - v.shape[0], 0, 8, cv2.BORDER_CONSTANT) for v in views])
        Path(a.preview).parent.mkdir(parents=True, exist_ok=True); cv2.imwrite(a.preview, row)
        print(a.preview)


if __name__ == '__main__':
    main()
