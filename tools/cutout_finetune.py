"""Fine-tune BiRefNet on the reviewer's masks, so the cut-outs themselves get better (the critic
only picks among cut-outs already made: when every candidate of a card is bad, it stays bad).

Labels, all from one person judging on the iPad (review_server.py):
- corrections: reviews/sprite.jsonl verdicts with a drawn mask (data/reviews/masks, full artwork frame);
- approved cut-outs: the sprite in use (data/auto-sprites/<code>.png), put back in the artwork's frame
  by locating its crop in the art;
- TDOANE close-ups aligned to the artwork (auto_cutout.ground_truth), as in the critic's calibration.
150 corrections are held out by a hash of the code, fixed in the manifest before anything trains: the
only measure is their IoU, old model against fine-tuned, never a re-review of the same cards.

    python tools/cutout_finetune.py prepare            # manifest + full-frame masks in data/cutout-finetune/
    python tools/cutout_finetune.py baseline           # held-out IoU of the ONNX models in use
    python tools/cutout_finetune.py train --epochs 3   # needs the GPU (.venv-gpu); best epoch -> ckpt-best.pt
    python tools/cutout_finetune.py export             # ckpt-best.pt -> downloads/cutout-models/BiRefNet-ygo.onnx
    python tools/cutout_finetune.py compete [--set held|tdoane]   # test cards through build()'s critic, by competing models
    python tools/cutout_finetune.py regression          # base vs fine-tuned weights on unseen TDOANE cards (PyTorch)

Weights and model code: ZhengPeng7/BiRefNet on Hugging Face (MIT; general-use checkpoint), snapshot in
downloads/birefnet-hf. Report: research/qa/cutout-finetune.json.
"""
import argparse, hashlib, json, random, sys, time
from pathlib import Path

import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import auto_cutout as ac  # noqa: E402

DATA = ROOT / 'data/cutout-finetune'
MASKS = ROOT / 'data/reviews/masks'
SPRITES = ROOT / 'data/auto-sprites'
HF = ROOT / 'downloads/birefnet-hf'
REPORT = ROOT / 'research/qa/cutout-finetune.json'
EXPORT = ac.MODELS / 'BiRefNet-ygo.onnx'
HELD_OUT, SIZE = 150, 1024
MEAN, STD = np.float32([.485, .456, .406]), np.float32([.229, .224, .225])


def latest_verdicts():
    out = {}
    for line in (ROOT / 'reviews/sprite.jsonl').read_text(encoding='utf-8').splitlines():
        if line.strip(): v = json.loads(line); out[v['id']] = v
    return out


def sprite_mask(code):
    """The approved sprite's alpha back in the artwork frame (its crop is located exactly in the art)."""
    art = cv2.imread(str(ac.ART / f'{code}.jpg')); sp = cv2.imread(str(SPRITES / f'{code}.png'), cv2.IMREAD_UNCHANGED)
    if art is None or sp is None or sp.ndim != 3 or sp.shape[2] != 4 or sp.shape[0] > art.shape[0] or sp.shape[1] > art.shape[1]: return None
    r = cv2.matchTemplate(art, sp[..., :3], cv2.TM_SQDIFF); best, _, (x, y), _ = cv2.minMaxLoc(r)
    if best / (sp.shape[0] * sp.shape[1] * 3) > 40: return None  # not this art (or edited): skip
    mask = np.zeros(art.shape[:2], np.uint8); mask[y:y + sp.shape[0], x:x + sp.shape[1]] = sp[..., 3]
    return mask


