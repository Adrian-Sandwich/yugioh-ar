"""Recalibrate the cut-out critic with human verdicts from review_server.py.

The critic in auto_cutout.py learned from TDOANE close-ups (IoU >= 0.8 = good), which exist only
for cards that already have a hand-made sprite: exactly the cards that do not need one. The
~7,000 automatic sprites are judged by a critic that never saw their kind of card.
Every candidate is fit on all verdicts, but thresholds and AUC are measured on the ones drawn at
random (review_server.py tags one in four as 'random'), since uncertainty-sampled cards bunch up
near the old threshold and would bias both. Human
verdicts (reviews/sprite.jsonl) are labels for those. Two candidates are compared on
held-out human verdicts: people only, and people plus the TDOANE pairs (so what the critic
already learned is not thrown away); the better one is offered.

    python tools/critic_human.py                 # evaluate current critic, fit a candidate
    python tools/critic_human.py --adopt         # also replace the critic if the candidate wins
    python tools/critic_human.py --source combined --human-share .7   # people weigh 70 %
    python tools/critic_human.py --requeue       # drop human-rejected cards (hand-corrected ones stay) from data/auto-sprites/index.json
    python tools/critic_human.py --requeue-all   # also every unreviewed card (after --adopt)
    (then: python tools/auto_cutout.py build  -- redoes exactly what was dropped)

Cut-outs in use and hologram candidates count; a verdict on a hologram itself judges the
fallback, not a mask. The control set never enters (its verdicts live in reviews/control/).
Masks are recomputed with the model recorded in each verdict, so this needs the GPU (.venv-gpu).
Scores in data/auto-sprites/index.json stay those of the critic that built each card until
--requeue-all redoes them.
Report: research/qa/critic-human.json. Candidate: reference/auto_cutout_critic.human.json.
The loop, one round at a time: review -> this script -> build -> review what changed.
"""
import argparse, json, shutil, sys, time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
import auto_cutout as ac  # noqa: E402
import review_server as rs  # noqa: E402

REVIEWS = ROOT / 'reviews/sprite.jsonl'
CANDIDATE = ROOT / 'reference/auto_cutout_critic.human.json'
REPORT = ROOT / 'research/qa/critic-human.json'


def verdicts():
    """Latest approve/reject per (card, sprite judged). A card re-reviewed after build() redid it
    gives two labels, one per mask: both are true, about different cut-outs."""
    last = {}
    for line in REVIEWS.read_text(encoding='utf-8').splitlines():
        if line.strip():
            v = json.loads(line); last[(v['id'], v.get('fp'))] = v
    return [v for v in last.values() if v['verdict'] in ('approve', 'reject')]


def current_verdicts(index):
    """Latest verdict per card that still applies to the sprite in use (review_server rules)."""
    last = rs.load_verdicts('sprite')
    return {c: v for c, v in last.items() if c in index and rs.same_asset(v, rs.sprite_fp(index[c]))}


CUTTERS = ac.CUTTERS


def human_features(labels):
    """Features of the exact mask each verdict judged: the model is in the verdict line. Cut-outs
    in use ('ok') and hologram candidates ('candidato') count; a hologram itself is no mask."""
    import cv2
    rows = [v for v in labels if v.get('meta', {}).get('estado') in ('ok', 'candidato')
            and v['meta'].get('modelo') in CUTTERS and (ac.ART / f"{v['id']}.jpg").exists()]
    arts = [cv2.imread(str(ac.ART / f"{v['id']}.jpg")) for v in rows]
    if not rows: return rows, np.zeros((0, len(ac.FEATURES)), np.float32), np.zeros(0, np.float32)
    main = ac.masks('birefnet', arts); second = ac.masks('birefnet-lite', arts)
    chosen = list(main)
    flip = [i for i, v in enumerate(rows) if v['meta']['modelo'] == 'birefnet-flip']
    if flip:
        for i, f in zip(flip, ac.masks('birefnet', [arts[i] for i in flip], flip=True)): chosen[i] = (main[i] + f) / 2
    for name in ('isnet-anime', 'toonout'):
        idx = [i for i, v in enumerate(rows) if v['meta']['modelo'] == name]
        if idx:
            for i, m in zip(idx, ac.masks(name, [arts[i] for i in idx])): chosen[i] = m
    X = np.float32([ac.features(a, m, s) for a, m, s in zip(arts, chosen, second)])
    y = np.float32([v['verdict'] == 'approve' for v in rows])
    return rows, X, y


def fit(X, y, l2=1e-3, iters=50, w=None):
    """L2 logistic regression by Newton steps (same model shape as auto_cutout.calibrate).
    w: optional per-sample weights (normalised to mean 1, so the regularisation stays comparable)."""
    w = np.ones(len(X)) if w is None else np.asarray(w, np.float64) / np.mean(w)
    mean, std = X.mean(0), X.std(0) + 1e-6
    Z = np.hstack([(X - mean) / std, np.ones((len(X), 1), np.float32)]).astype(np.float64)
    beta = np.zeros(Z.shape[1])
    reg = np.full(Z.shape[1], l2 * len(X)); reg[-1] = 0
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(Z @ beta, -30, 30)))
        g = Z.T @ (w * (p - y)) + reg * beta
        H = (Z * (w * p * (1 - p))[:, None]).T @ Z + np.diag(reg + 1e-9)
        step = np.linalg.solve(H, g); beta -= step
        if np.abs(step).max() < 1e-7: break
    return {'mean': mean.tolist(), 'std': std.tolist(), 'w': beta[:-1].tolist(), 'b': float(beta[-1])}


