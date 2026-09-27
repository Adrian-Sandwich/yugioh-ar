"""Restart a lab service when it dies, logging each exit.

    python supervise.py <name> -- <python args...>

The live viewer died once with a native access violation inside python314.dll
(27/09/2026, while the phone refused connections): no Python traceback, and
the camera page stayed dead until someone noticed. The child runs with
faulthandler on, so a repeat leaves every thread's Python stack in its error
log; this supervisor starts it again. More than MAX_RESTARTS exits within
WINDOW_S seconds stops the loop instead of restarting forever.
"""
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAX_RESTARTS, WINDOW_S = 5, 600


def main():
    if '--' not in sys.argv or sys.argv.index('--') != 2:
        sys.exit('uso: supervise.py <nombre> -- <argumentos de python>')
    name, args = sys.argv[1], sys.argv[3:]
    log = ROOT / '.runtime' / f'{name}.supervisor.log'
    log.parent.mkdir(exist_ok=True)
    env = {**os.environ, 'PYTHONFAULTHANDLER': '1'}
    exits = []
    while True:
        started = time.time()
        child = subprocess.Popen([sys.executable, '-X', 'utf8', *args], cwd=ROOT, env=env)
        with log.open('a', encoding='utf-8') as f:
            f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} inicio pid {child.pid}: {" ".join(args)}\n')
        try:
            code = child.wait()
        except KeyboardInterrupt:
            child.terminate(); child.wait(10); return
        now = time.time(); exits = [t for t in exits if now - t < WINDOW_S] + [now]
        # 0xC0000005 is an access violation; Windows reports it as 3221225477.
        with log.open('a', encoding='utf-8') as f:
            f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} salida código {code} ({code & 0xFFFFFFFF:#x}) tras {now - started:.0f} s\n')
        if code == 0:
            return
        if len(exits) > MAX_RESTARTS:
            with log.open('a', encoding='utf-8') as f:
                f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} {len(exits)} salidas en {WINDOW_S} s: no se reinicia más\n')
            sys.exit(1)
        time.sleep(2)


if __name__ == '__main__':
    main()