def prepare(a):
    index = json.loads((SPRITES / 'index.json').read_text(encoding='utf-8')); verdicts = latest_verdicts()
    (DATA / 'masks').mkdir(parents=True, exist_ok=True)
    corrected = sorted(c for c, v in verdicts.items() if v.get('correction') and (MASKS / f'{c}.png').exists() and (ac.ART / f'{c}.jpg').exists())
    order = sorted(corrected, key=lambda c: hashlib.sha1(c.encode()).hexdigest())
    held = set(order[:HELD_OUT])
    rows = [{'code': c, 'source': 'correction', 'mask': str((MASKS / f'{c}.png').relative_to(ROOT)), 'held_out': c in held} for c in corrected]
    approved = sorted(c for c, v in verdicts.items() if v['verdict'] == 'approve' and index.get(c, {}).get('status') == 'ok'
                      and index[c].get('model') != 'human' and c not in held)
    kept = 0
    for c in approved:
        m = sprite_mask(c)
        if m is None: continue
        cv2.imwrite(str(DATA / 'masks' / f'{c}.png'), m); rows.append({'code': c, 'source': 'approved', 'mask': f'data/cutout-finetune/masks/{c}.png', 'held_out': False}); kept += 1
    print(f'correcciones {len(corrected)} (apartadas {len(held)}) · aprobados {kept}/{len(approved)}', flush=True)
    seen = {r['code'] for r in rows}
    codes = [p.stem for p in ac.CLOSEUP.glob('*.png') if p.stem not in seen and (ac.ART / f'{p.stem}.jpg').exists()]
    random.Random(11).shuffle(codes); got = 0
    for c in codes[:a.tdoane * 2]:
        if got >= a.tdoane: break
        _, gt = ac.ground_truth(c)
        if gt is None: continue
        cv2.imwrite(str(DATA / 'masks' / f'{c}.png'), (gt * 255).astype(np.uint8)); rows.append({'code': c, 'source': 'tdoane', 'mask': f'data/cutout-finetune/masks/{c}.png', 'held_out': False}); got += 1
    print(f'tdoane {got}', flush=True)
    (DATA / 'manifest.json').write_text(json.dumps({'held_out': HELD_OUT, 'rows': rows}, indent=0), encoding='utf-8')
    print(f'{len(rows)} pares -> {DATA / "manifest.json"}', flush=True)


def manifest():
    return json.loads((DATA / 'manifest.json').read_text(encoding='utf-8'))['rows']


def load_pair(row):
    art = cv2.imread(str(ac.ART / f'{row["code"]}.jpg')); mask = cv2.imread(str(ROOT / row['mask']), cv2.IMREAD_GRAYSCALE)
    return art, mask


def preprocess(bgr):
    """Exactly auto_cutout.Cutter.mask's input, so training, evaluation and the exported ONNX agree."""
    rgb = cv2.cvtColor(cv2.resize(bgr, (SIZE, SIZE), interpolation=cv2.INTER_LANCZOS4), cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb /= max(rgb.max(), 1e-6)
    return ((rgb - MEAN) / STD).transpose(2, 0, 1)


def postprocess(logits, shape):
    out = 1 / (1 + np.exp(-np.clip(logits, -60, 60))); out = (out - out.min()) / max(out.max() - out.min(), 1e-6)
    return cv2.resize(out, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)


def held_out_iou(predict):
    """Mean IoU over the held-out corrections; `predict(bgr)` gives a soft mask at the art's size."""
    rows = [r for r in manifest() if r['held_out']]; scores = []
    for r in rows:
        art, gt = load_pair(r); scores.append(ac.iou(predict(art), gt / 255.))
    return float(np.mean(scores)), len(rows)


def report(update):
    data = json.loads(REPORT.read_text(encoding='utf-8')) if REPORT.exists() else {}
    data.update(update); data['date'] = time.strftime('%Y-%m-%d'); REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding='utf-8')


def baseline(a):
    out = {}
    for name in ac.usable(['birefnet', 'birefnet-lite', 'isnet-anime']):
        cutter = ac.Cutter(name); score, n = held_out_iou(cutter.mask); del cutter
        out[name] = round(score, 4); print(f'{name}: IoU {score:.4f} en {n} apartadas', flush=True)
    report({'baseline': out})


def load_model(device):
    import torch
    from transformers import AutoModelForImageSegmentation
    model = AutoModelForImageSegmentation.from_pretrained(str(HF), trust_remote_code=True, torch_dtype=torch.float32)
    return model.to(device)


