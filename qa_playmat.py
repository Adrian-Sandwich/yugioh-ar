"""Playmat map: zones and positions under perspective, two facing mats, ambiguity, stability."""
import json
import numpy as np
from playmat import Mat, ZoneTracker, battle_position, tcg_layout

MAT_W, MAT_H = 600., 350.   # mm, official single-player mat
CARD_W, CARD_H = 59., 86.


def center(zone):
    """Centre of a zone of the official layout, in mat units."""
    _, x0, y0, x1, y1 = next(z for z in tcg_layout() if z[0] == zone)
    return (x0 + x1) / 2, (y0 + y1) / 2


def card_in_mat(cx, cy, sideways=False):
    """Card corners TL,TR,BR,BL in mat units, centred on (cx, cy)."""
    w, h = (CARD_H, CARD_W) if sideways else (CARD_W, CARD_H)
    w, h = w / MAT_W / 2, h / MAT_H / 2
    return np.float32([[cx - w, cy - h], [cx + w, cy - h], [cx + w, cy + h], [cx - w, cy + h]])


def main():
    # Camera looking down at an angle: near player's mat wide at the bottom of the image,
    # the opponent's mat above it, narrower and seen from its own side (rotated 180 degrees).
    near = Mat(0, [[420, 610], [1500, 610], [1640, 1020], [280, 1020]])
    far = Mat(1, [[1430, 470], [490, 470], [560, 170], [1360, 170]])
    checks, n = [], 0
    for mat in (near, far):
        for name, x0, y0, x1, y1 in tcg_layout():
            if name.startswith('extra_monster') and mat is far: continue
            for sideways in (False, True):
                corners = mat.image_points(card_in_mat((x0 + x1) / 2, (y0 + y1) / 2, sideways))
                zone, orientation, _ = mat.locate(corners)
                assert zone == name and orientation == ('sideways' if sideways else 'upright'), (mat.player, name, sideways, zone, orientation)
                n += 1
    checks.append(f'{n} zone/orientation cases under perspective on two facing mats')
    # Card order does not matter for orientation (a card upside down or listed from another corner).
    corners = near.image_points(card_in_mat(*center('monster:1')))
    assert near.locate(np.roll(corners, 2, axis=0))[:2] == ('monster:1', 'upright')
    assert near.locate(np.roll(corners, 1, axis=0))[:2] == ('monster:1', 'upright')
    checks.append('orientation independent of corner order')
    # A center on a zone border, or off the mat, is not assigned.
    assert near.locate(near.image_points(card_in_mat((center('monster:0')[0] + center('monster:1')[0]) / 2, center('monster:0')[1])))[0] is None
    assert near.locate(near.image_points(card_in_mat(.5, 1.4)))[0] is None
    checks.append('border and off-mat cards unassigned')
    # Positions for the duel model.
    assert battle_position('monster:2', 'upright', False) == 'attack' and battle_position('monster:2', 'sideways', False) == 'defense'
    assert battle_position('monster:2', 'sideways', True) == 'facedown_defense' and battle_position('extra_monster:0', 'upright', False) == 'attack'
    assert battle_position('spell:0', 'upright', True) == 'facedown' and battle_position('field', 'upright', False) == 'faceup'
    assert battle_position('graveyard', 'upright', False) is None
    checks.append('duel positions')
    # Stability: three agreeing sightings before an observation; a move restarts the count.
    tracker = ZoneTracker([near, far], stable=3)
    card = {'track_id': 7, 'card_id': 'blue-eyes', 'corners': near.image_points(card_in_mat(*center('monster:2'))).tolist()}
    assert tracker.update([card]) == [] and tracker.update([card]) == []
    third = tracker.update([card])
    assert third == [{'player': 0, 'zone': 'monster:2', 'copy_id': 7, 'card_id': 'blue-eyes', 'position': 'attack'}], third
    moved = {**card, 'corners': near.image_points(card_in_mat(*center('monster:3'), sideways=True)).tolist()}
    assert tracker.update([moved]) == [] and tracker.update([moved]) == []
    assert tracker.update([moved])[0]['zone'] == 'monster:3' and tracker.state[7][0][2] == 'defense'
    checks.append('observation after 3 stable sightings; a move restarts the count')
    # Face-down card: identity withheld even if the recognizer guessed one.
    back = {'track_id': 9, 'card_id': 'guess', 'facedown': True, 'corners': far.image_points(card_in_mat(*center('spell:0'))).tolist()}
    for _ in range(3): result = tracker.update([back])
    assert result == [{'player': 1, 'zone': 'spell:0', 'copy_id': 9, 'card_id': None, 'position': 'facedown'}], result
    assert 7 not in tracker.state, 'tracks that disappeared are forgotten'
    checks.append('face-down: no identity; vanished tracks forgotten')
    # Invalid calibration.
    try: Mat(0, [[0, 0], [10, 10], [0, 10], [10, 0]]); raise AssertionError('self-intersecting corners accepted')
    except ValueError: pass
    checks.append('invalid corners rejected')
    print(json.dumps({'status': 'passed', 'checks': checks}))


if __name__ == '__main__':
    main()
