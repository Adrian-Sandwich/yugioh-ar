"""Experiment: ArtVerifier (SIFT + RANSAC against self-hosted YGOPRODeck art) over embedding top-3.

Runs the deployed verifier on every detector candidate of the real photos and
compares with a manual identity annotation of the nine-card scene. Reports how
often the true identity is verified, how often a wrong candidate is verified,
and the warm cost per candidate. One scene plus single-card captures: a
regression reference, not an accuracy benchmark.

    .venv-eval/Scripts/python.exe research/art_verification_experiment.py
"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2, numpy as np
from vision_onnx import ResearchRecognizer, ROOT
from art_verify import ArtVerifier
from passcode_ocr import rectify

PILOT = json.loads((ROOT / 'data/pilot/catalog.json').read_text(encoding='utf-8'))
NAMES = {e['card_id']: e['name'] for e in PILOT}
OUT = ROOT / 'research/qa/art-verification'
TRUTH = {
    'research/qa/corner-refinement/current.jpg': {0: 'Dragón Negro de Ojos Rojos', 1: 'Dragón Blanco de Ojos Azules', 2: 'Dragón Blanco de Ojos Azules',
        3: 'Dragón Blanco de Ojos Azules', 4: 'Dragón de Péndulo de Ojos Anómalos', 5: 'Mago Oscuro', 6: 'Número 39: Utopía',
        7: 'Dragón de Péndulo de Ojos Anómalos', 8: 'Juicio Solemne'},
    'data/captures/carta-2026-09-25T04-13-54-278Z.jpg': {0: 'Dragón Blanco de Ojos Azules'},
    'data/captures/carta-2026-09-25T04-15-11-032Z.jpg': {0: 'Dragón Blanco de Ojos Azules'},
    'data/captures/carta-2026-09-25T04-15-19-512Z.jpg': {0: 'Dragón Blanco de Ojos Azules'},
    'research/glare-benchmark/table-original.jpg': {},
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    model = ResearchRecognizer(); verifier = ArtVerifier()
    rows = []; stats = {'true_verified': 0, 'true_total': 0, 'wrong_verified': 0, 'ambiguous': 0, 'unverified_true': [], 'warm_ms': []}
    for photo, truth in TRUTH.items():
        image = cv2.imread(str(ROOT / photo)); result = model.detect(image)
        for i, cand in enumerate(result['detections']):
            try:
                rectified, _, native_height = rectify(image, cand['corners'])
            except ValueError as exc:
                rows.append({'photo': photo, 'cand': i, 'skipped': str(exc)}); continue
            proposals = [t['card_id'] for t in cand['top5'] if t.get('card_id')][:3]
            verifier.verify(rectified, proposals)  # warm reference cache
            started = time.perf_counter(); verdict = verifier.verify(rectified, proposals); ms = (time.perf_counter() - started) * 1000
            expected = truth.get(i)
            row = {'photo': photo.split('/')[-1], 'cand': i, 'geometry': cand['geometry_status'], 'native_height': round(native_height),
                   'truth': expected, 'top1': NAMES.get(proposals[0], proposals[0]), 'top1_score': round(cand['top5'][0]['score'], 3),
                   'accepted': cand['accepted'], 'art_status': verdict['status'], 'art_card': NAMES.get(verdict['card_id'], verdict['card_id']),
                   'warm_ms': round(ms), 'candidates': [{**c, 'name': NAMES.get(c['card_id'], c['card_id'])} for c in verdict['candidates']]}
            stats['warm_ms'].append(row['warm_ms'])
            if expected:
                stats['true_total'] += 1
                if verdict['status'] == 'matched':
                    if row['art_card'] == expected: stats['true_verified'] += 1
                    else: stats['wrong_verified'] += 1
                elif verdict['status'] == 'ambiguous': stats['ambiguous'] += 1
                if row['art_card'] != expected: stats['unverified_true'].append(f"{row['photo']}#{i}:{verdict['status']}")
            rows.append(row); print(json.dumps({k: v for k, v in row.items() if k != 'candidates'}, ensure_ascii=False), flush=True)
    ms = sorted(stats['warm_ms']); stats['warm_ms'] = {'min': ms[0], 'median': ms[len(ms) // 2], 'max': ms[-1]} if ms else None
    stats['rule'] = 'inliers>=30, ratio>=.6, coverage>=.15, best>=2x second'
    stats['limitations'] = 'One annotated scene plus three single-card captures; loaded PC; embedding candidates only; no unknown-card negatives beyond wrong candidates.'
    print('STATS', json.dumps(stats, ensure_ascii=False))
    (OUT / 'experiment-top3.json').write_text(json.dumps({'stats': stats, 'rows': rows}, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