def preds_of(out):
    """(masks low to full resolution, gradient refs or None). In eval the model returns the masks; in
    training, [scaled, [class]] where scaled is (([gdt_pred], [gdt_label]), masks) with out_ref on."""
    if isinstance(out, list) and len(out) == 2 and isinstance(out[1], list) and (not out[1] or out[1][0] is None): out = out[0]
    if isinstance(out, tuple) and len(out) == 2 and isinstance(out[0], list) and len(out[0]) == 2: return out[1], out[0]
    return out, None


def torch_predict(model, device):
    import torch

    def predict(bgr):
        x = torch.from_numpy(preprocess(bgr))[None].to(device)
        with torch.no_grad(), torch.autocast('cuda', dtype=torch.bfloat16, enabled=device == 'cuda'):
            masks, _ = preds_of(model(x))
        return postprocess(masks[-1][0, 0].float().cpu().numpy(), bgr.shape[:2])
    return predict


def train_mode(model):
    """Batch of one (what fits next to the lab on 12 GB): BatchNorm keeps its running statistics
    (its 1x1 pooling branch cannot normalise a single sample); its scale and shift still learn."""
    import torch
    model.train()
    for m in model.modules():
        if isinstance(m, torch.nn.modules.batchnorm._BatchNorm): m.eval()


def checkpoint_blocks(model):
    """Swin blocks recompute their activations in backward, so the whole model at 1024 fits in 12 GB.
    Not the model's own use_checkpoint: BiRefNet runs the backbone twice (full and half size) and a
    block reads its grid size from attributes the second pass overwrites, so a plain recompute of the
    first pass sees the wrong size. Each call here keeps its own H, W."""
    from torch.utils.checkpoint import checkpoint
    for blk in model.modules():
        if type(blk).__name__ != 'SwinTransformerBlock': continue

        def forward(x, mask, _orig=blk.forward, _blk=blk):
            H, W = _blk.H, _blk.W

            def run(x, mask):
                _blk.H, _blk.W = H, W
                return _orig(x, mask)
            return checkpoint(run, x, mask, use_reentrant=False)
        blk.forward = forward


def augment(art, mask, rng):
    if rng.random() < .5: art, mask = cv2.flip(art, 1), cv2.flip(mask, 1)
    h, w = mask.shape; s = rng.uniform(.8, 1.)
    ch, cw = int(h * s), int(w * s); y, x = rng.randint(0, h - ch), rng.randint(0, w - cw)
    art, mask = art[y:y + ch, x:x + cw], mask[y:y + ch, x:x + cw]
    art = np.clip(art.astype(np.float32) * rng.uniform(.85, 1.15) + rng.uniform(-12, 12), 0, 255).astype(np.uint8)
    return art, mask


