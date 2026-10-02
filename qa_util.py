"""util.quad_iou and util.atomic_write, and the shared settings module, on a temporary folder."""
import json
import os
import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

import settings
import util


def main():
    checks = []
    square = [[0, 0], [10, 0], [10, 10], [0, 10]]
    assert abs(util.quad_iou(square, [[5, 0], [15, 0], [15, 10], [5, 10]]) - 1 / 3) < 1e-6
    assert util.quad_iou(square, [[20, 20], [30, 20], [30, 30], [20, 30]]) == 0.
    import live_tracking, vision_onnx
    assert live_tracking.quad_iou is util.quad_iou and vision_onnx.quad_iou is util.quad_iou
    checks += ['quad IoU', 'one quad_iou shared by tracking and recognition']

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'index.json'
        util.atomic_write(path, json.dumps({'a': 1})); util.atomic_write(path, b'{"a": 2}')
        assert json.loads(path.read_text(encoding='utf-8')) == {'a': 2} and [p.name for p in Path(tmp).iterdir()] == ['index.json']
        # A rename refused for a moment (a reader holding the file on Windows) is retried.
        real, calls = os.replace, []
        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3: raise PermissionError('in use')
            real(src, dst)
        with patch.object(util.os, 'replace', flaky): util.atomic_write(path, 'x', wait=0)
        # >= 3: the real rename is sometimes refused for a moment too (a scanner holding the new file).
        assert path.read_text(encoding='utf-8') == 'x' and len(calls) >= 3, calls
        # Refused every time: the error surfaces and no temporary file is left behind.
        with patch.object(util.os, 'replace', lambda s, d: (_ for _ in ()).throw(PermissionError('in use'))):
            try: util.atomic_write(path, 'y', tries=3, wait=0)
            except PermissionError: pass
            else: raise AssertionError('a permanent failure must raise')
        assert [p.name for p in Path(tmp).iterdir()] == ['index.json'] and path.read_text(encoding='utf-8') == 'x'
        # Concurrent writers never leave a half-written file.
        errors = []
        def write(n):
            try: util.atomic_write(path, json.dumps({'n': n, 'pad': 'x' * 50_000}))
            except Exception as exc: errors.append(exc)  # an exception in a thread would not fail the check
        threads = [threading.Thread(target=write, args=(n,)) for n in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors, errors
        assert json.loads(path.read_text(encoding='utf-8'))['n'] in range(8)
    checks += ['atomic write of text and bytes', 'rename retried while refused', 'permanent failure raises and cleans up', 'concurrent writers']

    import name_ocr, set_ocr, passcode_ocr, registry, card_info
    assert name_ocr.DB == set_ocr.DB == passcode_ocr.DB == registry.DB == card_info.REGISTRY == settings.REGISTRY_DB
    assert vision_onnx.REFS == settings.REFS and vision_onnx.DEVICE == settings.ONNX_DEVICE
    checks += ['one registry path for every reader', 'recognizer scope and device from settings']
    print(json.dumps({'status': 'passed', 'checks': checks}))


if __name__ == '__main__':
    main()
