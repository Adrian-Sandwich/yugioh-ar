"""Read the printing number (and passcode) printed on TCGplayer scans that the offline
reconstruction could not resolve. Resumable, sharded, no network.

Each worker takes every k-th unresolved product, resizes the scan to the
rectified card size and runs the local readers (`SetReader` for the set code,
`NumberReader` for the passcode). Results append to
downloads/tcgplayer-sample/scan-numbers.jsonl; products already there are
skipped, so the job can be stopped and resumed. Merge with
`tcgplayer_reconstruct.py --with-scans` afterwards.

    .venv-eval/Scripts/python.exe research/tcgplayer_scan_numbers.py --workers 4
"""
import argparse, json, subprocess, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'downloads/tcgplayer-sample'
RESULTS = BASE / 'scan-numbers.jsonl'


def targets():
    rec = json.loads((BASE / 'reconstructed.json').read_text(encoding='utf-8'))['items']
    manifest = json.loads((BASE / 'manifest.json').read_text(encoding='utf-8'))['items']
    done = set()
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding='utf-8').splitlines():
            try:
                done.add(str(json.loads(line)['product_id']))
            except ValueError:
                continue
    out = []
    for key, r in rec.items():
        if r.get('number') and r.get('number_source') == 'search':
            continue
        item = manifest.get(key, {})
        if item.get('status') != 'ok' or key in done:
            continue
        if r.get('number') and r.get('card_ids') and len(r['card_ids']) == 1:
            continue  # registry-resolved with a single identity: nothing to read
        out.append((key, BASE / item['path'], r.get('number_candidates') or ([r['number']] if r.get('number') else [])))
    return out


def worker(shard, workers):
    import cv2
    from passcode_ocr import NumberReader, SIZE
    reader = NumberReader()
    jobs = targets()[shard::workers]
    print(f'shard {shard}: {len(jobs)} scans', flush=True)
    started = time.perf_counter()
    with RESULTS.open('a', encoding='utf-8') as out:
        for i, (key, path, candidates) in enumerate(jobs):
            image = cv2.imread(str(path))
            if image is None:
                continue
            card = cv2.resize(image, SIZE, interpolation=cv2.INTER_AREA)
            try:
                printing = reader.read_set(card)
                best, ambiguous, _ = reader.read(card)
            except Exception as exc:
                out.write(json.dumps({'product_id': int(key), 'error': str(exc)}) + '\n'); continue
            row = {'product_id': int(key), 'set_code_read': printing.get('code'), 'set_status': printing.get('status'),
                   'set_candidates_registry': candidates, 'set_read_in_candidates': printing.get('code') in candidates if candidates else None,
                   'passcode': best['passcode'] if best and best['score'] >= .85 and not ambiguous else None,
                   'passcode_score': round(best['score'], 3) if best else None}
            out.write(json.dumps(row, ensure_ascii=False) + '\n'); out.flush()
            if (i + 1) % 100 == 0:
                print(f'shard {shard}: {i + 1}/{len(jobs)} {(time.perf_counter() - started) / 60:.1f} min', flush=True)
    print(f'shard {shard}: done', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=int, default=1)
    parser.add_argument('--shard', type=int, default=None, help='internal: run one shard in this process')
    args = parser.parse_args()
    if args.shard is not None:
        worker(args.shard, args.workers); return
    print(f'{len(targets())} scans to read with {args.workers} workers', flush=True)
    procs = [subprocess.Popen([sys.executable, '-X', 'utf8', '-u', __file__, '--workers', str(args.workers), '--shard', str(i)]) for i in range(args.workers)]
    codes = [p.wait() for p in procs]
    print('DONE', codes, flush=True)


if __name__ == '__main__':
    main()
