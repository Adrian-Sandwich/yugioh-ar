"""Image-to-3D bench: which generator turns our cut-outs into usable models on a 12 GB GPU.

Each generator lives in its own clone and venv under downloads/gen3d/<name> (not versioned;
their PyTorch/CUDA pins conflict with each other and with .venv-gpu). See research/GENERACION_3D.md.
This script only needs the standard library.

    python research/gen3d_bench.py run --sprites 6 [--approved] [--only sf3d,hunyuan]  # random data/auto-sprites
    python research/gen3d_bench.py run IMG.png ...                         # or explicit cut-outs
    python research/gen3d_bench.py sheet                                    # rebuild the HTML sheet

Per generator it runs one process with 1 image (cold: load + one model) and one with all N,
so per-model time = (T_N - T_1) / (N - 1) without parsing each tool's logs. Peak VRAM is sampled
from nvidia-smi over the process lifetime, minus the idle baseline (other apps included in it).
Report: research/qa/gen3d-bench.json. Models and sheet: downloads/gen3d/out/ (serve that folder:
python -m http.server -d downloads/gen3d/out 8771, then open http://localhost:8771/).
"""
import argparse, json, os, random, shutil, struct, subprocess, sys, threading, time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'downloads/gen3d'
OUT = BASE / 'out'
SPRITES = ROOT / 'data/auto-sprites'
REPORT = ROOT / 'research/qa/gen3d-bench.json'
WORKERS = Path(__file__).resolve().parent / 'gen3d_workers'


def py(name):
    v = BASE / name / '.venv'
    return v / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


# name -> (clone folder, argv after the python executable; OUT/<i>/mesh.glb for input i)
GENERATORS = {
    # TripoSR: no --bake-texture. Baking writes the mesh through xatlas, which only exports OBJ
    # (plus texture.png), even when the file is named mesh.glb. Without it: GLB, vertex colours.
    'triposr': ('triposr', lambda imgs, out: ['run.py', *imgs, '--output-dir', out, '--model-save-format', 'glb']),
    'sf3d': ('sf3d', lambda imgs, out: ['run.py', *imgs, '--output-dir', out, '--texture-resolution', '1024']),
    'hunyuan': ('hunyuan', lambda imgs, out: [str(WORKERS / 'hunyuan_mini.py'), '--output-dir', out, *imgs]),
    'hunyuan-tex': ('hunyuan', lambda imgs, out: [str(WORKERS / 'hunyuan_mini.py'), '--output-dir', out, '--texture', *imgs]),
}


def vram_mb():
    try:
        r = subprocess.run(['nvidia-smi', '--query-gpu=memory.used', '--format=csv,noheader,nounits'],
                           capture_output=True, text=True, timeout=5)
        return int(r.stdout.split()[0])
    except Exception:
        return None


def run_once(name, imgs, out, timeout):
    folder, argv = GENERATORS[name]
    exe, cwd = py(folder), BASE / folder
    if not exe.exists():
        return {'exit': 'sin-venv', 'error': f'falta {exe}; ver research/GENERACION_3D.md'}
    shutil.rmtree(out, ignore_errors=True); out.mkdir(parents=True)
    base, peak, done = vram_mb(), [0], threading.Event()

    def sample():
        while not done.is_set():
            v = vram_mb()
            if v is not None: peak[0] = max(peak[0], v)
            time.sleep(0.25)
    threading.Thread(target=sample, daemon=True).start()
    t0 = time.perf_counter()
    try:
        p = subprocess.run([str(exe), '-X', 'utf8', *argv([str(i) for i in imgs], str(out))], cwd=cwd,
                           capture_output=True, text=True, timeout=timeout)
        code, err = p.returncode, p.stderr[-2000:]
    except subprocess.TimeoutExpired:
        code, err = 'timeout', ''
    secs = time.perf_counter() - t0
    done.set(); time.sleep(0.3)
    res = {'seconds': round(secs, 1), 'exit': code,
           'peak_vram_mb': (peak[0] - base) if base is not None and peak[0] else None}
    if code != 0:
        res['oom'] = 'out of memory' in err.lower()
        res['stderr_tail'] = err[-600:]
    return res


def glb_stats(path):
    """Triangles, colour and size straight from the GLB JSON chunk (no trimesh needed)."""
    data = path.read_bytes()
    if data[:4] != b'glTF':
        return {'error': 'no es GLB', 'kb': round(len(data) / 1024)}
    n = struct.unpack_from('<I', data, 12)[0]
    gltf = json.loads(data[20:20 + n])
    tris, vcolor = 0, False
    for mesh in gltf.get('meshes', []):
        for prim in mesh['primitives']:
            acc = gltf['accessors'][prim['indices'] if 'indices' in prim else prim['attributes']['POSITION']]
            tris += acc['count'] // 3
            vcolor |= 'COLOR_0' in prim['attributes']
    return {'triangles': tris, 'textured': bool(gltf.get('textures')), 'vertex_colors': vcolor, 'kb': round(len(data) / 1024)}


