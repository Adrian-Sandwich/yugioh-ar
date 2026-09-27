"""Printed playmat: markers found under perspective, zones and positions right, one marker enough, mats told apart."""
import json
import time

import cv2
import numpy as np

from playmat import ZoneTracker
from playmat_print import CARD_MM, TEMPLATE_MM, detect_mats, render, zones_mm

DPI = 60                      # template pixels per inch for the synthetic scene
K = DPI / 25.4


def card_quad(cx, cy, sideways=False):
    w, h = (CARD_MM[1], CARD_MM[0]) if sideways else CARD_MM
    return np.float32([[cx - w / 2, cy - h / 2], [cx + w / 2, cy - h / 2], [cx + w / 2, cy + h / 2], [cx - w / 2, cy + h / 2]])


def scene(templates, placements, size=(1920, 1080)):
    """Wood-coloured table with each template warped by its image corners; returns image and mm->image maps."""
    image = np.full((size[1], size[0], 3), (70, 110, 150), np.uint8); maps = {}
    w, h = TEMPLATE_MM
    for player, corners in placements.items():
        sheet = cv2.cvtColor(templates[player], cv2.COLOR_GRAY2BGR)
        pix = cv2.getPerspectiveTransform(np.float32([[0, 0], [sheet.shape[1], 0], [sheet.shape[1], sheet.shape[0]], [0, sheet.shape[0]]]), np.float32(corners))
        warped = cv2.warpPerspective(sheet, pix, size); mask = cv2.warpPerspective(np.full(sheet.shape[:2], 255, np.uint8), pix, size)
        image[mask > 0] = warped[mask > 0]
        maps[player] = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), np.float32(corners))
    return image, maps


def to_image(mm_to_image, quad_mm):
    return cv2.perspectiveTransform(quad_mm.reshape(-1, 1, 2), mm_to_image).reshape(-1, 2)


def main():
    templates = {p: render(p, DPI) for p in (0, 1)}
    near = [[330, 600], [1590, 600], [1760, 1060], [160, 1060]]
    far = [[1510, 520], [410, 520], [520, 110], [1400, 110]]     # seen from the opponent's side: rotated 180 degrees
    image, maps = scene(templates, {0: near, 1: far})
    started = time.perf_counter(); mats = detect_mats(image); ms = (time.perf_counter() - started) * 1000
    assert sorted(mats) == [0, 1] and all(m.markers == 4 for m in mats.values()), {p: m.markers for p, m in mats.items()}
    checks = [f'both mats found with 4 markers each ({ms:.0f} ms at 1920x1080)']
    n = 0
    for player, mat in mats.items():
        for name, x0, y0, x1, y1 in zones_mm():
            if y0 < 0: continue
            for sideways in (False, True):
                corners = to_image(maps[player], card_quad((x0 + x1) / 2, (y0 + y1) / 2, sideways))
                zone, orientation, _ = mat.locate(corners)
                assert zone == name and orientation == ('sideways' if sideways else 'upright'), (player, name, sideways, zone, orientation)
                n += 1
    checks.append(f'{n} zone/orientation cases on two printed mats')
    # A hand over two corners of player 1's mat: the two markers left still place every zone.
    covered = image.copy()
    for corner in near[2:]:
        cv2.circle(covered, tuple(int(v) for v in corner), 90, (60, 90, 120), -1)
    mats = detect_mats(covered)
    assert mats[0].markers == 2, mats[0].markers
    for name, x0, y0, x1, y1 in zones_mm():
        if y0 < 0: continue
        zone, _, _ = mats[0].locate(to_image(maps[0], card_quad((x0 + x1) / 2, (y0 + y1) / 2)))
        assert zone == name, (name, zone)
    checks.append('two visible markers place every zone')
    # One marker is refused (it placed cards a zone off).
    cv2.circle(covered, tuple(int(v) for v in near[1]), 90, (60, 90, 120), -1)
    assert 0 not in detect_mats(covered)
    checks.append('a single marker is not trusted')
    # The camera moves: the same card follows its zone with no recalibration.
    moved, maps2 = scene(templates, {0: [[500, 420], [1700, 520], [1720, 1000], [380, 960]]})
    mats = detect_mats(moved)
    tracker = ZoneTracker([mats[0]], stable=1)
    z = next(z for z in zones_mm() if z[0] == 'spell:3')
    out = tracker.update([{'track_id': 1, 'card_id': 'x', 'corners': to_image(maps2[0], card_quad((z[1] + z[3]) / 2, (z[2] + z[4]) / 2)).tolist()}])
    assert out and out[0]['zone'] == 'spell:3' and out[0]['player'] == 0, out
    checks.append('camera moved: zones follow the markers')
    # No mat in view.
    assert detect_mats(np.full((1080, 1920, 3), 128, np.uint8)) == {}
    checks.append('empty table: no mats')
    print(json.dumps({'status': 'passed', 'checks': checks}))


if __name__ == '__main__':
    main()