TDOANE_CACHE = ROOT / 'data/reviews/tdoane-features.npz'


def tdoane_set(n):
    """The pairs auto_cutout.calibrate learns from (BiRefNet cut-outs of cards with a TDOANE
    close-up, good = IoU >= 0.8), same selection and order, cached (regenerable, not versioned)."""
    if TDOANE_CACHE.exists():
        d = np.load(TDOANE_CACHE)
        if int(d['n']) == n and list(d['features']) == list(ac.FEATURES): return d['X'], d['y']
    import random
    codes = sorted(p.stem for p in ac.CLOSEUP.glob('*.png') if (ac.ART / f'{p.stem}.jpg').exists())
    random.Random(11).shuffle(codes)
    arts, gts = [], []
    for code in codes:
        art, gt = ac.ground_truth(code)
        if gt is None or gt.mean() < .05: continue
        arts.append(art); gts.append(gt.astype(np.float32))
        if len(arts) >= n: break
    if not arts: return np.zeros((0, len(ac.FEATURES)), np.float32), np.zeros(0, np.float32)
    main = ac.masks('birefnet', arts); second = ac.masks('birefnet-lite', arts)
    X = np.float32([ac.features(a, m, s) for a, m, s in zip(arts, main, second)])
    y = np.float32([ac.iou(m, g) >= .8 for m, g in zip(main, gts)])
    TDOANE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(TDOANE_CACHE, X=X, y=y, n=n, features=np.array(ac.FEATURES))
    return X, y


def combined_fit(X, y, Xt=None, yt=None, human_share=.5):
    """People weigh `human_share` of the total and the TDOANE pairs the rest, whatever their counts."""
    if Xt is None or not len(Xt): return fit(X, y)
    w = np.concatenate([np.full(len(X), human_share / len(X)), np.full(len(Xt), (1 - human_share) / len(Xt))])
    return fit(np.concatenate([X, Xt]), np.concatenate([y, yt]), w=w)


def held_out(X, y, Xt=None, yt=None, human_share=.5):
    """5-fold held-out scores on the human rows; TDOANE rows, if any, join every training fold."""
    folds = np.arange(len(X)) % 5; held = np.zeros(len(X))
    for k in range(5):
        tr = folds != k
        if not 0 < y[tr].sum() < tr.sum(): continue
        held[~tr] = score(X[~tr], combined_fit(X[tr], y[tr], Xt, yt, human_share))
    return held


def score(X, model):
    m = {**model, 'mean': np.float32(model['mean']), 'std': np.float32(model['std'])}
    return np.array([ac.critic_score(x, m) for x in X])


def auc(s, y):
    pos, neg = s[y == 1], s[y == 0]
    if not len(pos) or not len(neg): return None
    return float((pos[:, None] > neg[None, :]).mean() + .5 * (pos[:, None] == neg[None, :]).mean())


