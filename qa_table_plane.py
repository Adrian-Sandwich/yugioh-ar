"""The table plane from the cards (table_plane.py) and the virtual board laid on it: a synthetic camera
with a known tilt films cards of the real size; the tilt comes back from their corners alone, and the
board's zones come out to scale."""
import math
import tempfile

import cv2
import numpy as np

from playmat import tcg_layout
from table_duel import TableDuel
from table_plane import CardPlane, assumed_focal, board_corners, intrinsics, tilt_deg, unproject

SIZE = (1280, 720)
SPOTS = [(-120, -60, 0), (60, -70, 0), (150, 40, 90), (-40, 60, 0), (-170, 70, 12), (20, -10, 0)]  # x, y mm on the table, turn


def camera(target, distance, tilt):
    """R, t of a camera on the near side looking at `target` (table mm, z into the table), `tilt` degrees from straight down."""
    a = math.radians(tilt); centre = np.float64(target) + distance * np.float64([0, math.sin(a), -math.cos(a)])
    z = np.float64(target) - centre; z /= np.linalg.norm(z); x = np.float64([1, 0, 0]); y = np.cross(z, x)
    R = np.vstack([x, y, z]); return R, -R @ centre


def card_quad(x, y, turn, R, t, K, noise, rng):
    a = math.radians(turn); rot = np.float64([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    pts = np.float64([[-29.5, -43], [29.5, -43], [29.5, 43], [-29.5, 43]]) @ rot.T + [x, y]
    seen = cv2.projectPoints(np.hstack([pts, np.zeros((4, 1))]), cv2.Rodrigues(R)[0], t, K, None)[0].reshape(-1, 2)
    return seen + rng.normal(0, noise, seen.shape)


def detections(quads, status='tracked'):
    return [{'corners': np.float64(q).tolist(), 'geometry_status': status} for q in quads]


def main():
    checks = []; rng = np.random.default_rng(7); f = assumed_focal(SIZE)
    for label, lens, count, tolerance in (('the assumed lens', 1., 6, 2.), ('a lens 12 % longer', 1.12, 6, 6.), ('two cards', 1., 2, 5.)):
        K = intrinsics(f * lens, SIZE); R, t = camera((0, 0, 0), 520, 32)
        quads = [card_quad(x, y, turn, R, t, K, 1., rng) for x, y, turn in SPOTS[:count]]
        plane = CardPlane(); plane.see(detections(quads), SIZE, 10.)
        assert plane.pose is not None and abs(tilt_deg(plane.pose) - 32) < tolerance, (label, plane.pose and tilt_deg(plane.pose))
        centres = unproject([q.mean(axis=0) for q in quads[:2]], intrinsics(f, SIZE), plane.pose[0], plane.pose[1])
        true = math.dist(SPOTS[0][:2], SPOTS[1][:2]); got = float(np.linalg.norm(centres[0] - centres[1]))
        assert abs(got - true) / true < .08, (label, got, true)
        checks.append(f'{label}: tilt {tilt_deg(plane.pose):.1f} degrees (true 32), two cards {got:.0f} mm apart (true {true:.0f})')
    K = intrinsics(f, SIZE); R, t = camera((0, 0, 0), 520, 32)
    quads = [card_quad(x, y, turn, R, t, K, 1., rng) for x, y, turn in SPOTS]
    # The detector's box (no outline) does not count.
    plane = CardPlane(); plane.see(detections(quads, 'unresolved'), SIZE, 10.); assert plane.pose is None
    # A pose is held: noisy readings do not move it; it is redone once with twice the cards; a moved camera is followed after 4 misfits.
    plane = CardPlane(); plane.see(detections(quads), SIZE, 10.); held = plane.pose
    for i in range(12): plane.see(detections([card_quad(x, y, turn, R, t, K, 4., rng) for x, y, turn in SPOTS[:2]]), SIZE, 12. + i)
    assert plane.pose is held
    few = CardPlane(); few.see(detections(quads[:2]), SIZE, 10.); first = few.pose
    few.see(detections(quads[:3]), SIZE, 12.); assert few.pose is first
    few.see(detections(quads[:5]), SIZE, 14.); assert few.pose is not first and few.pose[3] == 5
    R2, t2 = camera((30, 10, 0), 600, 50); moved = [card_quad(x + 31, y + 17, turn, R2, t2, K, 1., rng) for x, y, turn in SPOTS[:4]]
    for now in (30., 31.5, 33.): plane.see(detections(moved), SIZE, now)
    assert plane.pose is held
    plane.see(detections(moved), SIZE, 34.5); assert abs(tilt_deg(plane.pose) - 50) < 4 and plane.pose[3] == 4
    checks.append('the pose is held through noise, redone once with more cards, and follows a moved camera')
    # It survives a restart.
    with tempfile.TemporaryDirectory() as folder:
        from pathlib import Path
        path = Path(folder) / 'camera_pose.json'; saved = CardPlane(path); saved.see(detections(quads), SIZE, 10.)
        again = CardPlane(path); assert again.pose is not None and np.allclose(again.pose[0], saved.pose[0]) and again.image_size == SIZE
    # The board laid on the plane: every zone is a true rectangle of the layout's size on the table.
    plane = CardPlane(); plane.see(detections(quads), SIZE, 10.)
    params = {'cx': .5, 'cy': .5, 'width': .5, 'rotation': 20., 'gap': .08}
    one = board_corners('one', params, SIZE, plane.pose); two = board_corners('two', params, SIZE, plane.pose)
    Kf = intrinsics(f, SIZE); on_table = unproject(one[0]['corners'], Kf, plane.pose[0], plane.pose[1])
    sides = [float(np.linalg.norm(on_table[i] - on_table[(i + 1) % 4])) for i in range(4)]
    assert np.allclose(sides, [300, 175, 300, 175], atol=.5), sides
    assert np.allclose(on_table.mean(axis=0), unproject([[640, 360]], Kf, plane.pose[0], plane.pose[1])[0], atol=.5)
    near, far = (np.float64(m['corners']) for m in two)
    assert far[:, 1].mean() < near[:, 1].mean() and cv2.contourArea(np.float32(far)) < cv2.contourArea(np.float32(near)), 'the far board is higher in the picture and smaller'
    checks.append(f'board on the plane: a 300 x 175 mm rectangle on the table, sides {np.round(sides).tolist()}')
    # In the duel: a metric board needs the plane; without it the board is drawn by eye and says so. With it,
    # a monster zone is as wide on the table as the layout says, and a card fits in it, at any tilt.
    with tempfile.TemporaryDirectory() as folder:
        table = TableDuel(folder=folder)
        by_eye = table.preview('one', {'metric': True}, list(SIZE))
        assert by_eye['virtual']['metric'] is False and by_eye['plane'] is None
        table.calibrate('one', [], list(SIZE), virtual={'metric': True, 'cx': .5, 'cy': .5, 'width': .5})
        assert table.virtual['metric'] is False
        table.see_cards(detections(quads), 10.)
        assert table.plane(SIZE) is not None and table.virtual['metric'] is False, 'a board drawn by eye stays as it was drawn'
        board = table.calibrate('one', [], list(SIZE), virtual={'metric': True, 'cx': .5, 'cy': .5, 'width': .5})
        assert board['virtual']['metric'] is True and board['plane']['cards'] == 6 and abs(board['plane']['tilt_deg'] - 32) < 2, board['plane']
        assert board['plane']['fits'] and board['plane']['back_mm'] == 0, board['plane']
        # A life-size mat from this close does not fit: the answer says how much farther the camera must go.
        big = table.preview('one', {'metric': True, 'cx': .5, 'cy': .5, 'width': 1.}, list(SIZE))['plane']
        assert big['fits'] is False and big['reach'] > 1.05 and abs(big['back_mm'] - (big['reach'] - 1) * big['distance_mm']) < 1, big
        zone = next(z for z in board['zones'] if z['zone'] == 'monster:2')
        zone_mm = unproject(zone['polygon'], Kf, plane.pose[0], plane.pose[1])
        _, x0, y0, x1, y1 = next(z for z in tcg_layout() if z[0] == 'monster:2')
        width, height = float(np.linalg.norm(zone_mm[1] - zone_mm[0])), float(np.linalg.norm(zone_mm[3] - zone_mm[0]))
        assert abs(width - (x1 - x0) * 300) < .5 and abs(height - (y1 - y0) * 175) < .5, (width, height)
        # The camera moves: the board follows the new plane on its own, still to scale, and is saved.
        before = [m.corners.copy() for m in table.mats]
        for now in (30., 31.5, 33., 34.5): table.see_cards(detections(moved), now)
        assert not np.allclose(before[0], table.mats[0].corners, atol=2), 'the board must follow the moved camera'
        again = TableDuel(folder=folder)
        assert again.virtual['metric'] is True and np.allclose(again.mats[0].corners, table.mats[0].corners, atol=.01) and again.plane(SIZE) is not None
    checks.append(f'duel: a metric board waits for the plane, then monster:2 is {width:.0f} x {height:.0f} mm on the table; it follows a moved camera and survives a restart')
    for c in checks: print('ok', c)


if __name__ == '__main__':
    main()
