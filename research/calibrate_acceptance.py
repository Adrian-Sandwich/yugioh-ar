"""Calibrate the embedding acceptance rule (similarity, margin) with TCGplayer scans.

The rule in vision_onnx.ResearchRecognizer.detect (similarity >= .80 and margin
>= .07) was set on two photos and never faced negatives. This script feeds whole
TCGplayer scans (flat, frontal photos of one printing) to the same encoder and
the same pilot index, exactly as production does with a rectified crop: resize
to 224x224 (the tensor() preprocessing), query at 0 and 180 degrees, keep the
orientation with the higher top score, margin = top-1 minus the best DIFFERENT
card_id.

Groups (only scans with status ok, width >= --min-width and exactly one
reconstructed card_id):

* POSITIVES: scans whose canonical card_id is one of the pilot identities;
  run in full when there are fewer than --max-positives, else sampled.
* NEGATIVES: a seeded sample of scans whose identity is NOT in the pilot,
  stratified by rarity (round robin over rarity strata so foils are present),
  sized from a measured per-scan time so the whole run fits --budget-minutes.

Then a grid of rules (similarity 0.40..0.90 step 0.02, margin 0.00..0.40 step
0.02) is evaluated: false-accept rate on negatives and recall (accepted AND
correct) on positives, plus by-rarity breakdowns for the current rule and for
the best rules under false-accept <= 1%, <= 0.5% and 0. The same rules are
also evaluated on the annotated real photo crops of
research/embedding_art_experiment.py (full-card retrieval as production does).

Caveat printed in the outputs: scans are flat, evenly lit photos, a domain
closer to the pilot references than a table photo. Both the negative rate and
the positive recall are optimistic for real tables.

Outputs: research/qa/calibration/acceptance.json and acceptance.md.

    .venv-eval/Scripts/python.exe -X utf8 research/calibrate_acceptance.py --budget-minutes 35
"""
import argparse, hashlib, json, random, struct, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2, numpy as np
from vision_onnx import ResearchRecognizer, ROOT
from identity_resolution import canonical

BASE = ROOT / 'downloads/tcgplayer-sample'
OUT = ROOT / 'research/qa/calibration'
CURRENT = (.80, .07)
SIM_GRID = [round(x, 2) for x in np.arange(.40, .90 + 1e-9, .02)]
MARGIN_GRID = [round(x, 2) for x in np.arange(.00, .40 + 1e-9, .02)]
FA_TARGETS = ((.01, 'fa_le_1pct'), (.005, 'fa_le_0_5pct'), (.0, 'fa_zero'))


def jpeg_size(path):
    """(width, height) from the JPEG SOF marker without decoding the image."""
    with open(path, 'rb') as f:
        data = f.read(65536)
    i = 2
    while i < len(data) - 9:
        if data[i] != 0xFF:
            i += 1; continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack('>HH', data[i + 5:i + 9]); return w, h
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2; continue
        i += 2 + struct.unpack('>H', data[i + 2:i + 4])[0]
    return None


def rarity_of(rec, item):
    return rec.get('rarity') or item.get('rarity') or 'unknown'


def select(min_width, pilot_ids):
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))['items']
    reconstructed = json.loads((BASE / 'reconstructed.json').read_text(encoding='utf-8'))['items']
    counts = {'manifest_items': len(manifest), 'status_ok': 0, 'one_card_id': 0, 'width_ok': 0}
    positives, negatives = [], []
    for key in sorted(manifest):
        item = manifest[key]
        if item.get('status') != 'ok':
            continue
        counts['status_ok'] += 1
        ids = (reconstructed.get(key) or {}).get('card_ids') or []
        if len(ids) != 1:
            continue
        counts['one_card_id'] += 1
        size = jpeg_size(BASE / item['path'])
        if not size or size[0] < min_width:
            continue
        counts['width_ok'] += 1
        rec = reconstructed[key]
        entry = {'product_id': int(key), 'path': item['path'], 'card_id': canonical(ids[0]), 'rarity': rarity_of(rec, item),
                 'width': size[0], 'height': size[1], 'number': rec.get('number'), 'name': rec.get('card_name') or item.get('name')}
        (positives if entry['card_id'] in pilot_ids else negatives).append(entry)
    return positives, negatives, counts


