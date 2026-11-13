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
With cards on the table, the pose comes from them instead (CardPlane): each is a rectangle of known
size, measured in every frame, while a virtual board is a trapezoid someone drew over the video.
"""
import math

import cv2
import numpy as np

ASSUMED_HFOV = 65.          # degrees: a phone's main camera filming 16:9 video
MIN_TILT = 12.              # degrees between the optical axis and the table's normal to trust the focal length
FOCAL_RANGE = (.35, 4.)     # plausible focal lengths, in image widths (about 110 to 14 degrees of HFOV)
CARD_W, CARD_H = 59., 86.   # mm


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


def assumed_focal(image_size):
    return image_size[0] / 2 / math.tan(math.radians(ASSUMED_HFOV) / 2)


def _card_poses(quad, K):
    """Both IPPE poses of one card (centre at its origin, z into the table), for the reading of its
    corners as upright or as lying on its side, best first: [(error px, normal, centre, (w, h))]."""
    out = []
    for w, h in ((CARD_W, CARD_H), (CARD_H, CARD_W)):
        obj = np.float64([[-w / 2, -h / 2, 0], [w / 2, -h / 2, 0], [w / 2, h / 2, 0], [-w / 2, h / 2, 0]])
        try: _, rvecs, tvecs, errors = cv2.solvePnPGeneric(obj, np.float64(quad).reshape(4, 1, 2), K, None, flags=cv2.SOLVEPNP_IPPE)
        except cv2.error: continue
        for rvec, tvec, err in zip(rvecs, tvecs, np.ravel(errors)):
            n = cv2.Rodrigues(rvec)[0][:, 2]; t = tvec.ravel()
            if t[2] <= 0: continue
            out.append((float(err), n if n @ t > 0 else -n, t, (w, h)))
    return sorted(out, key=lambda p: p[0])


def cards_pose(quads, image_size, f=None, rounds=4):
    """The table plane from the cards lying on it: every card is a 59 x 86 mm rectangle, whichever way
    it is turned. `quads`: image corners of each card, in order around it. Returns (R, t, reprojection
    px) of a frame on the table (x along the image's right, z into the table) or None.

    Each card alone gives two candidate planes (IPPE); the one most of them agree on starts an
    alternation: lay every card as a true rectangle on the plane, then one PnP over all their corners.
    The focal length is assumed: a few small quads cannot tell it, and it changes little here."""
    quads = [np.float64(q) for q in quads if len(q) == 4]
    if not quads: return None
    K = intrinsics(f or assumed_focal(image_size), image_size); Kinv = np.linalg.inv(K)
    poses = [_card_poses(q, K) for q in quads]
    keep = [i for i, p in enumerate(poses) if p]
    if not keep: return None
    quads = [quads[i] for i in keep]; poses = [poses[i] for i in keep]
    # The plane the cards agree on: each candidate normal in turn, every card's closest reading to it.
    best = None
    for ref in (p for ps in poses for p in ps):
        picks = [min(ps, key=lambda p: (1 - p[1] @ ref[1]) * 200 + p[0]) for ps in poses]
        cost = sum((1 - p[1] @ ref[1]) * 200 + p[0] for p in picks)
        if best is None or cost < best[0]: best = (cost, picks)
    picks = best[1]
    n = np.mean([p[1] for p in picks], axis=0); n /= np.linalg.norm(n)
    origin = n * float(np.mean([n @ p[2] for p in picks]))  # the plane's point nearest the camera
    u = np.float64([1, 0, 0]) - n[0] * n; u /= np.linalg.norm(u)
    R = np.column_stack([u, np.cross(n, u), n]); t = origin
    image = np.vstack(quads); err = None
    for _ in range(rounds):
        layout = []
        for quad, (_, _, _, (w, h)) in zip(quads, picks):
            on_plane = unproject(quad, K, R, t)
            ideal = np.float64([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]])
            centre = on_plane.mean(axis=0); U, _, Vt = np.linalg.svd(ideal.T @ (on_plane - centre))  # Kabsch, 2D
            turn = (U @ np.diag([1, np.sign(np.linalg.det(U @ Vt))]) @ Vt).T
            layout.append(ideal @ turn.T + centre)
        layout = np.hstack([np.vstack(layout), np.zeros((len(image), 1))])
        ok, rvec, tvec = cv2.solvePnP(layout, image.reshape(-1, 1, 2), K, None, cv2.Rodrigues(R)[0], t.reshape(3, 1).copy(),
                                      useExtrinsicGuess=True, flags=cv2.SOLVEPNP_ITERATIVE)
        if not ok: return None
        R = cv2.Rodrigues(rvec)[0]; t = tvec.ravel()
        if (-R.T @ t)[2] >= 0: return None  # camera under the table
        seen = cv2.projectPoints(layout, rvec, tvec, K, None)[0].reshape(-1, 2)
        err = float(np.sqrt(np.mean(np.sum((seen - image) ** 2, axis=1))))
    return R, t, err


class CardPlane:
    """The table plane a fixed camera sees, from the cards that have lain on it: their corners are kept
    by where they are in the image (one card per cell, the newest reading), so a pose from two cards
    grows steadier as cards are played in other places. A camera that moved shows as a pose its newest
    cards no longer fit: then only they count."""
    CELL = 48           # px: two readings this close are the same card
    MAX_AGE_S = 180.    # a card not seen for this long stops counting
    MIN_CARDS = 2
    MAX_ERROR = 6.      # px: beyond this the cards do not lie on one plane the way they were read
    GOOD = ('contour_refined', 'tracked')  # corners that follow the card's outline, not the detector's box

    def __init__(self):
        self.seen = {}; self.image_size = None; self.pose = None; self.solved_at = -1e9

    def see(self, detections, image_size, now):
        image_size = tuple(int(v) for v in image_size)
        if image_size != self.image_size: self.seen.clear(); self.pose = None; self.image_size = image_size
        fresh = []
        for d in detections or ():
            quad = np.float64(d.get('corners') or [])
            if quad.shape != (4, 2) or d.get('geometry_status') not in self.GOOD: continue
            if quad.min() < 2 or (quad[:, 0].max() > image_size[0] - 3) or (quad[:, 1].max() > image_size[1] - 3): continue  # cut by the frame
            key = tuple((quad.mean(axis=0) // self.CELL).astype(int)); self.seen[key] = (quad, now); fresh.append(quad)
        self.seen = {k: v for k, v in self.seen.items() if now - v[1] <= self.MAX_AGE_S}
        if now - self.solved_at < 1. or len(self.seen) < self.MIN_CARDS: return
        self.solved_at = now
        pose = cards_pose([q for q, _ in self.seen.values()], image_size)
        if (pose is None or pose[2] > self.MAX_ERROR) and len(fresh) >= self.MIN_CARDS:
            # The camera moved: what it saw before no longer lies on today's plane.
            self.seen = {k: v for k, v in self.seen.items() if v[1] == now}
            pose = cards_pose(fresh, image_size)
        if pose is not None and pose[2] <= self.MAX_ERROR: self.pose = pose + (len(self.seen),)


def scene(mats, image_size, cards=None):
    """The camera and the board in world mm; None without a mat or a pose. `cards`: a CardPlane; its
    pose, when it has one, is what the camera really sees and replaces the mat's own (a virtual board
    is drawn by hand; the cards are measured). The mat still says where the origin and the zones are."""
    if not mats or not image_size: return None
    image_size = tuple(int(v) for v in image_size)
    ref = next((m for m in mats if m.player == 0), mats[0])
    plane = cards.pose if cards is not None and cards.image_size == image_size else None
    if plane is not None:
        f = assumed_focal(image_size); source = 'assumed'; K = intrinsics(f, image_size); Rp, tp, err, count = plane
        # World = the plane's frame turned and moved so the reference mat's top edge is its x axis.
        a, b = unproject(ref.corners[:2], K, Rp, tp); x = (b - a) / np.linalg.norm(b - a)
        turn = np.float64([[x[0], -x[1], 0], [x[1], x[0], 0], [0, 0, 1]])
        pose = (Rp @ turn, Rp @ np.float64([a[0], a[1], 0]) + tp, err)
    else:
        f = focal_from_homographies([plane_homography(m) for m in mats], image_size); source = 'homography'
        pose = plane_pose(ref, intrinsics(f, image_size)) if f else None
        if pose is not None:
            tilt = math.degrees(math.acos(min(1., abs(pose[0][2, 2]))))  # optical axis vs the table's normal
            if tilt < MIN_TILT: pose = None
        if pose is None:
            f = assumed_focal(image_size); source = 'assumed'
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
                       'tilt_deg': round(math.degrees(math.acos(min(1., abs(R[2, 2])))), 2), 'reprojection_px': round(err, 3),
                       'source': 'cards' if plane is not None else 'mat', 'cards': plane[3] if plane is not None else 0},
            'world': 'mm; origin at the reference mat top-left; x to its player right, y toward its player, z into the table (up = -z)',
            'reference_player': ref.player,
            'mats': [{'player': m.player, 'corners_mm': to_world(m.corners)} for m in mats],
            'zones': zones}
