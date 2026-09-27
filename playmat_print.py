"""Printable playmat with ArUco markers: zones the players can see, a mat the camera finds alone.

One template per player. Zone outlines (corner brackets and labels, as in AR
duel demos) show where each card goes; four ArUco markers outside the zones,
one per corner, let the viewer recover the mat's homography on every frame, so
neither the camera nor the mat has to stay still and nobody clicks corners.
Every marker contributes its own four corners at known millimetre positions:
one visible marker is enough, more make the fit robust to a hand over the mat.

Player 1 uses marker ids 0-3 and player 2 ids 4-7 (DICT_4X4_50), so two mats
facing each other are told apart. Geometry is in millimetres, the frame of
reference playmat.Mat uses (TEMPLATE_MM).

    .venv-eval/Scripts/python.exe playmat_print.py            # data/playmat/print/*.png and *.pdf
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'data/playmat/print'
DICTIONARY = cv2.aruco.DICT_4X4_50
CARD_MM = (59, 86)
ZONE_MM = (74, 100)          # a card with room to place it
GAP_MM = 6
MARKER_MM = 40
MARGIN_MM = 12               # paper edge to marker
# Zone grid: 7 columns x 2 rows; markers sit in the corners outside it.
GRID_W = 7 * ZONE_MM[0] + 6 * GAP_MM
GRID_H = 2 * ZONE_MM[1] + GAP_MM
GRID_X = MARGIN_MM + MARKER_MM + 10
GRID_Y = MARGIN_MM + MARKER_MM + 4
TEMPLATE_MM = (GRID_X * 2 + GRID_W, GRID_Y * 2 + GRID_H)   # whole printed sheet
LABELS = {'field': 'CAMPO', 'graveyard': 'CEMENTERIO', 'extra_deck': 'MAZO EXTRA', 'deck': 'MAZO'}


def zones_mm():
    """(name, x0, y0, x1, y1) in template millimetres; row 0 faces the opponent."""
    out = []
    columns = ['field'] + [f'monster:{i}' for i in range(5)] + ['graveyard']
    lower = ['extra_deck'] + [f'spell:{i}' for i in range(5)] + ['deck']
    for row, names in enumerate((columns, lower)):
        for col, name in enumerate(names):
            x0 = GRID_X + col * (ZONE_MM[0] + GAP_MM); y0 = GRID_Y + row * (ZONE_MM[1] + GAP_MM)
            out.append((name, x0, y0, x0 + ZONE_MM[0], y0 + ZONE_MM[1]))
    # Shared Extra Monster Zones: off the sheet toward the opponent, above Main Monster Zones 2 and 4.
    for i, col in enumerate((2, 4)):
        x0 = GRID_X + col * (ZONE_MM[0] + GAP_MM)
        out.append((f'extra_monster:{i}', x0, -ZONE_MM[1] - 30, x0 + ZONE_MM[0], -30))
    return out


def markers_mm(player):
    """{marker id: 4x2 corners (TL, TR, BR, BL) in template mm} for one player's mat."""
    w, h = TEMPLATE_MM; m, s = MARGIN_MM, MARKER_MM
    origins = [(m, m), (w - m - s, m), (w - m - s, h - m - s), (m, h - m - s)]   # TL, TR, BR, BL corners of the sheet
    return {4 * player + i: np.float32([[x, y], [x + s, y], [x + s, y + s], [x, y + s]]) for i, (x, y) in enumerate(origins)}


_detector = None


def detect_mats(image, max_error_px=4., min_markers=2):
    """{player: playmat.Mat} for every printed mat with at least `min_markers` markers
    visible in `image` (BGR or grey). Each marker gives four point pairs, fitted with
    RANSAC; a fit whose reprojection error exceeds `max_error_px` (a misread marker, a
    bent sheet) is dropped rather than trusted. One marker alone is not enough: its
    40 mm extrapolated across the mat put a card one whole zone off in the test, so
    callers keep the last good mat while a hand covers the others."""
    from playmat import Mat
    global _detector
    if _detector is None:
        _detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(DICTIONARY), cv2.aruco.DetectorParameters())
    grey = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector.detectMarkers(grey)
    if ids is None: return {}
    known = {p: markers_mm(p) for p in (0, 1)}
    found = {}
    for quad, marker_id in zip(corners, ids.ravel()):
        player = int(marker_id) // 4
        if player in known and int(marker_id) in known[player]:
            found.setdefault(player, []).append((quad.reshape(4, 2), known[player][int(marker_id)]))
    layout = [z for z in zones_mm()]; w, h = TEMPLATE_MM
    outline = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    mats = {}
    for player, pairs in found.items():
        if len(pairs) < min_markers: continue
        src = np.concatenate([p[0] for p in pairs]).astype(np.float32); dst = np.concatenate([p[1] for p in pairs]).astype(np.float32)
        to_mat, _ = cv2.findHomography(src, dst, cv2.RANSAC if len(pairs) > 1 else 0, 3.)
        if to_mat is None: continue
        back = cv2.perspectiveTransform(dst.reshape(-1, 1, 2), np.linalg.inv(to_mat)).reshape(-1, 2)
        error = float(np.abs(back - src).max())
        if error > max_error_px: continue
        mats[player] = Mat.from_homography(player, to_mat, layout, outline)
        mats[player].markers = len(pairs); mats[player].error_px = round(error, 2)
    return mats


