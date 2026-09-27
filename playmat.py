"""Playmat map: camera pixels -> mat coordinates -> duel zone and battle position.

Calibration is four image points per mat, the mat's corners as its own player
sees them: top-left, top-right, bottom-right, bottom-left (top = the side facing
the opponent). A homography sends them to the unit square, x to the right and y
toward the player, so a camera at any angle gives the same mat coordinates. One
calibration per player: two mats facing each other, or one shared play area
calibrated twice (one quadrilateral per half).

The default layout is the official single-player TCG mat: upper row field zone,
five Main Monster Zones and graveyard; lower row Extra Deck, five Spell & Trap
Zones (the outer two double as Pendulum Zones) and Deck. The two Extra Monster
Zones are shared and sit off the mat, between the players, above Main Monster
Zones 1 and 3 (negative y). Zone names follow duel_engine: monster:0-4,
spell:0-4, field, extra_monster:0-1; piles are graveyard, banished, deck,
extra_deck.

Nothing here decides a duel event. `ZoneTracker` only reports where each tracked
card has been stable; duel_engine.observe compares that with its model and the
players explain any difference.
"""
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
CALIBRATION = ROOT / 'data/playmat/calibration.json'
UNIT = np.float32([[0, 0], [1, 0], [1, 1], [0, 1]])


def tcg_layout():
    """Zones of one official TCG mat as (name, x0, y0, x1, y1) in mat units."""
    column = 1 / 7
    zones = [('field', 0, 0, column, .5), ('graveyard', 6 * column, 0, 1, .5),
             ('extra_deck', 0, .5, column, 1), ('deck', 6 * column, .5, 1, 1)]
    for i in range(5):
        zones.append((f'monster:{i}', (i + 1) * column, 0, (i + 2) * column, .5))
        zones.append((f'spell:{i}', (i + 1) * column, .5, (i + 2) * column, 1))
    # Shared Extra Monster Zones, off the mat toward the opponent, over Main Monster Zones 1 and 3.
    zones.append(('extra_monster:0', 2 * column, -.55, 3 * column, -.05))
    zones.append(('extra_monster:1', 4 * column, -.55, 5 * column, -.05))
    return zones


class Mat:
    def __init__(self, player, corners, layout=None, margin=.08, size_mm=(600, 350)):
        """`corners`: image points TL, TR, BR, BL of this player's mat. `margin`:
        fraction of a zone's size near its border where a card center is ambiguous.
        `size_mm`: physical mat size; mat units are anisotropic (x spans the width,
        y the height), so orientation is judged in millimetres."""
        corners = np.float32(corners).reshape(4, 2)
        if not cv2.isContourConvex(corners) or cv2.contourArea(corners) < 100:
            raise ValueError('Esquinas del tapete inválidas: deben formar un cuadrilátero convexo')
        self.player = player; self.corners = corners; self.margin = margin; self.size_mm = np.float32(size_mm)
        self.layout = layout or tcg_layout()
        self.to_mat = cv2.getPerspectiveTransform(corners, UNIT)
        self.to_image = cv2.getPerspectiveTransform(UNIT, corners)

    def mat_points(self, points):
        return cv2.perspectiveTransform(np.float32(points).reshape(-1, 1, 2), self.to_mat).reshape(-1, 2)

    def image_points(self, points):
        return cv2.perspectiveTransform(np.float32(points).reshape(-1, 1, 2), self.to_image).reshape(-1, 2)

    def locate(self, card_corners):
        """(zone, position, mat_center) for one card, or (None, position, center) if
        its center is outside every zone or too close to a zone border to decide.

        Position is 'upright' when the card's long side runs along the mat's y axis
        (Attack Position for a monster) and 'sideways' otherwise (Defense Position).
        Face-down is not decided here: the caller knows whether it saw a card back.
        """
        quad = self.mat_points(card_corners)
        center = quad.mean(0)
        # Long side of the card, in millimetres on the mat: the longer of its two side pairs.
        mm = quad * self.size_mm
        a = (mm[1] - mm[0] + mm[2] - mm[3]) / 2; b = (mm[3] - mm[0] + mm[2] - mm[1]) / 2
        long = a if np.linalg.norm(a) > np.linalg.norm(b) else b
        position = 'upright' if abs(long[1]) >= abs(long[0]) else 'sideways'
        for name, x0, y0, x1, y1 in self.layout:
            mx, my = (x1 - x0) * self.margin, (y1 - y0) * self.margin
            if x0 + mx <= center[0] <= x1 - mx and y0 + my <= center[1] <= y1 - my:
                return name, position, center
        return None, position, center


def battle_position(zone, orientation, facedown):
    """duel_engine position for a card seen in `zone`."""
    if zone.startswith(('monster:', 'extra_monster:')):
        if facedown: return 'facedown_defense'
        return 'attack' if orientation == 'upright' else 'defense'
    if zone.startswith('spell:') or zone == 'field':
        return 'facedown' if facedown else 'faceup'
    return None


class ZoneTracker:
    """Per tracked card, report a zone only after `stable` consecutive agreeing sightings.

    A hand passing over the mat, or a card being slid across zones, produces
    short-lived or ambiguous readings; those never reach the duel model.
    """
    def __init__(self, mats, stable=3):
        self.mats = mats; self.stable = stable; self.state = {}

    def update(self, tracks):
        """`tracks`: dicts with track_id, corners, optional card_id and facedown.
        Returns stable observations: player, zone, copy_id, card_id, position."""
        out, seen = [], set()
        for track in tracks:
            key = track['track_id']; seen.add(key)
            reading = None
            for mat in self.mats:
                zone, orientation, _ = mat.locate(track['corners'])
                if zone:
                    reading = (mat.player, zone, battle_position(zone, orientation, bool(track.get('facedown')))); break
            previous = self.state.get(key)
            count = previous[1] + 1 if previous and previous[0] == reading else 1
            self.state[key] = (reading, count)
            if reading and count >= self.stable:
                player, zone, position = reading
                out.append({'player': player, 'zone': zone, 'copy_id': key, 'card_id': None if track.get('facedown') else track.get('card_id'),
                            'position': position})
        for key in [k for k in self.state if k not in seen]:
            del self.state[key]
        return out


def load(path=CALIBRATION):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    return [Mat(m['player'], m['corners'], size_mm=m.get('size_mm', (600, 350))) for m in data['mats']]


def save(mats, image_size, path=CALIBRATION):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps({'layout': 'tcg-single', 'image_size': list(image_size),
                                      'mats': [{'player': m.player, 'corners': m.corners.tolist(), 'size_mm': m.size_mm.tolist()} for m in mats]}, indent=2), encoding='utf-8')