def cmd_run(a):
    if a.images:
        imgs = [Path(p).resolve() for p in a.images]
    else:
        # Only real cut-outs: a hologram is the whole artwork, and every generator turns that
        # rectangle into a block (30/09/2026: two of three approved samples were holograms).
        index = json.loads((SPRITES / 'index.json').read_text(encoding='utf-8')) if (SPRITES / 'index.json').exists() else {}
        pool = [p for p in sorted(SPRITES.glob('*.png')) if index.get(p.stem, {}).get('status') == 'ok']
        if a.approved:  # only cut-outs a person approved in review_server.py
            last = {}
            for line in (ROOT / 'research/reviews/sprite.jsonl').read_text(encoding='utf-8').splitlines():
                if line.strip(): v = json.loads(line); last[v['id']] = v['verdict']
            pool = [p for p in pool if last.get(p.stem) == 'approve']
        if not pool: sys.exit(f'sin recortes en {SPRITES}; pasa imágenes explícitas')
        imgs = random.Random(a.seed).sample(pool, min(a.sprites, len(pool)))
    if len(imgs) < 2: sys.exit('hacen falta al menos 2 imágenes para separar carga y generación')
    names = a.only.split(',') if a.only else list(GENERATORS)
    (OUT / 'inputs').mkdir(parents=True, exist_ok=True)
    for i in imgs: shutil.copy(i, OUT / 'inputs' / i.name)
    report = {'date': date.today().isoformat(), 'inputs': [i.name for i in imgs], 'generators': {}}
    if REPORT.exists():
        old = json.loads(REPORT.read_text(encoding='utf-8'))
        if old.get('inputs') == report['inputs']: report['generators'] = old.get('generators', {})
    for name in names:
        print(f'== {name}', flush=True)
        work = BASE / 'work' / name
        cold = run_once(name, imgs[:1], work / 'cold', a.timeout)
        print('  frío:', cold, flush=True)
        full = run_once(name, imgs, work / 'full', a.timeout * len(imgs)) if cold['exit'] == 0 else None
        r = {'cold': cold, 'batch': full}
        if full and full['exit'] == 0:
            r['s_per_model'] = round((full['seconds'] - cold['seconds']) / (len(imgs) - 1), 1)
            if r['s_per_model'] < 0:
                if cold['seconds'] - full['seconds'] > .3 * full['seconds']:
                    # The first run ever downloads the weights inside the cold process (TripoSR: 111 s
                    # against 9.7 s afterwards): the difference means nothing until a second run.
                    r['s_per_model'] = None
                    print('  aviso: la corrida en frío descargó pesos; vuelve a correr el banco para medir', flush=True)
                else:  # timing noise around a near-zero cost per model (SF3D: 17.1 s cold, 16.2 s for six)
                    r['s_per_model'] = 0.0
            r['models'] = {}
            (OUT / name).mkdir(parents=True, exist_ok=True)
            for i, img in enumerate(imgs):
                src = work / 'full' / str(i) / 'mesh.glb'
                if src.exists():
                    dst = OUT / name / (img.stem + '.glb'); shutil.copy(src, dst)
                    r['models'][img.stem] = glb_stats(dst)
            print(f"  {r['s_per_model']} s/modelo, pico {full['peak_vram_mb']} MB", flush=True)
        report['generators'][name] = r
        REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    write_sheet(report)
    print(f'informe: {REPORT.relative_to(ROOT)}  hoja: {OUT / "index.html"}')


def write_sheet(report):
    gens = [g for g, r in report['generators'].items() if r.get('models')]
    rows = []
    for name in report['inputs']:
        stem = Path(name).stem
        cells = [f'<td><img src="inputs/{name}"></td>']
        for g in gens:
            m = report['generators'][g]['models'].get(stem)
            if not m or 'error' in m:
                cells.append(f'<td>{(m or {}).get("error", "—")}</td>'); continue
            color = '' if m['textured'] else ' · color por vértice' if m.get('vertex_colors') else ' · sin color'
            cells.append(f'<td><model-viewer src="{g}/{stem}.glb" camera-controls auto-rotate shadow-intensity="1"></model-viewer>'
                         f'<small>{m["triangles"]:,} tri · {m["kb"]} KB{color}</small></td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    head = ''.join(f"<th>{g}<br><small>{report['generators'][g]['s_per_model']} s/modelo · "
                   f"pico {report['generators'][g]['batch']['peak_vram_mb'] or 'n/d'} MB</small></th>" for g in gens)
    (OUT / 'index.html').write_text(f'''<!doctype html><meta charset="utf-8"><title>Banco 3D {report["date"]}</title>
<script type="module" src="https://cdn.jsdelivr.net/npm/@google/model-viewer@4.1.0/dist/model-viewer.min.js"></script>
<style>body{{font:14px system-ui;margin:16px;background:#111;color:#ddd}}table{{border-collapse:collapse}}
td,th{{border:1px solid #333;padding:6px;text-align:center;vertical-align:top}}img{{height:220px}}
model-viewer{{width:260px;height:220px;background:#222;display:block}}small{{color:#999}}</style>
<h1>Banco imagen→3D · {report["date"]}</h1><table><tr><th>recorte</th>{head}</tr>{"".join(rows)}</table>''', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run'); r.add_argument('images', nargs='*'); r.add_argument('--sprites', type=int, default=6)
    r.add_argument('--approved', action='store_true', help='sample only sprites approved in review_server.py')
    r.add_argument('--seed', type=int, default=7); r.add_argument('--only'); r.add_argument('--timeout', type=int, default=900)
    sub.add_parser('sheet')
    a = ap.parse_args()
    if a.cmd == 'run': cmd_run(a)
    else: write_sheet(json.loads(REPORT.read_text(encoding='utf-8')))


if __name__ == '__main__':
    main()