def stratified(entries, n, seed):
    """Round robin over rarity strata (seeded shuffle inside each) until n entries."""
    strata = {}
    for e in entries:
        strata.setdefault(e['rarity'], []).append(e)
    rng = random.Random(seed)
    for keys in strata.values():
        rng.shuffle(keys)
    chosen = []; names = sorted(strata)
    while len(chosen) < n and any(strata[k] for k in names):
        for k in names:
            if strata[k] and len(chosen) < n:
                chosen.append(strata[k].pop())
    return chosen


def query(model, image):
    """Production retrieval on a rectified 224x224 card: two orientations, best top score."""
    rectified = cv2.resize(image, (224, 224))  # same call as vision_onnx.tensor
    options = []
    for rotation in (0, 2):
        _, z = model.encoder.predict(np.ascontiguousarray(np.rot90(rectified, rotation)), classify=False)
        scores = model.vectors @ z; grouped = {}
        for i in np.argsort(scores)[::-1]:
            grouped.setdefault(canonical(model.rows[i]['card_id']), float(scores[i]))
        ranked = list(grouped.items())
        options.append((ranked[0][1], rotation, ranked))
    top, rotation, ranked = max(options, key=lambda o: o[0])
    margin = ranked[0][1] - (ranked[1][1] if len(ranked) > 1 else 0.)
    return {'top1': ranked[0][0], 'similarity': round(top, 4), 'margin': round(margin, 4), 'rotation': rotation * 90,
            'ranked': [(cid, round(s, 4)) for cid, s in ranked]}


def run_group(model, entries, group, log_every=100):
    rows = []; started = time.perf_counter()
    for i, e in enumerate(entries):
        image = cv2.imread(str(BASE / e['path']))
        if image is None:
            rows.append({**e, 'group': group, 'error': 'unreadable image'}); continue
        q = query(model, image)
        rank = next((k + 1 for k, (cid, _) in enumerate(q['ranked']) if cid == e['card_id']), None)
        rows.append({**e, 'group': group, 'top1': q['top1'], 'similarity': q['similarity'], 'margin': q['margin'], 'rotation': q['rotation'],
                     'correct': q['top1'] == e['card_id'], 'truth_rank': rank, 'truth_score': next((s for cid, s in q['ranked'] if cid == e['card_id']), None)})
        if (i + 1) % log_every == 0:
            print(f'{group} {i + 1}/{len(entries)} {(time.perf_counter() - started) / 60:.1f} min', flush=True)
    return rows, time.perf_counter() - started


def evaluate(positives, negatives):
    """Grid of rules. positives: rows with similarity, margin, correct; negatives: similarity, margin."""
    ps = np.array([r['similarity'] for r in positives]); pm = np.array([r['margin'] for r in positives]); pc = np.array([r['correct'] for r in positives])
    ns = np.array([r['similarity'] for r in negatives]); nm = np.array([r['margin'] for r in negatives])
    fa = np.zeros((len(SIM_GRID), len(MARGIN_GRID))); rc = np.zeros_like(fa); fa_n = np.zeros_like(fa, dtype=int); rc_n = np.zeros_like(fa_n)
    for a, t in enumerate(SIM_GRID):
        for b, m in enumerate(MARGIN_GRID):
            fa_n[a, b] = int(((ns >= t) & (nm >= m)).sum()) if len(ns) else 0
            rc_n[a, b] = int(((ps >= t) & (pm >= m) & pc).sum()) if len(ps) else 0
    fa = fa_n / max(len(ns), 1); rc = rc_n / max(len(ps), 1)
    return fa, rc, fa_n, rc_n


def rule_stats(rows, t, m, group_key='rarity'):
    """Accepted/correct counts overall and per group for one rule."""
    def block(subset):
        n = len(subset); acc = [r for r in subset if r['similarity'] >= t and r['margin'] >= m]
        out = {'n': n, 'accepted': len(acc)}
        if subset and 'correct' in subset[0]:
            out['top1_correct'] = sum(r['correct'] for r in subset); out['accepted_correct'] = sum(r['correct'] for r in acc)
            out['accepted_wrong'] = len(acc) - out['accepted_correct']
        return out
    groups = {}
    for r in rows:
        groups.setdefault(r[group_key], []).append(r)
    return {'all': block(rows), 'by_' + group_key: {k: block(v) for k, v in sorted(groups.items())}}


