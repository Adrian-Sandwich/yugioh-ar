"""Camera over the table for a 3D engine (Unreal, unreal/YgoAR): intrinsics, and the camera's
rotation and position in table millimetres, from the playmat calibration. Served at /scene.

World frame (OpenCV's, right-handed): origin at the top-left corner of the reference mat (player 0's,
or the first one seen), x along its width to that player's right, y toward that player, z into the
table, so up is -z. A left-handed engine with z up (Unreal) reads (x, y, -z) unchanged.

Intrinsics: the focal length the mats' own homographies imply (Zhang 2000: a plane's two axes are
orthogonal and equally long), with the principal point at the image centre and square pixels. Seen
nearly head-on, a homography cannot tell the focal length; then an assumed field of view is used
(and it barely matters: depth hardly changes across the table). A ChArUco calibration of the camera
would replace both and add lens distortion; with the camera at an angle the mat is enough.
Pose: IPPE (Collins and Bartoli 2014) gives both poses of a plane; the one with the camera above the
table and the smaller reprojection error wins.
"""
import math

import cv2
import numpy as np

ASSUMED_HFOV = 65.          # degrees: a phone's main camera filming 16:9 video
MIN_TILT = 12.              # degrees between the optical axis and the table's normal to trust the focal length
FOCAL_RANGE = (.35, 4.)     # plausible focal lengths, in image widths (about 110 to 14 degrees of HFOV)


def mm_corners(mat):
    """The mat's own corners TL, TR, BR, BL in millimetres of its own frame."""
    w, h = (float(v) for v in mat.size_mm)
    if w == 1 and h == 1:  # printed template (playmat.Mat.from_homography): mat units are already mm
        return mat.mat_points(mat.corners).astype(np.float64)
    return np.float64([[0, 0], [w, 0], [w, h], [0, h]])


def plane_homography(mat):
    """Homography from the mat's mm plane to image pixels."""
    return cv2.getPerspectiveTransform(np.float32(mm_corners(mat)), np.float32(mat.corners)).astype(np.float64)


def focal_from_homographies(homographies, image_size):
    """Least-squares focal length (px) from plane homographies, principal point at the centre; None if
    they do not constrain it (a plane seen head-on) or it is implausible."""
    w, h = image_size; shift = np.float64([[1, 0, -w / 2], [0, 1, -h / 2], [0, 0, 1]])
    rows = []
    for H in homographies:
        H = shift @ H; H = H / np.linalg.norm(H)
        (a, b, _), (c, d, _), (e, g, _) = H
        # r1.r2 = 0 and |r1| = |r2| with K = diag(f, f, 1), unknown 1/f^2 = s: rows of A s = -B.
        rows.append((a * b + c * d, e * g)); rows.append((a * a + c * c - b * b - d * d, e * e - g * g))
    A = np.float64([r[0] for r in rows]); B = np.float64([r[1] for r in rows])
    if not A.any(): return None
    s = -float(A @ B) / float(A @ A)
    if s <= 0: return None
    f = 1 / math.sqrt(s)
    return f if FOCAL_RANGE[0] * w <= f <= FOCAL_RANGE[1] * w else None


def intrinsics(f, image_size):
    w, h = image_size
    return np.float64([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]])


def plane_pose(mat, K):
    """(R, t, reprojection px): world (this mat's mm frame) to camera, camera above the table."""
    obj = np.hstack([mm_corners(mat), np.zeros((4, 1))]); img = np.float64(mat.corners).reshape(4, 1, 2)
    n, rvecs, tvecs, errors = cv2.solvePnPGeneric(obj, img, K, None, flags=cv2.SOLVEPNP_IPPE)
    best = None
    for rvec, tvec, err in zip(rvecs, tvecs, np.ravel(errors)):
        R = cv2.Rodrigues(rvec)[0]; t = tvec.ravel()
        if (-R.T @ t)[2] >= 0: continue  # camera under the table: the mirror solution
        if best is None or err < best[2]: best = (R, t, float(err))
    return best


def unproject(points, K, R, t):
    """Image pixels -> world mm on the table plane (z = 0)."""
    centre = -R.T @ t; rays = (R.T @ np.linalg.inv(K) @ np.vstack([np.float64(points).T, np.ones(len(points))])).T
    return centre[:2] + rays[:, :2] * (-centre[2] / rays[:, 2:3])


def scene(mats, image_size):
    """The camera and the board in world mm; None without a mat or a pose."""
    if not mats or not image_size: return None
    image_size = tuple(int(v) for v in image_size)
    ref = next((m for m in mats if m.player == 0), mats[0])
    f = focal_from_homographies([plane_homography(m) for m in mats], image_size); source = 'homography'
    pose = plane_pose(ref, intrinsics(f, image_size)) if f else None
    if pose is not None:
        tilt = math.degrees(math.acos(min(1., abs(pose[0][2, 2]))))  # optical axis vs the table's normal
        if tilt < MIN_TILT: pose = None
    if pose is None:
        f = image_size[0] / 2 / math.tan(math.radians(ASSUMED_HFOV) / 2); source = 'assumed'
        pose = plane_pose(ref, intrinsics(f, image_size))
        if pose is None: return None
    K = intrinsics(f, image_size); R, t, err = pose
    # The reference mat's mm frame is the world: other mats and every zone go through the image.
    to_world = lambda pts: unproject(pts, K, R, t).round(1).tolist()
    zones = []
    for mat in mats:
        for name, x0, y0, x1, y1 in mat.layout:
            if name.startswith('extra_monster') and mat.player != 0: continue  # shared: listed once
            zones.append({'player': mat.player, 'zone': name, 'polygon_mm': to_world(mat.image_points([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]))})
    return {'image_size': list(image_size),
            'intrinsics': {'fx': round(f, 2), 'fy': round(f, 2), 'cx': image_size[0] / 2, 'cy': image_size[1] / 2,
                           'hfov_deg': round(math.degrees(2 * math.atan(image_size[0] / 2 / f)), 2), 'source': source},
            'camera': {'rotation': R.round(6).tolist(), 'translation_mm': t.round(2).tolist(), 'position_mm': (-R.T @ t).round(2).tolist(),
                       'tilt_deg': round(math.degrees(math.acos(min(1., abs(R[2, 2])))), 2), 'reprojection_px': round(err, 3)},
            'world': 'mm; origin at the reference mat top-left; x to its player right, y toward its player, z into the table (up = -z)',
            'reference_player': ref.player,
            'mats': [{'player': m.player, 'corners_mm': to_world(m.corners)} for m in mats],
            'zones': zones}
