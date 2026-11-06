"""Camera over the table (scene3d.py): a synthetic camera with known focal length and pose films the
mats; the focal length, the pose and the board in mm come back from the image corners alone."""
import math

import cv2
import numpy as np

from playmat import Mat, tcg_layout
from scene3d import scene

W, H, F, SIZE = 600., 350., 1400., (1920, 1080)
K = np.float64([[F, 0, SIZE[0] / 2], [0, F, SIZE[1] / 2], [0, 0, 1]])


def camera(target, distance, tilt_deg):
    """R, t of a camera on player 0's side looking at `target` (world mm), `tilt_deg` from straight down."""
    a = math.radians(tilt_deg)
    centre = np.float64(target) + distance * np.float64([0, math.sin(a), -math.cos(a)])
    z = np.float64(target) - centre; z /= np.linalg.norm(z); x = np.float64([1, 0, 0]); y = np.cross(z, x)
    R = np.vstack([x, y, z]); return R, -R @ centre, centre


def project(points, R, t):
    pts = np.hstack([np.float64(points), np.zeros((len(points), 1))])
    return cv2.projectPoints(pts, cv2.Rodrigues(R)[0], t, K, None)[0].reshape(-1, 2)


NEAR = [[0, 0], [W, 0], [W, H], [0, H]]
FAR = [[W, -80], [0, -80], [0, -80 - H], [W, -80 - H]]  # player 1 across the table: its TL is world (W, -gap)


def main():
    checks = []
    # Tilted camera, one mat: focal length from the homography, pose to within a millimetre or so.
    R, t, centre = camera((W / 2, H / 2, 0), 800, 35)
    s = scene([Mat(0, project(NEAR, R, t))], SIZE)
    assert s['intrinsics']['source'] == 'homography' and abs(s['intrinsics']['fx'] - F) / F < .01, s['intrinsics']
    assert np.allclose(s['camera']['position_mm'], centre, atol=3), (s['camera']['position_mm'], centre)
    assert abs(s['camera']['tilt_deg'] - 35) < .3 and s['camera']['reprojection_px'] < .05, s['camera']
    assert np.allclose(s['mats'][0]['corners_mm'], NEAR, atol=.5)
    checks.append(f"35 degrees: f {s['intrinsics']['fx']:.0f} px (true {F:.0f}), camera at {np.round(s['camera']['position_mm']).tolist()} mm")
    # Every zone of the layout lands where the layout says, in mm.
    for name, x0, y0, x1, y1 in tcg_layout():
        poly = next(z['polygon_mm'] for z in s['zones'] if z['zone'] == name and z['player'] == 0)
        assert np.allclose(poly, [[x0 * W, y0 * H], [x1 * W, y0 * H], [x1 * W, y1 * H], [x0 * W, y1 * H]], atol=.5), name
    checks.append(f"{len(tcg_layout())} zones in mm on the near mat")
    # Head-on: the homography cannot tell the focal length; the assumed field of view gives a camera straight above.
    R, t, centre = camera((W / 2, H / 2, 0), 700, 0)
    s = scene([Mat(0, project(NEAR, R, t))], SIZE)
    assert s['intrinsics']['source'] == 'assumed' and s['camera']['tilt_deg'] < 1, (s['intrinsics'], s['camera'])
    p = s['camera']['position_mm']
    assert abs(p[0] - W / 2) < 2 and abs(p[1] - H / 2) < 2 and p[2] < 0, p
    assert np.allclose(s['mats'][0]['corners_mm'], NEAR, atol=1)
    checks.append(f"head-on: assumed {s['intrinsics']['hfov_deg']} degrees, camera above the mat centre at {-p[2]:.0f} mm")
    # Two facing mats: player 1's mat comes out across the table, in player 0's frame.
    R, t, centre = camera((W / 2, -40, 0), 1300, 30)
    near, far = Mat(0, project(NEAR, R, t)), Mat(1, project(FAR, R, t))
    s = scene([far, near], SIZE)
    assert s['reference_player'] == 0 and abs(s['intrinsics']['fx'] - F) / F < .01, s['intrinsics']
    got = {m['player']: m['corners_mm'] for m in s['mats']}
    assert np.allclose(got[0], NEAR, atol=.5) and np.allclose(got[1], FAR, atol=1), got
    assert sum(z['zone'].startswith('extra_monster') for z in s['zones']) == 2  # shared, listed once
    checks.append('two facing mats: the far one in the near one\'s frame to within 1 mm')
    # Printed template (mat units already mm): same camera, same answer.
    R, t, centre = camera((W / 2, H / 2, 0), 800, 35)
    to_image = K @ np.column_stack([R[:, 0], R[:, 1], t])
    layout = [(n, x0 * W, y0 * H, x1 * W, y1 * H) for n, x0, y0, x1, y1 in tcg_layout()]
    printed = Mat.from_homography(0, np.linalg.inv(to_image), layout, NEAR)
    s = scene([printed], SIZE)
    assert np.allclose(s['camera']['position_mm'], centre, atol=3) and np.allclose(s['mats'][0]['corners_mm'], NEAR, atol=.5), s['camera']
    checks.append('printed template: same pose from its mm homography')
    assert scene([], SIZE) is None and scene([printed], None) is None
    for c in checks: print('ok', c)


if __name__ == '__main__':
    main()
