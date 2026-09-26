"""Experiment: embedding retrieval with cropped artwork instead of full-card references.

Three retrievals on the same real photos, each with query and reference of the
same kind, so the comparison is about the reference domain, not about mixing:

1. full card query vs the current pilot index (63 full-card references, TDOANE);
2. artwork crop of the rectified card vs the same 63 illustrations as cropped art;
3. artwork crop vs every downloaded illustration of the catalog (~14k), which the
   self-hosted art makes possible for the first time.

Same encoder, same preprocessing, thresholds untouched. Output:
qa/embedding-art/comparison.json. Catalog vectors are cached in data/pilot/.

    .venv-eval/Scripts/python.exe research/embedding_art_experiment.py
"""
import hashlib, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2, numpy as np
from vision_onnx import ResearchRecognizer, ROOT
from art_verify import ART_REGION
from passcode_ocr import rectify, region

MANIFEST = ROOT / 'downloads/ygoprodeck-art/manifest.json'
CACHE = ROOT / 'data/pilot/art_index'
OUT = ROOT / 'research/qa/embedding-art'
PILOT = json.loads((ROOT / 'data/pilot/catalog.json').read_text(encoding='utf-8'))
NAMES = {e['card_id']: e['name'] for e in PILOT}
TRUTH = {
    'research/qa/corner-refinement/current.jpg': {0: 'Dragón Negro de Ojos Rojos', 1: 'Dragón Blanco de Ojos Azules', 2: 'Dragón Blanco de Ojos Azules',
        3: 'Dragón Blanco de Ojos Azules', 4: 'Dragón de Péndulo de Ojos Anómalos', 5: 'Mago Oscuro', 6: 'Número 39: Utopía',
        7: 'Dragón de Péndulo de Ojos Anómalos', 8: 'Juicio Solemne'},
    'data/captures/carta-2026-09-25T04-13-54-278Z.jpg': {0: 'Dragón Blanco de Ojos Azules'},
    'data/captures/carta-2026-09-25T04-15-11-032Z.jpg': {0: 'Dragón Blanco de Ojos Azules'},
    'data/captures/carta-2026-09-25T04-15-19-512Z.jpg': {0: 'Dragón Blanco de Ojos Azules'},
    'research/glare-benchmark/table-original.jpg': {0: 'Dragón Negro de Ojos Rojos', 1: 'Dragón Blanco de Ojos Azules', 2: 'Juicio Solemne',
        3: 'Mago Oscuro', 4: 'Número 39: Utopía', 5: 'Dragón de Péndulo de Ojos Anómalos', 6: 'Dragón de Péndulo de Ojos Anómalos'},
}
ACCEPT = lambda score, margin: score >= .80 and margin >= .07


def embed(encoder, image):
    return encoder.predict(image, classify=False)[1]


def catalog_index(encoder, manifest):
    """Vectors for every downloaded illustration, cached by manifest+model hash."""
    items = [(art_id, item) for art_id, item in manifest['items'].items() if item.get('status') == 'ok']
    key = hashlib.sha256((json.dumps(sorted(a for a, _ in items)) + hashlib.sha256(encoder.model_path.read_bytes()).hexdigest()).encode()).hexdigest()[:16]
    vectors_path = CACHE.with_name(f'art_index-{key}.npy'); meta_path = vectors_path.with_suffix('.json')
    if vectors_path.exists() and meta_path.exists():
        return np.load(vectors_path), json.loads(meta_path.read_text(encoding='utf-8'))['rows']
    vectors = []; rows = []; started = time.perf_counter()
    for i, (art_id, item) in enumerate(items):
        image = cv2.imread(str(MANIFEST.parent / item['path']))
        if image is None:
            continue
        vectors.append(embed(encoder, image)); rows.append({'artwork_id': art_id, 'card_id': item['card_id']})
        if (i + 1) % 500 == 0:
            print(f'catalog index {i + 1}/{len(items)} {(time.perf_counter() - started):.0f} s', flush=True)
    vectors = np.stack(vectors).astype(np.float32)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.save(vectors_path, vectors)
    meta_path.write_text(json.dumps({'rows': rows, 'model_sha256': hashlib.sha256(encoder.model_path.read_bytes()).hexdigest(),
        'preprocessing': 'cropped art resized 224 square; same tensor() as full cards', 'built_at': time.strftime('%Y-%m-%dT%H:%M:%S')}), encoding='utf-8')
    return vectors, rows


def ranking(vectors, rows, z):
    scores = vectors @ z; grouped = {}
    for i in np.argsort(scores)[::-1]:
        grouped.setdefault(rows[i]['card_id'], float(scores[i]))
    return list(grouped.items())


