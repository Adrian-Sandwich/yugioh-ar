"""Recover, for the holograms already built, the best cut-out that lost to the hologram.

build() now keeps that cut-out (data/auto-sprites/candidates/); holograms built before did not.
This redoes the same competition build() runs (BiRefNet, flipped BiRefNet, isnet-anime and
ToonOut when downloaded, judged by the current critic) only for them, and saves the winner as the candidate review_server.py shows.

    python research/hologram_candidates.py [--limit N]      # ~1,000 holograms: some 10-15 min on the 4070

Resumable: holograms that already have a candidate are skipped. Cut-outs a person rejected
for an artwork are never offered again (auto_cutout.rejected_models).
"""
import argparse, sys, time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import auto_cutout as ac  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--limit', type=int)
    a = ap.parse_args()
    import json
    model = json.loads(ac.CRITIC.read_text(encoding='utf-8'))
    model.update(mean=np.float32(model['mean']), std=np.float32(model['std']))
    index = json.loads((ac.OUT / 'index.json').read_text(encoding='utf-8'))
    cands = ac.load_candidates(); banned = ac.rejected_models()
    todo = [c for c, e in sorted(index.items()) if e.get('status') == 'hologram' and c not in cands
            and not e.get('all_rejected')][:a.limit]
    print('hologramas sin candidato', len(todo), flush=True)
    started = time.time(); chunk = 100
    for at in range(0, len(todo), chunk):
        codes, arts = [], []
        for code in todo[at:at + chunk]:
            art = cv2.imread(str(ac.ART / f'{code}.jpg'))
            if art is not None: codes.append(code); arts.append(art)
        if not arts: continue
        main = ac.masks('birefnet', arts); second = ac.masks('birefnet-lite', arts)
        flipped = ac.masks('birefnet', arts, flip=True); anime = ac.masks('isnet-anime', arts)
        toon = ac.masks('toonout', arts) if ac.usable(['toonout']) else [None] * len(arts)
        for code, art, m, s, f, an, t in zip(codes, arts, main, second, flipped, anime, toon):
            options = [(n, k) for n, k in (('birefnet', m), ('birefnet-flip', (m + f) / 2), ('isnet-anime', an), ('toonout', t))
                       if k is not None and n not in banned.get(code, ())]  # never offer again what a person rejected
            if not options: continue
            name, mask, score = max(((n, k, ac.critic_score(ac.features(art, k, s), model)) for n, k in options), key=lambda t: t[2])
            if (mask > .5).any(): ac.save_candidate(cands, code, art, name, mask, score)
        ac.write_candidates(cands)
        print(f'{min(at + chunk, len(todo))}/{len(todo)} {round(time.time() - started)} s', flush=True)


if __name__ == '__main__':
    main()
