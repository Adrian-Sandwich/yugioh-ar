"""The table plane from the cards lying on it: how far and how tilted the camera is, with nothing to
calibrate. Every card is a 59 x 86 mm rectangle; two of them in sight are enough (CardPlane). The
virtual board uses it (board_corners): its zones are laid out in real millimetres on that plane and
projected back, so they come out the size of the cards whatever the camera's angle, instead of a
trapezoid someone has to shape by eye with sliders.

The focal length is assumed (a phone's main camera): a few small quads cannot tell it, and an error
there moves the measured tilt by a degree or so.
Each card alone gives two candidate planes (IPPE, Collins and Bartoli 2014); the one most of them
agree on starts an alternation: lay every card as a true rectangle on the plane, then one PnP over
all their corners.
"""
import math

import cv2
import numpy as np

ASSUMED_HFOV = 65.          # degrees: a phone's main camera filming 16:9 video
CARD_W, CARD_H = 59., 86.   # mm


def intrinsics(f, image_size):
    w, h = image_size
    return np.float64([[f, 0, w / 2], [0, f, h / 2], [0, 0, 1]])


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
    alternation: lay every card as a true rectangle on the plane, then one PnP over all their corners."""
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


def fit_error(quads, image_size, R, t, f=None):
    """How well cards lie on a plane already known: RMS px between their corners and the nearest true
    card rectangles on it (upright or on its side, whichever fits)."""
    K = intrinsics(f or assumed_focal(image_size), image_size); rvec = cv2.Rodrigues(np.float64(R))[0]; total = []
    for quad in quads:
        quad = np.float64(quad); on_plane = unproject(quad, K, R, t); centre = on_plane.mean(axis=0); best = None
        for w, h in ((CARD_W, CARD_H), (CARD_H, CARD_W)):
            ideal = np.float64([[-w / 2, -h / 2], [w / 2, -h / 2], [w / 2, h / 2], [-w / 2, h / 2]])
            U, _, Vt = np.linalg.svd(ideal.T @ (on_plane - centre))
            laid = ideal @ (U @ np.diag([1, np.sign(np.linalg.det(U @ Vt))]) @ Vt) + centre
            seen = cv2.projectPoints(np.hstack([laid, np.zeros((4, 1))]), rvec, np.float64(t).reshape(3, 1), K, None)[0].reshape(-1, 2)
            err = float(np.mean(np.sum((seen - quad) ** 2, axis=1)))
            if best is None or err < best: best = err
        total.append(best)
    return math.sqrt(float(np.mean(total))) if total else None


class CardPlane:
    """The table plane a fixed camera sees, from the cards that have lain on it: their corners are kept
    by where they are in the image (one card per cell, the newest reading), so a pose from two cards
    can be redone once with more of them.

    A pose is held, not followed: corners are read to 4-6 px, and a pose solved again at every analysis
    moved the camera by a centimetre each time, and everything laid on the plane with it (13/11/2026).
    It changes only when it was made from few cards and many more are known now, or when the cards
    seen now stop fitting it for several analyses in a row: the camera moved, and only they count."""
    CELL = 48           # px: two readings this close are the same card
    MAX_AGE_S = 180.    # a card not seen for this long stops counting
    MIN_CARDS = 2
    # Errors are in card widths as seen (a card is 130-200 px wide on a table filmed at arm's length).
    # Live corners are loose: a sleeve's edge, a tracker's drift; five real cards fitted to 12 px (0.08).
    MAX_ERROR = .10     # beyond this the cards do not lie on one plane the way they were read
    KEEP_ERROR = .16    # the held pose stands while the cards seen now fit it this well
    MOVED_AFTER = 4     # checks in a row (one a second) the held pose must fail before it is dropped
    ENOUGH = 6          # a pose from this many cards is not redone for having more
    GOOD = ('contour_refined', 'tracked')  # corners that follow the card's outline, not the detector's box

    def __init__(self, path=None):
        """`path`: a file that keeps the pose across restarts; without the cards that made it, the
        camera would be back at whatever the board says until two cards are played again."""
        self.seen = {}; self.image_size = None; self.pose = None; self.solved_at = -1e9; self.misfits = 0; self.path = path
        try:
            import json
            saved = json.loads(path.read_text(encoding='utf-8'))
            self.image_size = tuple(saved['image_size'])
            self.pose = (np.float64(saved['rotation']), np.float64(saved['translation']), float(saved['error']), int(saved['cards']))
        except (AttributeError, OSError, KeyError, ValueError, TypeError): pass

    @staticmethod
    def width(quads):
        """Median width of the cards as seen, px: their shorter side."""
        return float(np.median([min(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[1])) for q in map(np.float64, quads)]))

    def solve(self, quads, image_size):
        """A pose from these cards, leaving out one at a time the card that fits worst while the rest
        do not agree (a hand over a corner, a card half on another): (pose, cards used) or None."""
        quads = list(quads)
        while len(quads) >= self.MIN_CARDS:
            pose = cards_pose(quads, image_size)
            if pose is None: return None
            if pose[2] <= self.MAX_ERROR * self.width(quads): return pose + (len(quads),)
            if len(quads) <= 3: return None
            worst = max(range(len(quads)), key=lambda i: fit_error([quads[i]], image_size, pose[0], pose[1]))
            quads.pop(worst)
        return None

    def keep(self, pose):
        self.pose = pose; self.misfits = 0
        if self.path is not None:
            import json
            try: self.path.write_text(json.dumps({'image_size': list(self.image_size), 'rotation': pose[0].tolist(), 'translation': pose[1].tolist(),
                                                  'error': pose[2], 'cards': pose[3]}), encoding='utf-8')
            except OSError: pass

    def see(self, detections, image_size, now):
        image_size = tuple(int(v) for v in image_size)
        if image_size != self.image_size: self.seen.clear(); self.pose = None; self.image_size = image_size  # another camera or resolution
        fresh = []
        for d in detections or ():
            quad = np.float64(d.get('corners') or [])
            if quad.shape != (4, 2) or d.get('geometry_status') not in self.GOOD: continue
            if quad.min() < 2 or (quad[:, 0].max() > image_size[0] - 3) or (quad[:, 1].max() > image_size[1] - 3): continue  # cut by the frame
            key = tuple((quad.mean(axis=0) // self.CELL).astype(int)); self.seen[key] = (quad, now); fresh.append(quad)
        self.seen = {k: v for k, v in self.seen.items() if now - v[1] <= self.MAX_AGE_S}
        if now - self.solved_at < 1. or len(self.seen) < self.MIN_CARDS: return
        self.solved_at = now
        if self.pose is not None:
            if len(fresh) < self.MIN_CARDS: return  # too little in sight to doubt it
            if fit_error(fresh, image_size, self.pose[0], self.pose[1]) <= self.KEEP_ERROR * self.width(fresh):
                self.misfits = 0
                if self.pose[3] >= self.ENOUGH or len(self.seen) < 2 * self.pose[3]: return
            else:
                self.misfits += 1
                if self.misfits < self.MOVED_AFTER: return  # a hand, a card being moved
                # The camera moved: what it saw before no longer lies on today's plane.
                moved = self.solve(fresh, image_size)
                if moved is None: return  # nothing better to offer yet: the old pose stays
                self.seen = {k: v for k, v in self.seen.items() if v[1] == now}
                return self.keep(moved)
        pose = self.solve([q for q, _ in self.seen.values()], image_size)
        if pose is not None and (self.pose is None or pose[3] > self.pose[3]): self.keep(pose)


def tilt_deg(pose):
    """Degrees between the camera's axis and the table's normal: 0 = straight down."""
    return math.degrees(math.acos(min(1., abs(pose[0][2, 2]))))


def board_corners(mode, params, image_size, pose, mat_mm=(600., 350.)):
    """[{player, corners}] of the virtual board(s) laid on the measured plane: real rectangles of
    `mat_mm` (times params['width'], 1 = life size) projected to the image, corners TL, TR, BR, BL as
    each player sees them. cx, cy: where the board's centre goes, as fractions of the image;
    rotation: degrees on the table; gap: space between the two boards, in board heights."""
    W, H = image_size; K = intrinsics(assumed_focal(image_size), image_size); R, t = pose[0], pose[1]
    centre = unproject([[params['cx'] * W, params['cy'] * H]], K, R, t)[0]
    w, h = mat_mm[0] * params['width'], mat_mm[1] * params['width']
    rows = 1. if mode == 'one' else 2. + params['gap']
    a = math.radians(params['rotation']); turn = np.float64([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    def place(points):  # board units (x 0..1 across, y 0..rows from the far edge) -> image
        on_table = (np.float64(points) - [.5, rows / 2]) * [w, h] @ turn.T + centre
        depth = (np.hstack([on_table, np.zeros((len(points), 1))]) @ np.float64(R).T + np.float64(t))[:, 2]
        if depth.min() < 30: raise ValueError('El tablero se sale por detrás de la cámara: hazlo más chico o aléjalo.')
        seen = cv2.projectPoints(np.hstack([on_table, np.zeros((len(points), 1))]), cv2.Rodrigues(np.float64(R))[0], np.float64(t).reshape(3, 1), K, None)[0]
        return seen.reshape(-1, 2).tolist()
    mats = [{'player': 0, 'corners': place([[0, rows - 1], [1, rows - 1], [1, rows], [0, rows]])}]
    if mode == 'two': mats.append({'player': 1, 'corners': place([[1, 1], [0, 1], [0, 0], [1, 0]])})
    return mats