def zone_label(name):
    kind, _, index = name.partition(':')
    if kind == 'monster': return f'M{int(index) + 1}'
    if kind == 'spell': return f'MT{int(index) + 1}'
    return LABELS.get(name, name)


def render(player, dpi=150):
    """Template image (white paper) at `dpi`."""
    k = dpi / 25.4; w, h = TEMPLATE_MM
    image = np.full((round(h * k), round(w * k)), 255, np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(DICTIONARY)
    for marker_id, corners in markers_mm(player).items():
        x, y = corners[0]; size = round(MARKER_MM * k)
        tile = cv2.aruco.generateImageMarker(dictionary, marker_id, size, borderBits=1)
        image[round(y * k):round(y * k) + size, round(x * k):round(x * k) + size] = tile
    font = cv2.FONT_HERSHEY_DUPLEX
    for name, x0, y0, x1, y1 in zones_mm():
        if y0 < 0: continue
        p0, p1 = (round(x0 * k), round(y0 * k)), (round(x1 * k), round(y1 * k)); arm = round(14 * k); t = max(2, round(1.2 * k))
        for (cx, cy), (dx, dy) in (((p0[0], p0[1]), (1, 1)), ((p1[0], p0[1]), (-1, 1)), ((p1[0], p1[1]), (-1, -1)), ((p0[0], p1[1]), (1, -1))):
            cv2.line(image, (cx, cy), (cx + dx * arm, cy), 0, t); cv2.line(image, (cx, cy), (cx, cy + dy * arm), 0, t)
        text = zone_label(name); scale = .16 * k if len(text) <= 3 else .09 * k
        (tw, th), _ = cv2.getTextSize(text, font, scale, max(1, t // 2))
        cv2.putText(image, text, ((p0[0] + p1[0] - tw) // 2, (p0[1] + p1[1] + th) // 2), font, scale, 150, max(1, t // 2), cv2.LINE_AA)
    title = f'JUGADOR {player + 1}  -  lado del rival arriba  -  marcadores {4 * player}-{4 * player + 3}'
    cv2.putText(image, title, (round(GRID_X * k), round((GRID_Y - 6) * k)), font, .1 * k, 120, 1, cv2.LINE_AA)
    return image


def tiles(image, dpi, paper_mm=(279.4, 215.9), overlap_mm=10):
    """Split the template into landscape pages with overlap and alignment crosses."""
    k = dpi / 25.4; pw, ph = round(paper_mm[0] * k), round(paper_mm[1] * k); step_x, step_y = pw - round(overlap_mm * k), ph - round(overlap_mm * k)
    pages = []
    for y in range(0, image.shape[0], step_y):
        for x in range(0, image.shape[1], step_x):
            page = np.full((ph, pw), 255, np.uint8); part = image[y:y + ph, x:x + pw]
            page[:part.shape[0], :part.shape[1]] = part
            cv2.putText(page, f'hoja {len(pages) + 1}: fila {y // step_y + 1}, columna {x // step_x + 1} (se solapan {overlap_mm} mm)', (round(8 * k), ph - round(4 * k)), cv2.FONT_HERSHEY_SIMPLEX, .05 * k, 160, 1)
            pages.append(page)
            if x + pw >= image.shape[1]: break
        if y + ph >= image.shape[0]: break
    return pages


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dpi', type=int, default=150)
    args = parser.parse_args()
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    for player in (0, 1):
        image = render(player, args.dpi)
        png = OUT / f'tapete-jugador{player + 1}.png'; cv2.imwrite(str(png), image)
        Image.fromarray(image).save(OUT / f'tapete-jugador{player + 1}-una-pieza.pdf', resolution=args.dpi)
        pages = [Image.fromarray(p) for p in tiles(image, args.dpi)]
        pages[0].save(OUT / f'tapete-jugador{player + 1}-hojas-carta.pdf', save_all=True, append_images=pages[1:], resolution=args.dpi)
        print(f'jugador {player + 1}: {TEMPLATE_MM[0]:.0f} x {TEMPLATE_MM[1]:.0f} mm, {len(pages)} hojas carta -> {png.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