def train(a):
    import torch, torch.nn.functional as F
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = load_model(device)
    if a.resume and (DATA / 'ckpt-best.pt').exists():
        model.load_state_dict(torch.load(DATA / 'ckpt-best.pt', map_location=device)); print('reanuda desde ckpt-best.pt', flush=True)
    train_mode(model)
    if a.checkpointing: checkpoint_blocks(model)
    if a.freeze_backbone:
        for n, p in model.named_parameters(): p.requires_grad = not n.startswith('bb.')
    elif a.backbone_stages:  # only the last Swin stages learn: what fits next to the desktop's own GPU use
        keep = tuple(f'bb.layers.{i}.' for i in range(4 - a.backbone_stages, 4)) + ('bb.norm',)
        for n, p in model.named_parameters(): p.requires_grad = not n.startswith('bb.') or n.startswith(keep)
    print(f'parámetros entrenables {sum(p.numel() for p in model.parameters() if p.requires_grad) / 1e6:.0f} M', flush=True)
    groups = [{'params': [p for n, p in model.named_parameters() if p.requires_grad and n.startswith('bb.')], 'lr': a.lr * .2},
              {'params': [p for n, p in model.named_parameters() if p.requires_grad and not n.startswith('bb.')], 'lr': a.lr}]
    opt = torch.optim.AdamW([g for g in groups if g['params']], weight_decay=1e-4)
    rows = [r for r in manifest() if not r['held_out']]; rng = random.Random(7)
    predict = torch_predict(model, device)
    model.eval(); start, n = held_out_iou(predict); train_mode(model)
    print(f'{"reanudado" if a.resume else "base (pesos de HF)"}: IoU {start:.4f} en {n} apartadas · {len(rows)} pares de entrenamiento', flush=True)
    DATA.mkdir(exist_ok=True); old = json.loads(REPORT.read_text(encoding='utf-8')).get('train', {}).get('history', []) if a.resume and REPORT.exists() else []
    history = old or [{'epoch': 0, 'iou': round(start, 4)}]; best = start
    first = old[-1]['epoch'] + 1 if old else 1

    def loss_of(logits, target):
        logits = F.interpolate(logits, size=target.shape[-2:], mode='bilinear', align_corners=False)
        p = torch.sigmoid(logits); inter = (p * target).sum((1, 2, 3)); union = (p + target - p * target).sum((1, 2, 3))
        return F.binary_cross_entropy_with_logits(logits, target) + (1 - (inter + 1) / (union + 1)).mean()

    for epoch in range(first, first + a.epochs):
        rng.shuffle(rows); started = time.time(); total = 0.; opt.zero_grad()
        for i, r in enumerate(rows, 1):
            art, mask = load_pair(r)
            if art is None or mask is None: continue
            art, mask = augment(art, mask, rng)
            x = torch.from_numpy(preprocess(art))[None].to(device)
            y = torch.from_numpy(cv2.resize(mask, (SIZE, SIZE), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.)[None, None].to(device)
            with torch.autocast('cuda', dtype=torch.bfloat16, enabled=device == 'cuda'):
                preds, gdt = preds_of(model(x))
            loss = loss_of(preds[-1].float(), y) + .3 * sum(loss_of(p.float(), y) for p in preds[:-1]) / max(len(preds) - 1, 1)
            if gdt:  # gradient refs, as BiRefNet's own training: predicted edges against the laplacian-weighted label
                for gp, gl in zip(*gdt):
                    gp = F.interpolate(gp.float(), size=gl.shape[2:], mode='bilinear', align_corners=True)
                    loss = loss + F.binary_cross_entropy(torch.sigmoid(gp), torch.sigmoid(gl.float()))
            (loss / a.accumulate).backward(); total += float(loss.detach())
            if i % a.accumulate == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.); opt.step(); opt.zero_grad()
            if i % 100 == 0 or i == a.probe:
                rate = (time.time() - started) / i
                print(f'  época {epoch} {i}/{len(rows)} pérdida {total / i:.4f} · {rate:.2f} s/par · faltan {rate * (len(rows) - i) / 60:.0f} min'
                      f' · GPU {torch.cuda.max_memory_allocated() / 2**30:.1f} GB (reservado {torch.cuda.max_memory_reserved() / 2**30:.1f})', flush=True)
            if i == a.probe: return
        model.eval(); score, _ = held_out_iou(predict); train_mode(model)
        history.append({'epoch': epoch, 'loss': round(total / len(rows), 4), 'iou': round(score, 4), 'minutes': round((time.time() - started) / 60, 1)})
        print(f'época {epoch}: pérdida {total / len(rows):.4f} · IoU apartadas {score:.4f} (mejor {best:.4f})', flush=True)
        if score > best:
            best = score; torch.save(model.state_dict(), DATA / 'ckpt-best.pt')
        report({'train': {'pairs': len(rows), 'held_out': n, 'freeze_backbone': a.freeze_backbone, 'checkpointing': a.checkpointing, 'lr': a.lr, 'history': history, 'best_iou': round(best, 4)}})
    print(f'mejor IoU {best:.4f} (partida {start:.4f})', flush=True)