def band(s, y, approval):
    """Lowest score from which the next stretch of cut-outs is approved at least `approval` of
    the time (sliding window over the sorted scores). Below it, people mostly reject."""
    order = np.argsort(s); ss, ys = s[order], y[order]
    w = max(15, len(ss) // 10)
    for i in range(0, max(len(ss) - w, 0) + 1):
        if ys[i:i + w].mean() >= approval: return float(ss[i])
    return float(ss[-1])


def by_band(s, y):
    out = {}
    for lo in np.arange(0, 1, .1):
        m = (s >= lo) & (s < lo + .1 + (1e-9 if lo >= .9 else 0))
        if m.any(): out[f'{lo:.1f}'] = {'n': int(m.sum()), 'approved': round(float(y[m].mean()), 3)}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--min', type=int, default=150, help='fewest labelled cut-outs to fit a candidate')
    ap.add_argument('--adopt', action='store_true'); ap.add_argument('--requeue', action='store_true')
    ap.add_argument('--requeue-all', action='store_true')
    ap.add_argument('--source', choices=('best', 'human', 'combined'), default='best',
                    help='fit on human verdicts, on those plus the TDOANE pairs, or try both (default)')
    ap.add_argument('--tdoane', type=int, default=600, help='TDOANE pairs, as auto_cutout.py calibrate')
    ap.add_argument('--human-share', type=float, default=.5, help='share of the total weight given to people')
    ap.add_argument('--min-random', type=int, default=40, help='random-draw verdicts needed to set thresholds on them')
    a = ap.parse_args()
    current = json.loads(ac.CRITIC.read_text(encoding='utf-8'))
    index_path = ac.OUT / 'index.json'; index = json.loads(index_path.read_text(encoding='utf-8'))
    labels = verdicts()
    rows, X, y = human_features(labels)
    report = {'date': time.strftime('%Y-%m-%d'), 'labelled_cutouts': len(rows),
              'from_hologram_candidates': sum(v['meta']['estado'] == 'candidato' for v in rows),
              'approved_share': round(float(y.mean()), 3) if len(y) else None}
    adopted = False
    # Cards shown because they were uncertain bunch up near the old threshold; the ones drawn at
    # random (review_server.py tags one in four) stand for all the cards. Thresholds and AUC come
    # from those when there are enough; otherwise from everything, and the report says so.
    R = np.array([v.get('sampling') == 'random' for v in rows], bool)
    use_random = R.sum() >= a.min_random and 0 < y[R].sum() < R.sum()
    report['evaluated_on'] = (f'{int(R.sum())} veredictos al azar' if use_random else
                              f'todos ({int(R.sum())} al azar, hacen falta {a.min_random}): umbrales y AUC sesgados hacia el umbral viejo')
    E = R if use_random else np.ones(len(rows), bool)
    if len(rows) < 20:
        report['current'] = report['candidate'] = f'sólo {len(rows)} recortes con veredicto; revisa más con review_server.py'
    else:
        s_old = score(X, current)
        report['current'] = {'auc_on_humans': auc(s_old[E], y[E]), 'approval_by_score': by_band(s_old[E], y[E]),
                             'kept_but_rejected': int(((s_old >= current['threshold']) & (y == 0)).sum()),
                             'hologram_but_approved': int(((s_old < current['threshold']) & (y == 1)).sum())}
        if len(rows) >= a.min and 0 < y.sum() < len(y):
            # Candidates judged the same way (held-out human verdicts): people only, and people
            # plus the TDOANE pairs the current critic learned from. The better one is offered;
            # it replaces the current critic only if it also beats it.
            options = {}
            if a.source in ('best', 'human'): options['humanos'] = (held_out(X, y), lambda: fit(X, y))
            if a.source in ('best', 'combined'):
                Xt, yt = tdoane_set(a.tdoane)
                report['tdoane_pairs'] = len(Xt)
                if len(Xt):
                    options['humanos+tdoane'] = (held_out(X, y, Xt, yt, a.human_share),
                                                 lambda: combined_fit(X, y, Xt, yt, a.human_share))
                elif not options:
                    options['humanos'] = (held_out(X, y), lambda: fit(X, y))  # no close-ups on disk
            report['options'] = {k: {'auc_held_out': auc(h[E], y[E])} for k, (h, _) in options.items()}
            name = max(options, key=lambda k: report['options'][k]['auc_held_out'] or 0)
            held, make = options[name]
            model = make()
            cand = {**model, 'threshold': band(held[E], y[E], .3), 'retry_threshold': band(held[E], y[E], .5),
                    'features': list(ac.FEATURES), 'source': name, 'labelled': len(rows)}
            report['candidate'] = {'source': name, 'auc_held_out': auc(held[E], y[E]), 'threshold': cand['threshold'],
                                   'retry_threshold': cand['retry_threshold'], 'approval_by_score': by_band(held[E], y[E])}
            CANDIDATE.write_text(json.dumps(cand, indent=2), encoding='utf-8')
            wins = (report['candidate']['auc_held_out'] or 0) > (report['current']['auc_on_humans'] or 0)
            report['candidate']['beats_current'] = wins
            if a.adopt and wins:
                shutil.copy(ac.CRITIC, ac.CRITIC.with_name('auto_cutout_critic.prev.json'))
                ac.CRITIC.write_text(json.dumps({**cand, 'report': report['candidate']}, indent=2), encoding='utf-8')
                adopted = True
        else:
            report['candidate'] = f'hacen falta {a.min} recortes con ambos veredictos (hay {len(rows)})'
    report['adopted'] = adopted
    if a.requeue or a.requeue_all:
        # Pinned, never redone: hand corrections, promoted candidates, and cut-outs approved as
        # they are now. A hologram approved as a fallback is not pinned: a better critic may find
        # it a cut-out. --requeue redoes rejected cut-outs; --requeue-all every card not pinned
        # (the scores stored in the index come from the previous critic).
        # A newer rejection of a pinned sprite (a correction or a promotion that looked wrong later)
        # unpins it: the latest verdict on the sprite in use always wins.
        cur = current_verdicts(index)
        rejected = {c for c, v in cur.items() if v['verdict'] == 'reject'}
        pinned = {c for c, e in index.items() if e.get('model') == 'human' or e.get('promoted')}
        pinned |= {c for c, v in cur.items() if v['verdict'] == 'approve' and index[c].get('status') == 'ok'}
        pinned -= rejected
        if a.requeue_all:
            drop = set(index) - pinned
        else:
            drop = {c for c, v in cur.items() if v['verdict'] == 'reject' and v['meta'].get('estado') == 'ok'} - pinned
        for c in drop: index.pop(c, None)
        tmp = index_path.with_suffix('.tmp'); tmp.write_text(json.dumps(index), encoding='utf-8'); tmp.replace(index_path)
        report['requeued'] = len(drop)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
