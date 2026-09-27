"""Set-code OCR accuracy on TCGplayer scans, and whether other crop regions or thresholds read more.

Truth: the printing number recovered from TCGplayer's own search metadata
(`number_source == 'search'` in reconstructed.json). Registry-inferred numbers
are reported separately as weaker truth. Part A scores what
research/tcgplayer_scan_numbers.py already read (scan-numbers.jsonl) by rarity
and scan width, with character confusions for wrong reads. Part B re-reads a
stratified sample with alternative SET_REGIONS (vertical shifts, a wider
band) using set_ocr.SetReader on the scan resized to passcode_ocr.SIZE, exactly
like the batch job, and scores each variant at thresholds 0.80/0.85/0.90 from
the same raw observations. Module constants are never changed; the region
override lives only in this process.

Outputs: research/qa/calibration/set-regions.json and set-regions.md.

    .venv-eval/Scripts/python.exe -X utf8 research/calibrate_set_regions.py --sample 400
"""
import argparse, collections, json, random, struct, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import set_ocr
from set_ocr import SetReader, codes
from passcode_ocr import SIZE

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'downloads/tcgplayer-sample'
OUT = ROOT / 'research/qa/calibration'
BASELINE = set_ocr.SET_REGIONS
THRESHOLDS = (.80, .85, .90)


def jpeg_size(path):
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


def variants():
    """(name, regions): vertical shifts and a wider band, as fractions of card height/width."""
    out = {'baseline': BASELINE}
    for dy in (-.03, -.015, .015, .03):
        out[f'shift_{dy:+.3f}'] = tuple((x0, y0 + dy, x1, y1 + dy) for x0, y0, x1, y1 in BASELINE)
    out['wider_5pct'] = tuple((max(0., x0 - .05), y0, min(1., x1 + .05), y1) for x0, y0, x1, y1 in BASELINE)
    out['taller_1pct'] = tuple((x0, y0 - .01, x1, y1 + .01) for x0, y0, x1, y1 in BASELINE)
    return out


def confusions(read, truth):
    """Character substitutions between two same-length codes."""
    if not read or not truth or len(read) != len(truth):
        return []
    return [(a, b) for a, b in zip(read, truth) if a != b]


def bucket(width):
    return f'{min(width // 100 * 100, 700)}px'


def part_a(rows, manifest, reconstructed):
    stats = {'exact': collections.defaultdict(lambda: collections.Counter()), 'registry': collections.defaultdict(lambda: collections.Counter())}
    pairs = collections.Counter(); wrong_examples = []
    for r in rows:
        key = str(r['product_id']); rec = reconstructed.get(key) or {}; item = manifest.get(key) or {}
        truth = rec.get('number'); source = rec.get('number_source')
        if not truth or source not in ('search', 'registry'):
            continue
        size = jpeg_size(BASE / item['path']) if item.get('path') else None
        width = size[0] if size else 0
        groups = stats['exact' if source == 'search' else 'registry']
        for g in ('all', 'rarity:' + (rec.get('rarity') or item.get('rarity') or 'unknown'), 'width:' + bucket(width)):
            c = groups[g]; c['n'] += 1
            status = r.get('set_status') or 'error'
            c['status:' + status] += 1
            if r.get('set_code_read'):
                c['read'] += 1
                if r['set_code_read'] == truth:
                    c['correct'] += 1
                elif source == 'search':
                    c['wrong'] += 1
                    for pair in confusions(r['set_code_read'], truth):
                        pairs[pair] += 1
                    if len(wrong_examples) < 60 and g == 'all':
                        wrong_examples.append({'product_id': r['product_id'], 'read': r['set_code_read'], 'truth': truth, 'rarity': rec.get('rarity') or item.get('rarity'), 'width': width})
    def finish(groups):
        return {g: {**dict(c), 'accuracy_of_reads': round(c['correct'] / c['read'], 4) if c['read'] else None, 'coverage': round(c['correct'] / c['n'], 4) if c['n'] else None} for g, c in sorted(groups.items())}
    return {'exact_truth': finish(stats['exact']), 'registry_truth': finish(stats['registry']),
            'confusions_exact_truth': [{'read': a, 'truth': b, 'count': n} for (a, b), n in pairs.most_common(30)], 'wrong_examples': wrong_examples}


def stratified(entries, n, seed):
    strata = collections.defaultdict(list)
    for e in entries:
        strata[e['rarity']].append(e)
    rng = random.Random(seed)
    for v in strata.values():
        rng.shuffle(v)
    chosen = []; names = sorted(strata)
    while len(chosen) < n and any(strata[k] for k in names):
        for k in names:
            if strata[k] and len(chosen) < n:
                chosen.append(strata[k].pop())
    return chosen


def score(observations, truth, threshold):
    """SetReader's decision rule from raw observations at another threshold."""
    qualified = {code for o in observations if o['score'] >= threshold for code in o['codes']}
    if len(qualified) != 1:
        return 'ambiguous' if qualified else 'unreadable'
    return 'correct' if next(iter(qualified)) == truth else 'wrong'


