"""Automatic cut-outs (monster standing figures) for cards without a TDOANE close-up.

TDOANE close-ups (downloads/tdoane-reference/YGOPRO/picture/closeup) are hand made: they
sometimes complete parts the artwork hides. They still serve as ground truth where they
match the artwork: each close-up is aligned onto its artwork (downloads/ygoprodeck-art)
with SIFT + a RANSAC similarity, its alpha is warped into the artwork frame and compared
(IoU) with the mask a segmentation model predicts from the artwork alone.

Models (rembg's ONNX exports, downloads/cutout-models, not versioned):
isnet-anime, isnet-general-use, BiRefNet-general (full) and its swin-tiny variant.

    python research/auto_cutout.py eval  [--n 60]      # IoU per model -> research/qa/auto-cutout-eval.json
    python research/auto_cutout.py sheet CODES...       # side-by-side sheet of every model's cut-out
"""
import argparse, json, random, sys, time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ART = ROOT / 'downloads/ygoprodeck-art/art'
CLOSEUP = ROOT / 'downloads/tdoane-reference/YGOPRO/picture/closeup'
MODELS = ROOT / 'downloads/cutout-models'
VARIANTS = {
    'isnet-anime': ('isnet-anime.onnx', (.5, .5, .5), (1., 1., 1.), False),
    'isnet-general': ('isnet-general-use.onnx', (.5, .5, .5), (1., 1., 1.), False),
    'birefnet-lite': ('BiRefNet-general-bb_swin_v1_tiny-epoch_232.onnx', (.485, .456, .406), (.229, .224, .225), True),
    'birefnet': ('BiRefNet-general-epoch_244.onnx', (.485, .456, .406), (.229, .224, .225), True),
}


class Cutter:
    def __init__(self, name):
        from vision_onnx import session
        file, self.mean, self.std, self.sigmoid = VARIANTS[name]
        self.name = name; self.model = session(MODELS / file)
        inp = self.model.get_inputs()[0]; self.input = inp.name; self.size = (inp.shape[3], inp.shape[2]) if isinstance(inp.shape[2], int) else (1024, 1024)

    def mask(self, bgr):
        """Soft mask 0..1 at the image's size (rembg's preprocessing)."""
        rgb = cv2.cvtColor(cv2.resize(bgr, self.size, interpolation=cv2.INTER_LANCZOS4), cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb /= max(rgb.max(), 1e-6)
        x = ((rgb - self.mean) / self.std).transpose(2, 0, 1)[None].astype(np.float32)
        out = self.model.run(None, {self.input: x})[0][0, 0]
        if self.sigmoid: out = 1 / (1 + np.exp(-out))
        out = (out - out.min()) / max(out.max() - out.min(), 1e-6)
        return cv2.resize(out, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR)


def ground_truth(code):
    """The close-up's alpha in the artwork's frame, or None when they cannot be aligned."""
    art = cv2.imread(str(ART / f'{code}.jpg')); cu = cv2.imread(str(CLOSEUP / f'{code}.png'), cv2.IMREAD_UNCHANGED)
    if art is None or cu is None or cu.ndim != 3 or cu.shape[2] != 4: return None, None
    sift = cv2.SIFT_create(3000)
    ka, da = sift.detectAndCompute(cv2.cvtColor(art, cv2.COLOR_BGR2GRAY), None)
    kc, dc = sift.detectAndCompute(cv2.cvtColor(cu[..., :3], cv2.COLOR_BGR2GRAY), (cu[..., 3] > 128).astype(np.uint8) * 255)
    if da is None or dc is None or len(kc) < 12: return art, None
    matches = [m for m, n in cv2.BFMatcher().knnMatch(dc, da, k=2) if m.distance < .75 * n.distance]
    if len(matches) < 12: return art, None
    src = np.float32([kc[m.queryIdx].pt for m in matches]); dst = np.float32([ka[m.trainIdx].pt for m in matches])
    M, inl = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4)
    if M is None or inl.sum() < 12: return art, None
    return art, cv2.warpAffine(cu[..., 3], M, (art.shape[1], art.shape[0])) / 255.


def iou(a, b):
    a, b = a > .5, b > .5; u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.


def evaluate(n):
    codes = sorted(p.stem for p in CLOSEUP.glob('*.png') if (ART / f'{p.stem}.jpg').exists())
    random.Random(7).shuffle(codes)
    pairs = []
    for code in codes:
        art, gt = ground_truth(code)
        if gt is not None and gt.mean() > .05: pairs.append((code, art, gt))
        if len(pairs) >= n: break
    print('pares alineados', len(pairs), flush=True)
    result = {'date': time.strftime('%Y-%m-%d'), 'pairs': len(pairs), 'models': {}}
    for name in VARIANTS:
        cutter = Cutter(name); cutter.mask(pairs[0][1])   # warm-up
        scores = []; started = time.perf_counter()
        for code, art, gt in pairs: scores.append(iou(cutter.mask(art), gt))
        ms = (time.perf_counter() - started) * 1000 / len(pairs)
        result['models'][name] = {'iou_mean': round(float(np.mean(scores)), 3), 'iou_median': round(float(np.median(scores)), 3),
                                  'iou_p25': round(float(np.percentile(scores, 25)), 3), 'share_iou_ge_0_8': round(float(np.mean(np.array(scores) >= .8)), 3), 'ms_per_card': round(ms, 1)}
        print(name, result['models'][name], flush=True)
        del cutter
    (ROOT / 'research/qa/auto-cutout-eval.json').write_text(json.dumps(result, indent=2), encoding='utf-8')


def sheet(path, codes):
    rows = []
    cutters = [Cutter(n) for n in VARIANTS]
    for code in codes:
        art = cv2.imread(str(ART / f'{code}.jpg')); tile = [cv2.resize(art, (256, 256))]
        for c in cutters:
            m = c.mask(art)[..., None]; checker = np.indices(art.shape[:2]).sum(0) // 24 % 2
            bg = np.where(checker[..., None], 235, 190).astype(np.uint8).repeat(3, 2)
            tile.append(cv2.resize((art * m + bg * (1 - m)).astype(np.uint8), (256, 256)))
        rows.append(np.hstack(tile))
    header = np.full((30, rows[0].shape[1], 3), 255, np.uint8)
    for i, t in enumerate(['ilustracion', *VARIANTS]): cv2.putText(header, t, (8 + 256 * i, 21), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 0, 0), 1)
    cv2.imwrite(path, np.vstack([header, *rows]), [cv2.IMWRITE_JPEG_QUALITY, 88])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); sub = parser.add_subparsers(dest='cmd', required=True)
    e = sub.add_parser('eval'); e.add_argument('--n', type=int, default=60)
    s = sub.add_parser('sheet'); s.add_argument('out'); s.add_argument('codes', nargs='+')
    a = parser.parse_args()
    evaluate(a.n) if a.cmd == 'eval' else sheet(a.out, a.codes)