def deform_conv2d_grid(input, offset, weight, bias=None, stride=(1, 1), padding=(0, 0), dilation=(1, 1), mask=None):
    """torchvision.ops.deform_conv2d (one offset group and one weight group, as BiRefNet's) in ops
    ONNX has: bilinear sampling with grid_sample, which, like torchvision, reads zeros outside the
    input. Only for the export: torch 2.14's exporter loses the input shape the
    deform_conv2d_onnx_exporter package needs."""
    import torch
    pair = lambda v: (v, v) if isinstance(v, int) else tuple(v)
    (sh, sw), (ph, pw), (dh, dw) = pair(stride), pair(padding), pair(dilation)
    n, c, h, w = input.shape; o, _, kh, kw = weight.shape; ho, wo = offset.shape[2:]; k = kh * kw
    assert offset.shape[1] == 2 * k and weight.shape[1] == c, 'one offset group, one weight group'
    ar = lambda m, s: torch.arange(m, device=input.device, dtype=input.dtype) * s
    ky, kx = torch.meshgrid(ar(kh, dh), ar(kw, dw), indexing='ij')
    off = offset.reshape(n, k, 2, ho, wo)  # torchvision's layout: (dy, dx) per kernel tap
    y = ky.reshape(1, k, 1, 1) + (ar(ho, sh) - ph).reshape(1, 1, ho, 1) + off[:, :, 0]
    x = kx.reshape(1, k, 1, 1) + (ar(wo, sw) - pw).reshape(1, 1, 1, wo) + off[:, :, 1]
    grid = torch.stack((x * (2 / (w - 1)) - 1, y * (2 / (h - 1)) - 1), -1)  # (n, k, ho, wo, 2)
    # One kernel tap at a time: all 49 taps of the 7x7 branch at once are ~0.8 GB per copy at 256x256,
    # and the GPU is shared (12/10/2026 the run spilled into system memory and was stopped).
    taps = weight.reshape(o, c, k); out = 0
    for t in range(k):
        s = torch.nn.functional.grid_sample(input, grid[:, t], mode='bilinear', padding_mode='zeros', align_corners=True)
        if mask is not None: s = s * mask[:, t:t + 1]
        out = out + taps[:, :, t] @ s.reshape(n, c, ho * wo)
    out = out.reshape(n, o, ho, wo)
    return out + bias.reshape(1, o, 1, 1) if bias is not None else out


def export(a):
    import gc, torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cuda' and a.gpu_gb:
        # A clean out-of-memory error instead of Windows spilling the GPU into system RAM (the
        # GPU is shared with deckforge's training; 12/10/2026 the spill got runs stopped).
        torch.cuda.set_per_process_memory_fraction(min(1., a.gpu_gb * 2**30 / torch.cuda.get_device_properties(0).total_memory))
    model = load_model(device); model.load_state_dict(torch.load(DATA / 'ckpt-best.pt', map_location=device)); model.eval()
    # PyTorch's own score first (torchvision's op), so this model is gone before ONNX Runtime loads.
    torch_iou, n = held_out_iou(torch_predict(model, device))

    class Last(torch.nn.Module):
        def __init__(self, m): super().__init__(); self.m = m

        def forward(self, x):
            return preds_of(self.m(x))[0][-1]
    wrapped = Last(model).to(device).float().eval()  # export() restores the wrapper's mode on every submodule
    # torchvision's deform_conv2d (the decoder's ASPP) has no ONNX op: the model's module calls it by
    # its global name, so it is swapped for the grid_sample version while exporting.
    module = sys.modules[type(next(m for m in model.modules() if type(m).__name__ == 'DeformableConv2d')).__module__]
    original = module.deform_conv2d; module.deform_conv2d = deform_conv2d_grid
    with torch.no_grad():
        torch.onnx.export(wrapped, torch.zeros(1, 3, SIZE, SIZE, device=device), str(EXPORT), input_names=['input_image'], output_names=['output'],
                          opset_version=17, dynamo=False)
    module.deform_conv2d = original
    del wrapped, model; gc.collect(); torch.cuda.empty_cache()
    # The export must give the same masks as PyTorch, read through the production code path (Cutter).
    ac.VARIANTS['birefnet-ygo'] = (EXPORT.name, (.485, .456, .406), (.229, .224, .225), True)
    cutter = ac.Cutter('birefnet-ygo'); onnx_iou, _ = held_out_iou(cutter.mask); del cutter
    print(f'{EXPORT.name}: IoU apartadas {onnx_iou:.4f} (PyTorch {torch_iou:.4f}, {n} cartas)', flush=True)
    report({'export': {'file': EXPORT.name, 'iou_onnx': round(onnx_iou, 4), 'iou_torch': round(torch_iou, 4)}})


