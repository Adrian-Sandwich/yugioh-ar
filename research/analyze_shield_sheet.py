"""Does each pose of the Millennium shield sheet belong to one steady turn?

For a shield turning on its vertical axis, seen at one scale, the visible width follows
|cos(angle)| (plus the rim thickness), and what shows is the red face (front half of the turn)
or the dark wood (back half). Per pose: height, width, share of red face and of wood, and on
which side each lies; the angle estimated from the width; and the step between poses.

    python research/analyze_shield_sheet.py "<sheet.png>"
"""
import json, math, sys
import cv2, numpy as np
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1]))
from research.make_shield_strip import poses, cutout

sheet = cv2.imread(sys.argv[1])
rows = []
for i, box in enumerate(poses(sheet)):
    rgba = cutout(sheet, box); a = rgba[..., 3] > 128
    hsv = cv2.cvtColor(rgba[..., :3], cv2.COLOR_BGR2HSV)
    red = a & (((hsv[..., 0] < 8) | (hsv[..., 0] > 170)) & (hsv[..., 1] > 120) & (hsv[..., 2] > 90))
    wood = a & (hsv[..., 1] < 70) & (hsv[..., 2] < 110)
    xs = np.nonzero(a)[1]; mid = (xs.min() + xs.max()) / 2
    side = lambda m: 'izq' if m.any() and np.nonzero(m)[1].mean() < mid - 3 else 'der' if m.any() and np.nonzero(m)[1].mean() > mid + 3 else 'centro'
    rows.append({'pose': i + 1, 'alto': rgba.shape[0], 'ancho': rgba.shape[1], 'ancho_rel': rgba.shape[1] / rgba.shape[0],
                 'rojo': round(red.sum() / a.sum(), 3), 'madera': round(wood.sum() / a.sum(), 3), 'lado_rojo': side(red), 'lado_madera': side(wood)})
full = max(r['ancho_rel'] for r in rows); edge = min(r['ancho_rel'] for r in rows)
for r in rows:
    c = max(0., min(1., (r['ancho_rel'] - edge) / (full - edge)))
    base = math.degrees(math.acos(c))                     # 0 = facing, 90 = edge-on
    r['angulo'] = round(base if r['madera'] < r['rojo'] else 180 - base)
prev = None
for r in rows:
    r['paso'] = None if prev is None else r['angulo'] - prev; prev = r['angulo']
    print(f"{r['pose']:2d} alto {r['alto']:3d} ancho {r['ancho']:3d} rel {r['ancho_rel']:.2f} rojo {r['rojo']:.2f} ({r['lado_rojo']:6}) madera {r['madera']:.2f} ({r['lado_madera']:6}) ángulo≈{r['angulo']:3d}° paso {r['paso']}")
print(json.dumps({'alturas': [r['alto'] for r in rows]}))
