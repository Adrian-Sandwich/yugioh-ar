"""Correct a cut-out mask from a reviewer's strokes: green "this belongs to the monster" (the
cut-out ate the wings), red "this is background" (halo, sky, frame).

Edits stay local: only regions that touch a stroke change, so a stroke on the wings never
moves the tail. The strokes themselves always win (under green = monster, under red = not).

Two refiners, same interface (refine(art_bgr, base, strokes) -> float mask 0..1):
  grabcut  OpenCV only, CPU, always available. Good with clear colour contrast.
  sam2     Meta's SAM 2.1 (torch + git install, GPU). Understands shapes: "the wing" as a whole.
           See research/PLAN_3D_Y_REVISION.md for the install. Loaded once, image cached.

Strokes (art pixel coordinates): [{"mode": "add"|"remove", "w": width, "pts": [[x, y, pressure], ...]}]
"""
import cv2
import numpy as np


def rasterize(shape, strokes):
    """Two uint8 maps (add, remove) with every stroke drawn at its width x pen pressure."""
    add, rem = np.zeros(shape, np.uint8), np.zeros(shape, np.uint8)
    for s in strokes:
        target = add if s['mode'] == 'add' else rem
        pts = s['pts']; w = float(s['w'])
        for (x0, y0, p0), (x1, y1, p1) in zip(pts, pts[1:] or pts):
            t = max(1, int(round(w * (0.4 + 1.2 * (p0 + p1) / 2))))
            cv2.line(target, (int(round(x0)), int(round(y0))), (int(round(x1)), int(round(y1))), 255, t, cv2.LINE_AA)
    return add > 127, rem > 127


def touching(region, strokes):
    """Connected components of `region` that overlap `strokes`."""
    if not region.any() or not strokes.any(): return np.zeros_like(region)
    n, labels = cv2.connectedComponents(region.astype(np.uint8), connectivity=8)
    hit = np.unique(labels[strokes & region]); hit = hit[hit > 0]
    return np.isin(labels, hit)


def combine(base, grown, shrunk, add, rem):
    """base: bool mask; grown: candidate monster (for green); shrunk: candidate background (for red)."""
    added = touching(grown & ~base, add)
    removed = touching(shrunk & base, rem)
    out = (base | added | add) & ~removed & ~rem
    return out


def sample(mask, n, rng):
    ys, xs = np.nonzero(mask)
    if not len(xs): return np.zeros((0, 2), np.float32)
    idx = rng.choice(len(xs), min(n, len(xs)), replace=False)
    return np.float32(np.stack([xs[idx], ys[idx]], 1))


class GrabCutRefiner:
    name = 'grabcut'

    def refine(self, art, base_soft, strokes, max_side=640):
        h, w = art.shape[:2]
        base = base_soft > .5
        add, rem = rasterize((h, w), strokes)
        if not add.any() and not rem.any(): return base.astype(np.float32)
        k = min(1., max_side / max(h, w))
        small = cv2.resize(art, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA) if k < 1 else art
        rs = lambda m: cv2.resize(m.astype(np.uint8), (small.shape[1], small.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
        gc = np.where(rs(base), cv2.GC_PR_FGD, cv2.GC_PR_BGD).astype(np.uint8)
        gc[rs(add)] = cv2.GC_FGD; gc[rs(rem)] = cv2.GC_BGD
        if (gc == cv2.GC_FGD).any() or (gc == cv2.GC_PR_FGD).any():
            bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
            try:
                cv2.grabCut(small, gc, None, bgd, fgd, 5, cv2.GC_INIT_WITH_MASK)
            except cv2.error:
                pass  # degenerate colour models: fall back to the strokes alone
        fg = np.isin(gc, (cv2.GC_FGD, cv2.GC_PR_FGD)).astype(np.uint8)
        fg = cv2.resize(fg, (w, h), interpolation=cv2.INTER_NEAREST) > 0
        return combine(base, fg, ~fg, add, rem).astype(np.float32)


class Sam2Refiner:
    name = 'sam2'

    def __init__(self, model_id='facebook/sam2.1-hiera-small'):
        import torch
        from sam2.sam2_image_predictor import SAM2ImagePredictor
        self.torch = torch
        self.predictor = SAM2ImagePredictor.from_pretrained(model_id, device='cuda' if torch.cuda.is_available() else 'cpu')
        self.key = None; self.rng = np.random.default_rng(3)

    def _predict(self, pos, neg):
        pts = np.concatenate([pos, neg]); labels = np.int32([1] * len(pos) + [0] * len(neg))
        with self.torch.inference_mode():
            masks, scores, _ = self.predictor.predict(point_coords=pts, point_labels=labels, multimask_output=False)
        return masks[0] > 0

    def refine(self, art, base_soft, strokes, image_key=None):
        h, w = art.shape[:2]
        base = base_soft > .5
        add, rem = rasterize((h, w), strokes)
        if not add.any() and not rem.any(): return base.astype(np.float32)
        if image_key is None or image_key != self.key:
            with self.torch.inference_mode():
                self.predictor.set_image(cv2.cvtColor(art, cv2.COLOR_BGR2RGB))
            self.key = image_key
        core = cv2.erode(base.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        grown = shrunk = np.zeros((h, w), bool)
        if add.any():  # the missing part: green points in, red points and far background out
            far = ~cv2.dilate(base.astype(np.uint8) | add.astype(np.uint8), np.ones((41, 41), np.uint8)).astype(bool)
            grown = self._predict(sample(add, 12, self.rng), np.concatenate([sample(rem, 6, self.rng), sample(far, 4, self.rng)]))
        if rem.any():  # what to drop: red points in, green points and the core of the monster out
            shrunk = self._predict(sample(rem, 12, self.rng), np.concatenate([sample(add, 6, self.rng), sample(core, 6, self.rng)]))
        return combine(base, grown, shrunk, add, rem).astype(np.float32)


def make(kind='auto'):
    if kind in ('auto', 'sam2'):
        try:
            return Sam2Refiner()
        except Exception as e:  # not installed or no weights: say so, keep working with GrabCut
            if kind == 'sam2': raise
            print(f'SAM 2 no disponible ({type(e).__name__}: {e}); uso GrabCut', flush=True)
    return GrabCutRefiner()