def best_rule(fa, rc, limit):
    best = None
    for a, t in enumerate(SIM_GRID):
        for b, m in enumerate(MARGIN_GRID):
            if fa[a, b] <= limit + 1e-12:
                key = (rc[a, b], -fa[a, b], t, m)
                if best is None or key > best[0]:
                    best = (key, t, m)
    return None if best is None else {'similarity': best[1], 'margin': best[2]}


def photos(model):
    """Annotated real photo crops of embedding_art_experiment.py, full-card retrieval as production."""
    try:
        sys.path.insert(0, str(ROOT / 'research'))
        import embedding_art_experiment as art
    except Exception as exc:
        return {'available': False, 'reason': f'embedding_art_experiment import failed: {exc}', 'rows': []}
    from passcode_ocr import rectify
    by_name = {v: k for k, v in art.NAMES.items()}
    rows = []; missing = []
    for photo, truth in art.TRUTH.items():
        image = cv2.imread(str(ROOT / photo))
        if image is None:
            missing.append(photo); continue
        result = model.detect(image)
        for i, cand in enumerate(result['detections']):
            expected = truth.get(i)
            if not expected:
                continue
            truth_id = canonical(by_name[expected])
            try:
                rectify(image, cand['corners'])
            except ValueError as exc:
                rows.append({'photo': photo.split('/')[-1], 'cand': i, 'truth': expected, 'skipped': str(exc)}); continue
            rows.append({'photo': photo.split('/')[-1], 'cand': i, 'truth': expected, 'top1': canonical(cand['card_id']), 'top1_name': art.NAMES.get(cand['card_id'], cand['card_id']),
                         'similarity': round(cand['score'], 4), 'margin': round(cand['margin'], 4), 'correct': canonical(cand['card_id']) == truth_id,
                         'rarity': 'photo', 'geometry': cand['geometry_status']})
    return {'available': True, 'photos': len(art.TRUTH), 'missing_photos': missing, 'annotated_candidates': sum(len(v) for v in art.TRUTH.values()),
            'rows': rows, 'note': 'Same photos and truth as embedding_art_experiment.py; candidates that fail rectify() are listed as skipped, like there. Unlike scans, these are camera photos of a table.'}


