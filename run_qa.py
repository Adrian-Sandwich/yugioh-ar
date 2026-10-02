"""Run the qa_*.py checks and summarise them (one process each, as they were written).

    python run_qa.py --ci        # the checks that pass on a clean clone, without data/ or models (CI)
    python run_qa.py             # every qa_*.py; several need data/, models, a browser or the GPU
    python run_qa.py qa_duel_engine.py qa_table_duel.py

CI is the list below; docs/CI.md says what each one covers. Exit code 1 if any check fails.
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CI = ['qa_duel_engine.py', 'qa_shared_snapshot.py', 'qa_sprite_cache.py', 'qa_live_tracking.py', 'qa_camera_source.py',
      'qa_pipeline_core.py', 'qa_card_geometry.py', 'qa_card_evidence.py', 'qa_enroll_reference.py', 'qa_pose_from_captures.py',
      'qa_catalog_sync.py', 'qa_curated_registry.py', 'qa_download_watch.py', 'qa_printing_art_links.py',
      'qa_table_duel.py', 'qa_name_pick.py', 'qa_auto_sprite_reload.py', 'qa_server_loop.py', 'qa_playmat.py', 'qa_util.py', 'qa_contracts.py']


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ci', action='store_true'); ap.add_argument('scripts', nargs='*')
    a = ap.parse_args()
    scripts = a.scripts or (CI if a.ci else sorted(p.name for p in ROOT.glob('qa_*.py')))
    (ROOT / 'research/qa').mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'PYTHONUTF8': '1'}; failed = []
    for name in scripts:
        started = time.perf_counter()
        r = subprocess.run([sys.executable, '-X', 'utf8', name], cwd=ROOT, env=env, capture_output=True, text=True, errors='replace')
        ok = r.returncode == 0; tail = (r.stdout + r.stderr).strip().splitlines()[-1:] or ['']
        print(f"{'ok   ' if ok else 'FALLA'} {name:34} {time.perf_counter() - started:6.1f} s  {tail[0][:110]}", flush=True)
        if not ok: failed.append(name)
    print(f'{len(scripts) - len(failed)}/{len(scripts)} pasaron' + (f"; fallaron: {', '.join(failed)}" if failed else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