def summarize(ranked, truth_id):
    top = ranked[0]; margin = top[1] - (ranked[1][1] if len(ranked) > 1 else 0.)
    rank = next((i + 1 for i, (cid, _) in enumerate(ranked) if cid == truth_id), None)
    true_score = next((s for cid, s in ranked if cid == truth_id), None)
    return {'top1': NAMES.get(top[0], top[0]), 'top1_score': round(top[1], 3), 'margin': round(margin, 3), 'accepted': ACCEPT(top[1], margin),
            'correct': top[0] == truth_id, 'truth_rank': rank, 'truth_score': None if true_score is None else round(true_score, 3)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    model = ResearchRecognizer(); encoder = model.encoder
    by_name = {v: k for k, v in NAMES.items()}
    # 2. pilot art index: same 63 illustrations, cropped art.
    pilot_art = np.stack([embed(encoder, cv2.imread(str(MANIFEST.parent / manifest['items'][r['artwork_id']]['path']))) for r in model.rows]).astype(np.float32)
    # 3. catalog art index.
    catalog_vectors, catalog_rows = catalog_index(encoder, manifest)
    print('catalog index', catalog_vectors.shape, flush=True)
    rows = []; totals = {k: {'n': 0, 'correct': 0, 'accepted_correct': 0, 'accepted_wrong': 0, 'true_scores': [], 'margins_when_correct': []} for k in ('full_card', 'art_pilot', 'art_catalog')}
    for photo, truth in TRUTH.items():
        image = cv2.imread(str(ROOT / photo)); result = model.detect(image)
        for i, cand in enumerate(result['detections']):
            expected = truth.get(i)
            if not expected:
                continue
            truth_id = by_name[expected]
            try:
                rectified, _, native_height = rectify(image, cand['corners'])
            except ValueError as exc:
                rows.append({'photo': photo.split('/')[-1], 'cand': i, 'truth': expected, 'skipped': str(exc)}); continue
            full = summarize([(t['card_id'], t['score']) for t in cand['top5']] + [(None, 0.)] * 0, truth_id)
            # Query art at both orientations; keep the orientation with the higher top score, as detect() does.
            best_pilot = best_catalog = None
            for turns in (0, 2):
                oriented = np.ascontiguousarray(np.rot90(rectified, turns))
                z = embed(encoder, region(oriented, ART_REGION))
                p = ranking(pilot_art, model.rows, z); c = ranking(catalog_vectors, catalog_rows, z)
                if best_pilot is None or p[0][1] > best_pilot[0][1]: best_pilot = p
                if best_catalog is None or c[0][1] > best_catalog[0][1]: best_catalog = c
            row = {'photo': photo.split('/')[-1], 'cand': i, 'geometry': cand['geometry_status'], 'native_height': round(native_height), 'truth': expected,
                   'full_card': full, 'art_pilot': summarize(best_pilot, truth_id), 'art_catalog': summarize(best_catalog[:50], truth_id)}
            for key in ('full_card', 'art_pilot', 'art_catalog'):
                s = row[key]; t = totals[key]; t['n'] += 1; t['correct'] += s['correct']
                t['accepted_correct'] += s['accepted'] and s['correct']; t['accepted_wrong'] += s['accepted'] and not s['correct']
                if s['truth_score'] is not None: t['true_scores'].append(s['truth_score'])
                if s['correct']: t['margins_when_correct'].append(s['margin'])
            rows.append(row); print(json.dumps({k: row[k] for k in ('photo', 'cand', 'truth')} | {k: (row[k]['top1'][:16], row[k]['top1_score'], row[k]['margin'], row[k]['accepted'], row[k]['truth_rank']) for k in ('full_card', 'art_pilot', 'art_catalog')}, ensure_ascii=False), flush=True)
    stats = {}
    for key, t in totals.items():
        stats[key] = {'candidates': t['n'], 'top1_correct': t['correct'], 'accepted_correct': t['accepted_correct'], 'accepted_wrong': t['accepted_wrong'],
                      'true_score_mean': round(float(np.mean(t['true_scores'])), 3) if t['true_scores'] else None,
                      'true_score_min': round(float(np.min(t['true_scores'])), 3) if t['true_scores'] else None,
                      'margin_mean_when_correct': round(float(np.mean(t['margins_when_correct'])), 3) if t['margins_when_correct'] else None}
    stats['catalog_size'] = {'illustrations': int(catalog_vectors.shape[0]), 'cards': len({r['card_id'] for r in catalog_rows})}
    stats['acceptance_rule'] = 'score>=.80 and margin>=.07 (unchanged)'
    stats['limitations'] = 'Two annotated scenes (same seven cards) and three single-card captures; no unknown cards; art query window is a fixed anatomical region.'
    print('STATS', json.dumps(stats, ensure_ascii=False, indent=1))
    (OUT / 'comparison.json').write_text(json.dumps({'stats': stats, 'rows': rows}, ensure_ascii=False, indent=1), encoding='utf-8')


if __name__ == '__main__':
    main()