def part_b(sample, seed):
    reader = SetReader(engine=__import__('passcode_ocr').NumberReader().engine)
    results = {}
    started = time.perf_counter()
    for name, regions in variants().items():
        set_ocr.SET_REGIONS = regions
        try:
            counts = {t: collections.Counter() for t in THRESHOLDS}; by_rarity = {t: collections.defaultdict(collections.Counter) for t in THRESHOLDS}
            for i, e in enumerate(sample):
                image = cv2.imread(str(BASE / e['path']))
                if image is None:
                    continue
                card = cv2.resize(image, SIZE, interpolation=cv2.INTER_AREA)
                observations = reader.read(card)['raw_observations']
                for o in observations:
                    o['codes'] = codes(o['text'])
                for t in THRESHOLDS:
                    outcome = score(observations, e['truth'], t)
                    counts[t][outcome] += 1; by_rarity[t][e['rarity']][outcome] += 1; by_rarity[t][e['rarity']]['n'] += 1
                if (i + 1) % 100 == 0:
                    print(f'{name} {i + 1}/{len(sample)} {(time.perf_counter() - started) / 60:.1f} min', flush=True)
            results[name] = {'regions': [list(r) for r in regions],
                             'thresholds': {str(t): {'n': len(sample), **dict(counts[t]), 'accuracy': round(counts[t]['correct'] / len(sample), 4),
                                                     'by_rarity': {k: dict(v) for k, v in sorted(by_rarity[t].items())}} for t in THRESHOLDS}}
            print(f"{name}: " + ', '.join(f"{t}: {results[name]['thresholds'][str(t)]['accuracy']:.3f}" for t in THRESHOLDS), flush=True)
        finally:
            set_ocr.SET_REGIONS = BASELINE
    return results, time.perf_counter() - started


def markdown(report):
    L = []; a = L.append
    a('# Calibración de regiones y umbral del OCR de set code — escaneos TCGplayer\n')
    a(f"Fecha: {report['date']}. Semilla {report['seed']}. Lecturas evaluadas: {report['rows']} (scan-numbers.jsonl).\n")
    a('## A. Lecturas existentes contra el número exacto de TCGplayer\n')
    a('| Grupo | n | leídas | correctas | erróneas | ilegibles | precisión de las leídas | cobertura |'); a('|---|---|---|---|---|---|---|---|')
    for g, c in report['part_a']['exact_truth'].items():
        a(f"| {g} | {c.get('n', 0)} | {c.get('read', 0)} | {c.get('correct', 0)} | {c.get('wrong', 0)} | {c.get('status:unreadable', 0)} | {c['accuracy_of_reads']} | {c['coverage']} |")
    a('\nConfusiones más frecuentes (leído → verdad):\n')
    a('| leído | verdad | veces |'); a('|---|---|---|')
    for p in report['part_a']['confusions_exact_truth'][:15]:
        a(f"| {p['read']} | {p['truth']} | {p['count']} |")
    a(f"\nCon verdad inferida por el registro (más débil): {report['part_a']['registry_truth'].get('all', {})}\n")
    a('## B. Variantes de región y umbral (muestra estratificada por rareza)\n')
    a(f"Muestra: {report['part_b']['sample']} escaneos ≥ {report['part_b']['min_width']} px con número exacto; {report['part_b']['minutes']:.1f} min.\n")
    a('| Variante | regiones | ' + ' | '.join(f'umbral {t}' for t in THRESHOLDS) + ' |'); a('|---|---|' + '---|' * len(THRESHOLDS))
    for name, r in report['part_b']['results'].items():
        a(f"| {name} | {r['regions']} | " + ' | '.join(f"{r['thresholds'][str(t)]['accuracy']:.3f} ({r['thresholds'][str(t)]['correct']}/{r['thresholds'][str(t)]['n']})" for t in THRESHOLDS) + ' |')
    a(f"\nConclusión automática: {report['conclusion']}\n")
    a('Los escaneos son fotos planas con borde blanco; una foto de mesa tiene perspectiva y menos píxeles. Esta calibración dice qué región lee mejor el escaneo, no la foto real.')
    return '\n'.join(L) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--sample', type=int, default=400); parser.add_argument('--min-width', type=int, default=400); parser.add_argument('--seed', type=int, default=20260926)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in (BASE / 'scan-numbers.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))['items']
    reconstructed = json.loads((BASE / 'reconstructed.json').read_text(encoding='utf-8'))['items']
    a = part_a(rows, manifest, reconstructed)
    print('part A all (exact truth):', a['exact_truth'].get('all'), flush=True)
    pool = []
    for key, rec in reconstructed.items():
        item = manifest.get(key) or {}
        if item.get('status') != 'ok' or rec.get('number_source') != 'search' or not rec.get('number'):
            continue
        size = jpeg_size(BASE / item['path'])
        if not size or size[0] < args.min_width:
            continue
        pool.append({'product_id': int(key), 'path': item['path'], 'truth': rec['number'], 'rarity': rec.get('rarity') or item.get('rarity') or 'unknown', 'width': size[0]})
    sample = stratified(pool, args.sample, args.seed)
    print(f'part B: pool {len(pool)}, sample {len(sample)}', flush=True)
    results, seconds = part_b(sample, args.seed)
    base = results['baseline']['thresholds']['0.85']['accuracy']
    best = max(((r['thresholds'][str(t)]['accuracy'], name, t) for name, r in results.items() for t in THRESHOLDS))
    gain = best[0] - base
    conclusion = (f"la mejor variante es {best[1]} con umbral {best[2]} ({best[0]:.3f} frente a {base:.3f} de la configuración actual); "
                  + ('la ganancia es menor de 2 puntos: no se justifica cambiar SET_REGIONS' if gain < .02 else 'la ganancia supera 2 puntos en escaneos; validar con fotos reales antes de cambiar SET_REGIONS'))
    report = {'date': time.strftime('%Y-%m-%d %H:%M'), 'seed': args.seed, 'rows': len(rows), 'part_a': a,
              'part_b': {'sample': len(sample), 'pool': len(pool), 'min_width': args.min_width, 'minutes': seconds / 60, 'results': results, 'size': list(SIZE)},
              'conclusion': conclusion}
    (OUT / 'set-regions.json').write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding='utf-8')
    (OUT / 'set-regions.md').write_text(markdown(report), encoding='utf-8')
    print('CONCLUSION', conclusion, flush=True)


if __name__ == '__main__':
    main()