def tdoane_unseen(n):
    """TDOANE close-ups the fine-tune never saw (ordinary cards), aligned to their artwork."""
    seen = {r['code'] for r in manifest()}
    pool = sorted(p.stem for p in ac.CLOSEUP.glob('*.png') if p.stem not in seen and (ac.ART / f'{p.stem}.jpg').exists())
    random.Random(23).shuffle(pool); codes, arts, gts = [], [], []
    for c in pool:
        art, gt = ac.ground_truth(c)
        if gt is None or gt.mean() < .05: continue
        codes.append(c); arts.append(art); gts.append(gt.astype(np.float32))
        if len(codes) >= n: break
    return codes, arts, gts


def regression(a):
    """Base weights against fine-tuned, both in PyTorch (bf16 fits next to other GPU work, where the
    ONNX models at 1024 do not), on TDOANE cards the fine-tune never saw: did it get worse at the
    ordinary cards while learning the hard ones?"""
    import gc, torch
    if a.gpu_gb: torch.cuda.set_per_process_memory_fraction(min(1., a.gpu_gb * 2**30 / torch.cuda.get_device_properties(0).total_memory))
    codes, arts, gts = tdoane_unseen(a.n); out = {'cards': len(codes)}; ious = {}
    for name, ckpt in (('birefnet base', None), ('birefnet-ygo', DATA / 'ckpt-best.pt')):
        model = load_model('cuda')
        if ckpt: model.load_state_dict(torch.load(ckpt, map_location='cuda'))
        model.eval(); predict = torch_predict(model, 'cuda')
        ious[name] = [ac.iou(predict(x), g) for x, g in zip(arts, gts)]
        out[name] = round(float(np.mean(ious[name])), 4); print(name, out[name], flush=True)
        del model, predict; gc.collect(); torch.cuda.empty_cache()
    d = np.float32(ious['birefnet-ygo']) - np.float32(ious['birefnet base'])
    out.update(better=int((d > .02).sum()), worse=int((d < -.02).sum()), worst_drop=round(float(d.min()), 4),
               worse_codes=[codes[i] for i in np.argsort(d)[:10] if d[i] < -.02])
    print(json.dumps(out), flush=True)
    report({'regression_tdoane': out})


