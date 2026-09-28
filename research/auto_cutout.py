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
    python research/auto_cutout.py calibrate [--n 600]  # train the critic -> research/auto_cutout_critic.json
    python research/auto_cutout.py build [--limit N]    # data/auto-sprites/<code>.png + index.json (resumable)

The viewer uses data/auto-sprites for catalog references without a TDOANE sprite
(sprite_ref 'auto:<code>.png', see vision_onnx.LiveRecognizer.load_references).
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
        import onnxruntime as ort
        file, self.mean, self.std, self.sigmoid = VARIANTS[name]
        ort.preload_dlls()
        # Measured 28/09/2026 (RTX 4070, BiRefNet at 1024): with ORT's memory pattern on, every run
        # after the first took 5-28 s (the first 0.7 s); off, 0.45 s each. Conv algorithm search
        # DEFAULT and exact-size arena growth also beat HEURISTIC (10 s) with the pattern on.
        so = ort.SessionOptions(); so.enable_mem_pattern = False; so.log_severity_level = 3
        cuda = {'cudnn_conv_algo_search': 'DEFAULT', 'arena_extend_strategy': 'kSameAsRequested'}
        self.name = name; self.model = ort.InferenceSession(str(MODELS / file), so, providers=[('CUDAExecutionProvider', cuda), 'CPUExecutionProvider'])
        inp = self.model.get_inputs()[0]; self.input = inp.name; self.size = (inp.shape[3], inp.shape[2]) if isinstance(inp.shape[2], int) else (1024, 1024)

    def mask(self, bgr):
        """Soft mask 0..1 at the image's size (rembg's preprocessing)."""
        rgb = cv2.cvtColor(cv2.resize(bgr, self.size, interpolation=cv2.INTER_LANCZOS4), cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb /= max(rgb.max(), 1e-6)
        x = ((rgb - self.mean) / self.std).transpose(2, 0, 1)[None].astype(np.float32)
        out = self.model.run(None, {self.input: x})[0][0, 0]
        if self.sigmoid: out = 1 / (1 + np.exp(-np.clip(out, -60, 60)))
        out = (out - out.min()) / max(out.max() - out.min(), 1e-6)
        return cv2.resize(out, (bgr.shape[1], bgr.shape[0]), interpolation=cv2.INTER_LINEAR)


def masks(name, images, flip=False):
    """One model at a time over a batch: two BiRefNet sessions together fill the 12 GB card and
    spill to system RAM (a 600-pair run stalled for 30 min on 28/09/2026). Freed afterwards."""
    cutter = Cutter(name)
    out = [(cv2.flip(cutter.mask(cv2.flip(im, 1)), 1) if flip else cutter.mask(im)).astype(np.float32) for im in images]
    del cutter
    return out


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


# --- critic: an adversary that tries to reject each cut-out ---------------------------------
# Features that do not need ground truth: agreement with a second, independent model, how
# unsure the mask is, how fragmented, how much of the artwork it keeps, whether it touches the
# frame, and whether its outline follows real edges of the drawing.
FEATURES = ('agree', 'fg', 'soft', 'main_part', 'parts', 'border', 'edge_ratio')
CRITIC = ROOT / 'research/auto_cutout_critic.json'


def features(art, mask, other):
    hard = mask > .5; fg = float(hard.mean())
    other_hard = other > .5; union = (hard | other_hard).sum()
    agree = float((hard & other_hard).sum() / union) if union else 0.
    soft = float(((mask > .15) & (mask < .85)).mean() / max(fg, 1e-3))
    n, _, stats, _ = cv2.connectedComponentsWithStats(hard.astype(np.uint8), 8)
    areas = sorted(stats[1:, cv2.CC_STAT_AREA], reverse=True) if n > 1 else [0]
    main_part = float(areas[0] / max(hard.sum(), 1)); parts = float(sum(a > .01 * hard.size for a in areas))
    border = float(np.concatenate([hard[0], hard[-1], hard[:, 0], hard[:, -1]]).mean())
    grey = cv2.cvtColor(art, cv2.COLOR_BGR2GRAY).astype(np.float32)
    grad = cv2.magnitude(cv2.Sobel(grey, cv2.CV_32F, 1, 0), cv2.Sobel(grey, cv2.CV_32F, 0, 1))
    outline = cv2.morphologyEx(hard.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
    edge_ratio = float(grad[outline].mean() / max(grad.mean(), 1e-3)) if outline.any() else 0.
    return [agree, fg, soft, main_part, parts, border, edge_ratio]


def critic_score(x, model):
    z = (np.float32(x) - model['mean']) / model['std']
    return float(1 / (1 + np.exp(-(z @ np.float32(model['w']) + model['b']))))


def calibrate(n, good=.8):
    """Features of BiRefNet cut-outs on cards with a TDOANE close-up, labelled by their IoU with
    it, and a logistic critic trained on them (torch, cross-validated)."""
    import torch
    codes = sorted(p.stem for p in CLOSEUP.glob('*.png') if (ART / f'{p.stem}.jpg').exists())
    random.Random(11).shuffle(codes)
    arts, gts = [], []; started = time.time()
    for code in codes:
        art, gt = ground_truth(code)
        if gt is None or gt.mean() < .05: continue
        arts.append(art); gts.append(gt.astype(np.float32))
        if len(arts) % 100 == 0: print('pares alineados', len(arts), round(time.time() - started), 's', flush=True)
        if len(arts) >= n: break
    main = masks('birefnet', arts); print('birefnet', round(time.time() - started), 's', flush=True)
    second = masks('birefnet-lite', arts); print('birefnet-lite', round(time.time() - started), 's', flush=True)
    X = np.float32([features(a, m, s) for a, m, s in zip(arts, main, second)]); ious = [iou(m, g) for m, g in zip(main, gts)]
    y = np.float32(np.array(ious) >= good)
    mean, std = X.mean(0), X.std(0) + 1e-6

    def fit(idx):
        xt = torch.tensor((X[idx] - mean) / std); yt = torch.tensor(y[idx])
        w = torch.zeros(X.shape[1], requires_grad=True); b = torch.zeros(1, requires_grad=True)
        opt = torch.optim.LBFGS([w, b], max_iter=200)
        def closure():
            opt.zero_grad(); loss = torch.nn.functional.binary_cross_entropy_with_logits(xt @ w + b, yt) + 1e-3 * (w * w).sum(); loss.backward(); return loss
        opt.step(closure)
        return {'mean': mean.tolist(), 'std': std.tolist(), 'w': w.detach().numpy().tolist(), 'b': float(b.detach())}

    def auc(scores, labels):
        pos, neg = scores[labels == 1], scores[labels == 0]
        return float((pos[:, None] > neg[None, :]).mean() + .5 * (pos[:, None] == neg[None, :]).mean()) if len(pos) and len(neg) else None
    folds = np.arange(len(X)) % 5; held = np.zeros(len(X))
    for k in range(5):
        model = fit(np.where(folds != k)[0])
        for i in np.where(folds == k)[0]: held[i] = critic_score(X[i], {**model, 'mean': np.float32(model['mean']), 'std': np.float32(model['std'])})
    model = fit(np.arange(len(X)))
    # Two operating points from the held-out scores (a 90 %-precision cut rejected 61 % of the
    # cut-outs, whose IoU was still 0.76 on average). Retry: the widest low band where most
    # cut-outs are bad (good share <= 50 %). Hologram: the widest low band whose IoU averages
    # <= 0.56, where a cut-out is worse than showing the whole artwork. (At <= 0.65 it took 29 %
    # of the cards; TDOANE close-ups repaint hidden parts, so a low IoU understates a cut-out.
    # At 0.56: 14 % hologram, of which 17 % were good; the rest IoU 0.87, 4 % below 0.5.)
    ious = np.array(ious); order = np.argsort(held); hs, ys, iu = held[order], y[order], ious[order]
    below_good = np.cumsum(ys) / np.arange(1, len(ys) + 1); below_iou = np.cumsum(iu) / np.arange(1, len(iu) + 1)
    band = lambda ok: float(hs[np.where(ok)[0].max() + 1]) if ok.any() and np.where(ok)[0].max() + 1 < len(hs) else float(hs[0])
    retry, cut = band(below_good <= .5), band(below_iou <= .56)
    def share(mask): return {'share': float(mask.mean()), 'iou_mean': float(ious[mask].mean()) if mask.any() else None, 'good_share': float(y[mask].mean()) if mask.any() else None}
    report = {'date': time.strftime('%Y-%m-%d'), 'pairs': len(X), 'good_iou': good, 'good_share': float(y.mean()),
              'features': FEATURES, 'auc_held_out': auc(held, y), 'baseline_iou_mean': float(ious.mean()),
              'retry_threshold': retry, 'hologram_threshold': cut,
              'kept_as_is': share(held >= retry), 'retried': share((held < retry) & (held >= cut)), 'hologram_band': share(held < cut),
              'samples': [[round(float(h), 4), round(float(i), 4)] for h, i in zip(held, ious)]}
    CRITIC.write_text(json.dumps({**model, 'threshold': cut, 'retry_threshold': retry, 'features': FEATURES,
                                  'report': {k: v for k, v in report.items() if k != 'samples'}}, indent=2), encoding='utf-8')
    (ROOT / 'research/qa/auto-cutout-critic.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'samples'}, indent=2))


OUT = ROOT / 'data/auto-sprites'


def targets():
    """Artwork codes of catalog cards without a TDOANE sprite, whose artwork is downloaded."""
    from collections import defaultdict
    full = json.loads((ROOT / 'data/full/catalog.json').read_text(encoding='utf-8'))
    by_card = defaultdict(list)
    for e in full: by_card[e['card_id']].append(e)
    codes = []
    for entries in by_card.values():
        if any(e.get('sprite_ref') for e in entries): continue
        codes += [Path(e['source']).stem for e in entries if (ART / f"{Path(e['source']).stem}.jpg").exists()]
    return sorted(set(codes))


def hologram(art):
    """Fallback when no cut-out convinces the critic: the whole artwork, edges faded."""
    h, w = art.shape[:2]; alpha = np.zeros((h, w), np.float32)
    m = int(min(h, w) * .06); cv2.rectangle(alpha, (m, m), (w - m, h - m), 1., -1)
    return cv2.GaussianBlur(alpha, (0, 0), m / 2) * .92


def rgba(art, mask):
    out = np.dstack([art, np.clip(mask * 255, 0, 255).astype(np.uint8)])
    ys, xs = np.nonzero(out[..., 3] > 16)
    return out[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else out


def build(limit=None):
    """Cut-outs for every target (resumable): BiRefNet, judged by the critic; when it rejects,
    the adversarial retries (flipped artwork averaged in, isnet-anime) compete and the best
    score wins; below the threshold the card gets the artwork hologram, marked doubtful."""
    model = json.loads(CRITIC.read_text(encoding='utf-8'))
    model.update(mean=np.float32(model['mean']), std=np.float32(model['std']))
    OUT.mkdir(parents=True, exist_ok=True); index_path = OUT / 'index.json'
    index = json.loads(index_path.read_text(encoding='utf-8')) if index_path.exists() else {}
    todo = [c for c in targets() if c not in index][:limit]
    print('pendientes', len(todo), 'hechas', len(index), flush=True)
    started = time.time(); chunk = 200
    for at in range(0, len(todo), chunk):
        codes = []; arts = []
        for code in todo[at:at + chunk]:
            art = cv2.imread(str(ART / f'{code}.jpg'))
            if art is None: index[code] = {'status': 'unreadable'}
            else: codes.append(code); arts.append(art)
        # One model at a time over the chunk (see masks()).
        main = masks('birefnet', arts); second = masks('birefnet-lite', arts)
        best = [('birefnet', m, critic_score(features(a, m, s), model)) for a, m, s in zip(arts, main, second)]
        weak = [i for i, b in enumerate(best) if b[2] < model['retry_threshold']]
        if weak:
            # The adversarial round: the critic rejected these; other cut-outs compete for them.
            flipped = masks('birefnet', [arts[i] for i in weak], flip=True)
            anime = masks('isnet-anime', [arts[i] for i in weak])
            for i, f, a in zip(weak, flipped, anime):
                for name, cand in (('birefnet-flip', (main[i] + f) / 2), ('isnet-anime', a)):
                    score = critic_score(features(arts[i], cand, second[i]), model)
                    if score > best[i][2]: best[i] = (name, cand, score)
        for code, art, (name, mask, score) in zip(codes, arts, best):
            status = 'ok' if score >= model['threshold'] else 'hologram'
            cv2.imwrite(str(OUT / f'{code}.png'), rgba(art, hologram(art) if status == 'hologram' else mask), [cv2.IMWRITE_PNG_COMPRESSION, 6])
            index[code] = {'status': status, 'model': name, 'score': round(score, 3)}
        tmp = index_path.with_suffix('.tmp'); tmp.write_text(json.dumps(index), encoding='utf-8'); tmp.replace(index_path)
        ok = sum(v.get('status') == 'ok' for v in index.values())
        print(f'{min(at + chunk, len(todo))}/{len(todo)} {round(time.time() - started)} s · ok {ok} de {len(index)} · reintentos {len(weak)}', flush=True)


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
    c = sub.add_parser('calibrate'); c.add_argument('--n', type=int, default=600)
    b = sub.add_parser('build'); b.add_argument('--limit', type=int)
    a = parser.parse_args()
    import onnxruntime; onnxruntime.set_default_logger_severity(3)
    if a.cmd == 'eval': evaluate(a.n)
    elif a.cmd == 'calibrate': calibrate(a.n)
    elif a.cmd == 'build': build(a.limit)
    else: sheet(a.out, a.codes)
