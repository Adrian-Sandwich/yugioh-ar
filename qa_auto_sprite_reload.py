"""Automatic sprites reach a running viewer: after auto_cutout.py build or review_server.py --apply
rewrites data/auto-sprites, the viewer maps new cards, drops removed ones, serves the new picture
and gives the page a new URL for it. Runs on a temporary folder; touches no real data."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from settings import QA_OUT  # outputs of the checks: .runtime/qa, not versioned
QA_OUT.mkdir(parents=True, exist_ok=True)
ROOT = Path(__file__).resolve().parent


def write(folder, sprites, version):
    """sprites: {name: bgr colour}. Index last, like build() and --apply."""
    for p in folder.glob('*.png'):
        if p.stem not in sprites: p.unlink()
    for name, colour in sprites.items():
        img = np.zeros((20, 16, 4), np.uint8); img[..., :3] = colour; img[..., 3] = 255
        cv2.imwrite(str(folder / f'{name}.png'), img)
    index = folder / 'index.json'
    index.write_text(json.dumps({n: {'status': 'ok'} for n in sprites}), encoding='utf-8')
    os.utime(index, ns=(version, version))  # distinct versions even within one clock tick (NTFS: 100 ns steps)


def main():
    import ar_overlay, camera_viewer, pipeline, vision_onnx
    checks = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp); auto = root / 'data/auto-sprites'; auto.mkdir(parents=True)
        write(auto, {'a1': (0, 0, 255)}, 10**18)
        with patch.object(ar_overlay, 'AUTO_SPRITES', auto), patch.object(vision_onnx, 'ROOT', root), \
             patch.object(pipeline, 'AUTO_SPRITES', auto):
            # Overlay: the cached picture is replaced once the index changes.
            overlay = ar_overlay.SpriteOverlay()
            assert overlay.load('auto:a1.png')[0, 0, 2] == 255
            overlay.cache['tdoane:x'] = 'kept'
            write(auto, {'a1': (255, 0, 0)}, 10**18 + 1 * 10**9)
            assert overlay.load('auto:a1.png')[0, 0, 2] == 255, 'throttle: no disk check within the second'
            overlay.refresh_auto(every=0)
            assert overlay.load('auto:a1.png')[0, 0, 0] == 255, 'new picture after the index changed'
            assert overlay.cache.get('tdoane:x') == 'kept', 'hand-made sprites stay cached'
            checks += ['overlay drops changed automatic sprites', 'throttled disk check', 'hand-made sprites untouched']

            # Recognizer: which cards have an automatic sprite follows the folder.
            rec = object.__new__(vision_onnx.LiveRecognizer)  # no models: only the sprite mapping
            rec.references = [{'source': 'x/a1.jpg'}, {'source': 'x/b2.jpg'}, {'source': 'x/c3.jpg', 'sprite_ref': 'tdoane:sprite:c3'}]
            rec.map_auto_sprites()
            assert [r.get('sprite_ref') for r in rec.references] == ['auto:a1.png', None, 'tdoane:sprite:c3']
            assert rec.refresh_auto_sprites() is False, 'unchanged index: no remap'
            write(auto, {'b2': (0, 255, 0)}, 10**18 + 2 * 10**9)
            assert rec.refresh_auto_sprites() is True
            assert [r.get('sprite_ref') for r in rec.references] == [None, 'auto:b2.png', 'tdoane:sprite:c3']
            checks += ['new automatic sprites mapped', 'removed ones unmapped', 'TDOANE sprites untouched', 'no remap without change']

            # Page: the URL carries the version, so the browser does not reuse the old picture.
            url1 = camera_viewer.track_payload([{'sprite_ref': 'auto:b2.png', 'corners': [[0, 0]] * 4}])[0]['sprite_url']
            write(auto, {'b2': (9, 9, 9)}, 10**18 + 3 * 10**9)
            url2 = camera_viewer.track_payload([{'sprite_ref': 'auto:b2.png', 'corners': [[0, 0]] * 4}])[0]['sprite_url']
            tdoane = camera_viewer.track_payload([{'sprite_ref': 'tdoane:sprite:c3', 'corners': [[0, 0]] * 4}])[0]
            assert url1 != url2 and url1.startswith('/sprite/auto:b2.png?v=') and 'sprite_url' not in tdoane
            checks += ['versioned URL for automatic sprites', 'new version after a change', 'hand-made sprite URLs unchanged']
    result = {'passed': True, 'checks': checks,
              'not_covered': 'the duel view (/duelo) caches /cutout/<ref> per page load: reload that page after --apply'}
    (QA_OUT / 'auto-sprite-reload.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