def markdown(report):
    L = []; a = L.append
    a('# Calibración de la regla de aceptación (embeddings) — escaneos TCGplayer\n')
    a(f"Fecha: {report['date']}. Semilla {report['seed']}. Modelo sha256 `{report['model_sha256'][:16]}…`. Índice piloto: {report['index']['rows']} referencias, {report['index']['identities']} identidades.\n")
    s = report['selection']
    a(f"Escaneos: {s['counts']['manifest_items']} productos, {s['counts']['status_ok']} con imagen, {s['counts']['one_card_id']} con una sola identidad, {s['counts']['width_ok']} con ancho ≥ {s['min_width']} px. "
      f"Positivos disponibles {s['positives_available']}, evaluados {s['positives_run']}; negativos disponibles {s['negatives_available']}, evaluados {s['negatives_run']} (muestra estratificada por rareza).\n")
    t = report['timing']
    a(f"Tiempo: {t['per_scan_s_measured']:.2f} s por escaneo (dos orientaciones, medido sobre {t['measured_on']} escaneos), positivos {t['positives_min']:.1f} min, negativos {t['negatives_min']:.1f} min, fotos {t['photos_s']:.0f} s, total {t['total_min']:.1f} min.\n")
    a('**Aviso:** los escaneos son fotos planas y uniformes, un dominio más cercano a las referencias del piloto que una foto de mesa. La tasa de falsas aceptaciones y el recall son optimistas para mesas reales.\n')
    a('## Reglas\n')
    a('| Regla | similitud ≥ | margen ≥ | Falsas aceptaciones (negativos) | Recall (positivos aceptados y correctos) | Positivos aceptados erróneos |')
    a('|---|---|---|---|---|---|')
    for name, r in report['rules'].items():
        if r is None:
            a(f'| {name} | — | — | ninguna regla de la rejilla cumple | — | — |'); continue
        st = r['scans']
        a(f"| {name} | {r['similarity']:.2f} | {r['margin']:.2f} | {st['negatives']['all']['accepted']}/{st['negatives']['all']['n']} ({r['false_accept_rate'] * 100:.2f}%) | "
          f"{st['positives']['all']['accepted_correct']}/{st['positives']['all']['n']} ({r['recall'] * 100:.1f}%) | {st['positives']['all']['accepted_wrong']} |")
    p = report['positives']
    a(f"\nTop-1 correcto en positivos sin regla: {p['top1_correct']}/{p['n']}. Similitud de la identidad correcta: mediana {p['truth_score_median']}, mín. {p['truth_score_min']}. "
      f"Negativos: similitud top-1 mediana {report['negatives']['similarity_median']}, p95 {report['negatives']['similarity_p95']}, máx. {report['negatives']['similarity_max']}; margen mediana {report['negatives']['margin_median']}, p95 {report['negatives']['margin_p95']}.\n")
    a('## Recall por rareza (positivos: aceptados correctos / n)\n')
    names = list(report['rules']); rarities = sorted(report['positives']['by_rarity'])
    a('| Rareza | n | top-1 correcto | ' + ' | '.join(names) + ' |')
    a('|---|---|---|' + '---|' * len(names))
    for rar in rarities:
        cells = []
        for name in names:
            r = report['rules'][name]
            b = r['scans']['positives']['by_rarity'].get(rar) if r else None
            cells.append('—' if not b else f"{b['accepted_correct']}/{b['n']}")
        base = report['positives']['by_rarity'][rar]
        a(f"| {rar} | {base['n']} | {base['top1_correct']} | " + ' | '.join(cells) + ' |')
    a('\n## Falsas aceptaciones por rareza (negativos: aceptados / n)\n')
    rarities = sorted(report['negatives']['by_rarity'])
    a('| Rareza | n | ' + ' | '.join(names) + ' |')
    a('|---|---|' + '---|' * len(names))
    for rar in rarities:
        cells = []
        for name in names:
            r = report['rules'][name]
            b = r['scans']['negatives']['by_rarity'].get(rar) if r else None
            cells.append('—' if not b else f"{b['accepted']}/{b['n']}")
        a(f"| {rar} | {report['negatives']['by_rarity'][rar]['n']} | " + ' | '.join(cells) + ' |')
    ph = report['photos']
    a('\n## Fotos reales anotadas (embedding_art_experiment.py)\n')
    if not ph.get('available'):
        a(f"No disponibles: {ph.get('reason')}\n")
    else:
        usable = [r for r in ph['rows'] if 'skipped' not in r]
        a(f"{len(usable)} candidatas con verdad y rectificables de {ph['annotated_candidates']} anotadas en {ph['photos']} fotos ({len(ph['rows']) - len(usable)} omitidas por geometría; fotos ausentes: {ph['missing_photos'] or 'ninguna'}). Top-1 correcto {sum(r['correct'] for r in usable)}/{len(usable)}.\n")
        a('| Regla | Aceptadas correctas | Aceptadas erróneas |'); a('|---|---|---|')
        for name, r in report['rules'].items():
            if r is None: continue
            b = r['photos']['all']
            a(f"| {name} ({r['similarity']:.2f}/{r['margin']:.2f}) | {b['accepted_correct']}/{b['n']} | {b['accepted_wrong']} |")
        a('\n| Foto | cand. | verdad | top-1 | similitud | margen |'); a('|---|---|---|---|---|---|')
        for r in usable:
            a(f"| {r['photo']} | {r['cand']} | {r['truth']} | {r['top1_name']}{'' if r['correct'] else ' (ERROR)'} | {r['similarity']:.3f} | {r['margin']:.3f} |")
    a('\n## Rejilla (falsas aceptaciones % / recall %) — filas similitud, columnas margen\n')
    cols = [m for m in MARGIN_GRID if round(m * 100) % 10 == 0]
    a('| sim \\ margen | ' + ' | '.join(f'{m:.2f}' for m in cols) + ' |'); a('|---|' + '---|' * len(cols))
    g = report['grid']
    for a_, t in enumerate(SIM_GRID):
        if round(t * 100) % 10 not in (0, 4, 6, 8, 2) or round(t * 100) % 4: continue
        cells = [f"{g['false_accept_rate'][a_][MARGIN_GRID.index(m)] * 100:.2f} / {g['recall'][a_][MARGIN_GRID.index(m)] * 100:.1f}" for m in cols]
        a(f'| {t:.2f} | ' + ' | '.join(cells) + ' |')
    a('\nRejilla completa en `acceptance.json` (`grid`).')
    return '\n'.join(L) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--budget-minutes', type=float, default=35., help='wall-clock budget for encoding scans (positives + negatives)')
    parser.add_argument('--min-width', type=int, default=400)
    parser.add_argument('--max-positives', type=int, default=1500)
    parser.add_argument('--max-negatives', type=int, default=6000)
    parser.add_argument('--seed', type=int, default=20260926)
    parser.add_argument('--measure', type=int, default=20, help='scans used to measure the per-scan time before sizing the negative sample')
    parser.add_argument('--from-records', action='store_true', help='re-evaluate the rules from acceptance-records.json without encoding again')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    model = ResearchRecognizer('embedding')
    model_sha = hashlib.sha256(model.encoder.model_path.read_bytes()).hexdigest()
    raw_ids = {r['card_id'] for r in model.rows}; pilot_ids = {canonical(c) for c in raw_ids}
    records_path = OUT / 'acceptance-records.json'
    if args.from_records and records_path.exists():
        saved = json.loads(records_path.read_text(encoding='utf-8'))
        positives_all, negatives_all, counts = saved['positives_all'], saved['negatives_all'], saved['counts']
        positive_rows, negative_rows, photo_report = saved['positive_rows'], saved['negative_rows'], saved['photo_report']
        measure = positive_rows[:args.measure]; per_scan = saved['timing']['per_scan_s_measured']
        positives_s, negatives_s, photos_s = saved['timing']['positives_s'], saved['timing']['negatives_s'], saved['timing']['photos_s']
        print(f'records reloaded: {len(positive_rows)} positives, {len(negative_rows)} negatives', flush=True)
    else:
        positives_all, negatives_all, counts = select(args.min_width, pilot_ids)
        print(f'selection: {counts} positives {len(positives_all)} negatives {len(negatives_all)}', flush=True)
        positives = positives_all if len(positives_all) <= args.max_positives else stratified(positives_all, args.max_positives, args.seed)
        # Measure the per-scan cost on the first scans of the positive set (they are re-used, not re-run).
        measure = positives[:args.measure]
        measured_rows, measured_s = run_group(model, measure, 'positive', log_every=10 ** 9)
        per_scan = measured_s / max(len(measure), 1)
        rest_rows, rest_s = run_group(model, positives[args.measure:], 'positive')
        positive_rows = measured_rows + rest_rows; positives_s = measured_s + rest_s
        remaining = args.budget_minutes * 60 - positives_s
        n_neg = int(min(args.max_negatives, len(negatives_all), max(0, remaining / per_scan)))
        print(f'per-scan {per_scan:.2f} s; positives took {positives_s / 60:.1f} min; negatives sized to {n_neg}', flush=True)
        negatives = stratified(negatives_all, n_neg, args.seed)
        negative_rows, negatives_s = run_group(model, negatives, 'negative')
        photo_started = time.perf_counter(); photo_report = photos(model); photos_s = time.perf_counter() - photo_started
        # Encoding is the expensive part: keep it before any evaluation can fail.
        records_path.write_text(json.dumps({'positives_all': positives_all, 'negatives_all': negatives_all, 'counts': counts, 'positive_rows': positive_rows,
                                            'negative_rows': negative_rows, 'photo_report': photo_report,
                                            'timing': {'per_scan_s_measured': per_scan, 'positives_s': positives_s, 'negatives_s': negatives_s, 'photos_s': photos_s}}, ensure_ascii=False), encoding='utf-8')
    pos = [r for r in positive_rows if 'error' not in r]; neg = [r for r in negative_rows if 'error' not in r]
    fa, rc, fa_n, rc_n = evaluate(pos, neg)
    photo_rows = [r for r in photo_report['rows'] if 'skipped' not in r]
    rules = {'current_0.80_0.07': {'similarity': CURRENT[0], 'margin': CURRENT[1]}}
    for limit, name in FA_TARGETS:
        rules[f'best_{name}'] = best_rule(fa, rc, limit)
    for name, r in rules.items():
        if r is None: continue
        t, m = r['similarity'], r['margin']
        # Rules off the grid (the current 0.07 margin) are scored directly.
        accepted_neg = sum(1 for x in neg if x['similarity'] >= t and x['margin'] >= m)
        accepted_pos = sum(1 for x in pos if x['similarity'] >= t and x['margin'] >= m and x['correct'])
        r.update(false_accept_rate=accepted_neg / max(len(neg), 1), false_accepts=accepted_neg, recall=accepted_pos / max(len(pos), 1), recall_n=accepted_pos,
                 scans={'positives': rule_stats(pos, t, m), 'negatives': rule_stats(neg, t, m)}, photos=rule_stats(photo_rows, t, m))
    def summary(rows, with_truth):
        sims = np.array([r['similarity'] for r in rows]); margins = np.array([r['margin'] for r in rows])
        out = {'n': len(rows), 'similarity_median': round(float(np.median(sims)), 4), 'similarity_p95': round(float(np.percentile(sims, 95)), 4), 'similarity_max': round(float(sims.max()), 4),
               'margin_median': round(float(np.median(margins)), 4), 'margin_p95': round(float(np.percentile(margins, 95)), 4), 'margin_max': round(float(margins.max()), 4),
               'by_rarity': {k: v for k, v in rule_stats(rows, 0, 0)['by_rarity'].items()}}
        if with_truth:
            ts = [r['truth_score'] for r in rows if r['truth_score'] is not None]
            out.update(top1_correct=int(sum(r['correct'] for r in rows)), truth_score_median=round(float(np.median(ts)), 4), truth_score_min=round(float(min(ts)), 4),
                       distinct_identities=len({r['card_id'] for r in rows}),
                       wrong_top1=[{'product_id': r['product_id'], 'truth': r['card_id'], 'top1': r['top1'], 'similarity': r['similarity'], 'margin': r['margin'], 'rarity': r['rarity']} for r in rows if not r['correct']])
        return out
    report = {'date': time.strftime('%Y-%m-%d %H:%M'), 'seed': args.seed, 'model_sha256': model_sha, 'budget_minutes': args.budget_minutes,
              'index': {'rows': len(model.rows), 'identities': len(pilot_ids), 'raw_identities': len(raw_ids), 'canonical_changes_pilot': len(raw_ids) - len(pilot_ids),
                        'note': 'margin computed between canonical card_ids; production groups by raw card_id (identical here since no pilot alias exists)'},
              'selection': {'min_width': args.min_width, 'counts': counts, 'positives_available': len(positives_all), 'positives_run': len(pos), 'negatives_available': len(negatives_all), 'negatives_run': len(neg),
                            'negatives_stratification': 'round robin over rarity strata (unknown rarity is its own stratum)', 'errors': len(positive_rows) - len(pos) + len(negative_rows) - len(neg)},
              'timing': {'per_scan_s_measured': per_scan, 'measured_on': len(measure), 'positives_min': positives_s / 60, 'negatives_min': negatives_s / 60, 'photos_s': photos_s, 'total_min': (time.perf_counter() - started) / 60,
                         'encoder_threads': int(__import__('os').environ.get('YUGIOH_ONNX_THREADS') or 4), 'note': 'wall-clock on a shared CPU; not a benchmark'},
              'preprocessing': 'whole scan resized to 224x224 with cv2.resize (as vision_onnx.tensor), orientations 0/180, best top score kept, cosine on L2 vectors',
              'grid': {'similarity': SIM_GRID, 'margin': MARGIN_GRID, 'false_accept_rate': fa.round(5).tolist(), 'false_accepts': fa_n.tolist(), 'recall': rc.round(5).tolist(), 'recall_n': rc_n.tolist()},
              'rules': rules, 'positives': summary(pos, True), 'negatives': summary(neg, False), 'photos': photo_report,
              'caveats': ['Scans are flat, evenly lit photos: closer to the references than a table photo. False-accept rate and recall are both optimistic for real tables.',
                          'Positives are matched by card_id; a scan may show an alternate artwork the pilot reference does not have.',
                          'Negatives are stratified by rarity, not proportional to the market; rarity is unknown for a large share of products.',
                          'The pilot index has 50 identities; with a larger index the margins shrink and this calibration must be repeated.'],
              'records': positive_rows + negative_rows}
    (OUT / 'acceptance.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'acceptance.md').write_text(markdown(report), encoding='utf-8')
    print('RULES', json.dumps({k: (None if v is None else {kk: v[kk] for kk in ('similarity', 'margin', 'false_accept_rate', 'recall')}) for k, v in rules.items()}, indent=1))
    print(f'DONE total {(time.perf_counter() - started) / 60:.1f} min', flush=True)


if __name__ == '__main__':
    main()