def compete(a):
    """What build() would make of a test set, by which models compete: the critic picks, as in
    production (first round, retries for weak cards, human bans), and the pick is scored by IoU
    against the truth. A better model the critic does not choose would gain nothing.
    Sets: 'held' = the held-out corrections (the hard cards: a person had to redraw them);
    'tdoane' = TDOANE close-ups the fine-tune never saw (ordinary cards, to catch a regression)."""
    critic = json.loads(ac.CRITIC.read_text(encoding='utf-8'))
    critic.update(mean=np.float32(critic['mean']), std=np.float32(critic['std']))
    if a.set == 'held':
        rows = [r for r in manifest() if r['held_out']]; pairs = [load_pair(r) for r in rows]
        codes = [r['code'] for r in rows]; arts = [p[0] for p in pairs]; gts = [p[1] / np.float32(255) for p in pairs]
    else:
        codes, arts, gts = tdoane_unseen(a.n)
    # Only each model's critic score and IoU are kept, not its masks: six full sets of masks at once
    # got the run stopped for low system memory (12/10/2026).
    banned = ac.rejected_models(); second = ac.masks('birefnet-lite', arts); score, iou = {}, {}

    def judge(name, masks):
        score[name] = [ac.critic_score(ac.features(x, k, s), critic) for x, k, s in zip(arts, masks, second)]
        iou[name] = [ac.iou(k, g) for k, g in zip(masks, gts)]
    main = ac.masks('birefnet', arts); judge('birefnet', main)
    judge('birefnet-flip', [(b + f) / 2 for b, f in zip(main, ac.masks('birefnet', arts, flip=True))]); del main
    for name in ac.usable(['toonout', 'isnet-anime', 'birefnet-ygo']): judge(name, ac.masks(name, arts))
    out = {'set': a.set, 'cards': len(codes), 'threshold': critic['threshold'],
           'iou_by_model': {n: round(float(np.mean(v)), 4) for n, v in iou.items()},
           'iou_oracle': round(float(np.mean([max(v[i] for v in iou.values()) for i in range(len(codes))])), 4)}

    def pick(i, first, retries):
        best = (None, float('-inf'))
        for group in (first, retries):
            if group is retries and best[1] >= critic['retry_threshold']: break  # retries only for weak cards
            for n in group:
                if n in banned.get(codes[i], ()) or n not in score: continue
                if score[n][i] > best[1]: best = (n, score[n][i])
        return best
    old_retries = ['birefnet-flip', 'isnet-anime']
    configs = (('produccion: birefnet', ['birefnet'], old_retries),
               ('+ toonout compite', ['birefnet', 'toonout'], old_retries),
               ('+ toonout + ygo compiten', ['birefnet', 'birefnet-ygo', 'toonout'], old_retries),
               ('ygo principal, reintentos viejos', ['birefnet-ygo'], old_retries),
               ('ygo principal, todos de reintento', ['birefnet-ygo'], ['birefnet', 'toonout', *old_retries]))
    for label, first, retries in configs:
        picks = [pick(i, first, retries) for i in range(len(codes))]
        ious = [iou[n][i] if n else 0. for i, (n, _) in enumerate(picks)]
        ok = [i for i, (n, s) in enumerate(picks) if n and s >= critic['threshold']]
        res = {'iou_pick': round(float(np.mean(ious)), 4), 'ok': len(ok),
               'iou_ok': round(float(np.mean([ious[i] for i in ok])), 4) if ok else None,
               'ok_good': sum(ious[i] >= .9 for i in ok), 'ok_bad': sum(ious[i] < .7 for i in ok),
               'models': {n: sum(p[0] == n for p in picks) for n in sorted({p[0] for p in picks}, key=str)}}
        out[label] = res; print(label, json.dumps(res, ensure_ascii=False), flush=True)
    print(json.dumps(out['iou_by_model']), 'oraculo', out['iou_oracle'], flush=True)
    report({f'compete_{a.set}': out})


def main():
    global SIZE
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0]); sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--tdoane', type=int, default=2000, help='TDOANE pairs to add (0: none)')
    sub.add_parser('baseline')
    p = sub.add_parser('compete'); p.add_argument('--set', choices=('held', 'tdoane'), default='held'); p.add_argument('--n', type=int, default=300)
    p = sub.add_parser('regression'); p.add_argument('--n', type=int, default=300); p.add_argument('--gpu-gb', type=float, default=0)
    p = sub.add_parser('train'); p.add_argument('--epochs', type=int, default=3); p.add_argument('--lr', type=float, default=5e-5)
    p.add_argument('--accumulate', type=int, default=4); p.add_argument('--freeze-backbone', action='store_true')
    p.add_argument('--probe', type=int, default=0, help='stop after this many pairs, having printed speed and memory')
    p.add_argument('--backbone-stages', type=int, default=0, help='train only the last N of the 4 Swin stages (0: all)')
    p.add_argument('--checkpointing', action='store_true', help='gradient checkpointing in the Swin backbone (less memory, slower)')
    p.add_argument('--resume', action='store_true', help='continue from ckpt-best.pt and its history in the report')
    for q in (p, sub.add_parser('export')): q.add_argument('--size', type=int, default=SIZE, help='model input side (the ONNX in use: 1024)')
    q.add_argument('--gpu-gb', type=float, default=0, help='cap PyTorch on the GPU (GB): fail instead of spilling into system RAM')
    a = ap.parse_args()
    if getattr(a, 'size', None): SIZE = a.size
    {'prepare': prepare, 'baseline': baseline, 'train': train, 'export': export, 'compete': compete, 'regression': regression}[a.cmd](a)


if __name__ == '__main__':
    main()
