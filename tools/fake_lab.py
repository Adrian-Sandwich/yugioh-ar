"""A stand-in for the lab's camera viewer, for checking the Unreal view (unreal/YgoAR) without a
camera or cards: the same HTTP contract (/snapshot with X-Tracks, /scene, /duel, /card-info,
/cutout/<ref>), a saved capture as the video, the saved playmat calibration, and a scripted duel
on a 40 s loop:

     5 s  a face-down monster in Main Monster Zone 1 and a set card (card backs seen until 30 s)
     3 s  Dark Magician arrives in Main Monster Zone 3 (Normal Summon)
     9 s  Blue-Eyes White Dragon arrives in Main Monster Zone 5 (Special Summon)
    14 s  Battle Phase; 16 s the rival takes 2500; 19 s Main Phase 2
    24 s  both cards leave; 40 s the loop starts again (later than the 15 s arrival memory)

    python tools/fake_lab.py [--port 8799] [--image data/captures/<file>.jpg] [--tilt 40] [--tilt 40]
    UnrealEditor.exe unreal/YgoAR/YgoAR.uproject -game -LabUrl=http://127.0.0.1:8799

Only the timeline is invented: the camera pose comes from scene3d.py, card sheets from card_info,
sprites from ar_overlay, exactly as camera_viewer.py serves them.
"""
import argparse, json, math, re, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ar_overlay import SpriteOverlay  # noqa: E402
from card_info import card_sheet  # noqa: E402
from playmat import CALIBRATION, Mat  # noqa: E402
from scene3d import scene  # noqa: E402

LOOP = 40.
CARD_W, CARD_H = 59., 86.  # mm
CARDS = [  # (arrives, leaves, copy id, card id, sprite, zone, how it came)
    (3., 24., 'c1', 'c0285d04-cadd-402d-a865-799a182d7510', 'tdoane:sprite:46986414.png', 'monster:2', 'Invocación Normal'),
    (9., 24., 'c2', 'e0404755-1ade-4c7c-9a2a-b29b7755d860', 'tdoane:sprite:89631139.png', 'monster:4', 'Invocación Especial'),
]
BACKS = ('monster:0', 'spell:3')  # card backs seen from 5 s to 30 s: a face-down monster (its shield) and a set card


class Lab:
    def __init__(self, image, tilt=0., distance=0.):
        self.jpeg = Path(image).read_bytes()
        cal = json.loads(CALIBRATION.read_text(encoding='utf-8'))
        self.mats = [Mat(m['player'], m['corners'], size_mm=m.get('size_mm', (600, 350))) for m in cal['mats']]
        self.scene = scene(self.mats, cal['image_size'])
        if tilt: self.tilt(tilt, distance, cal['image_size'])

    def tilt(self, degrees, distance, image_size):
        """Film the same table from the player's side, looking down at `degrees` from the vertical: the
        capture and the mats' corners go through the homography of the table plane between both cameras
        (what stands above the table is smeared, as in any such warp)."""
        K = np.float64([[self.scene['intrinsics']['fx'], 0, self.scene['intrinsics']['cx']],
                        [0, self.scene['intrinsics']['fy'], self.scene['intrinsics']['cy']], [0, 0, 1]])
        plane = lambda R, t: K @ np.column_stack([R[:, 0], R[:, 1], t])
        R0 = np.float64(self.scene['camera']['rotation']); t0 = np.float64(self.scene['camera']['translation_mm'])
        s, c = math.sin(math.radians(degrees)), math.cos(math.radians(degrees))
        w, h = self.mats[0].size_mm; centre = np.float64([w / 2, h / 2, 0])
        distance = distance or float(np.linalg.norm(t0)) * 1.25
        R1 = np.float64([[1, 0, 0], [0, c, s], [0, -s, c]]); t1 = -R1 @ (centre + distance * np.float64([0, s, -c]))
        H = plane(R1, t1) @ np.linalg.inv(plane(R0, t0))
        frame = cv2.warpPerspective(cv2.imdecode(np.frombuffer(self.jpeg, np.uint8), cv2.IMREAD_COLOR), H, tuple(image_size))
        self.jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])[1].tobytes()
        self.mats = [Mat(m.player, cv2.perspectiveTransform(np.float64(m.corners).reshape(-1, 1, 2), H).reshape(-1, 2).tolist(),
                         size_mm=m.size_mm) for m in self.mats]
        self.scene = scene(self.mats, image_size)
        self.sprites = SpriteOverlay()
        self.started = time.time()
        self.names = {c[3]: (card_sheet(c[3]) or {}).get('name', c[3]) for c in CARDS}

    def clock(self):
        return (time.time() - self.started) % LOOP

    def card_corners(self, zone):
        """Image corners TL, TR, BR, BL of a card standing upright in a zone of player 0's mat."""
        mat = self.mats[0]
        _, x0, y0, x1, y1 = next(z for z in mat.layout if z[0] == zone)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2; w, h = CARD_W / mat.size_mm[0] / 2, CARD_H / mat.size_mm[1] / 2
        return mat.image_points([[cx - w, cy - h], [cx + w, cy - h], [cx + w, cy + h], [cx - w, cy + h]]).astype(float).round(1).tolist()

    def tracks(self):
        t = self.clock()
        return [{'track_id': copy, 'card_id': card, 'name': self.names[card], 'sprite_ref': sprite, 'stable': True,
                 'corners': self.card_corners(zone)} for at, leaves, copy, card, sprite, zone, _ in CARDS if at <= t < leaves]

    def duel(self):
        t = self.clock()
        phase = 'battle' if 14 <= t < 19 else 'main2' if 19 <= t < 24 else 'main1'
        board = [{'player': 0, 'zone': zone, 'copy_id': copy, 'card_id': card, 'name': self.names[card], 'position': 'attack'}
                 for at, leaves, copy, card, _, zone, _ in CARDS if at <= t < leaves]
        recent = [{'id': f'p{i}', 'text': f'{how}: {self.names[card]}', 'card_id': card}
                  for i, (at, leaves, copy, card, _, zone, how) in enumerate(CARDS) if at <= t]
        if t >= 16: recent.append({'id': 'p9', 'text': f'{self.names[CARDS[0][3]]} ataca directamente: 2500 de daño', 'card_id': CARDS[0][3]})
        return {'started': True, 'turn': 3, 'current': 0, 'phase': phase, 'battle_step': 'battle' if phase == 'battle' else None,
                'result': None, 'players': [
                    {'name': 'Yugi', 'lp': 8000, 'hand': 3, 'deck': 32, 'extra_deck': 0, 'graveyard': 1, 'banished': 0},
                    {'name': 'Kaiba', 'lp': 5500 if 16 <= t < 24 else 8000, 'hand': 4, 'deck': 31, 'extra_deck': 0, 'graveyard': 0, 'banished': 0}],
                'board': board, 'questions': [], 'pending_attack': None, 'recent': recent[::-1], 'calibrated': True, 'mode': 'one',
                'backs_seen': [{'player': 0, 'zone': zone} for zone in BACKS if 5 <= t < 30]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def send(self, code, body, kind, headers=None):
        self.send_response(code); self.send_header('Content-Type', kind); self.send_header('Content-Length', str(len(body)))
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        lab, url = self.server.lab, urlsplit(self.path)
        if url.path == '/snapshot':
            return self.send(200, lab.jpeg, 'image/jpeg', {'X-Captured-At': str(time.time()), 'X-Capture-Time-Basis': 'fake',
                                                            'X-Tracks': json.dumps(lab.tracks(), ensure_ascii=True, separators=(',', ':'))})
        if url.path == '/scene': return self.send(200, json.dumps(lab.scene).encode(), 'application/json')
        if url.path == '/duel': return self.send(200, json.dumps(lab.duel(), ensure_ascii=False).encode(), 'application/json')
        if url.path == '/card-info':
            sheet = card_sheet(parse_qs(url.query).get('id', [''])[0])
            return self.send(200, json.dumps(sheet, ensure_ascii=False).encode(), 'application/json') if sheet else self.send(404, b'Unknown card', 'text/plain')
        if url.path.startswith('/cutout/'):
            png = lab.sprites.cutout_png(unquote(url.path[len('/cutout/'):]))
            return self.send(200, png, 'image/png') if png else self.send(404, b'No sprite', 'text/plain')
        if re.fullmatch(r'/fx/[\w.-]+\.png', url.path) and (ROOT / 'web' / url.path[1:]).is_file():
            return self.send(200, (ROOT / 'web' / url.path[1:]).read_bytes(), 'image/png')
        self.send(404, b'Not found', 'text/plain')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--port', type=int, default=8799)
    ap.add_argument('--image', default=str(ROOT / 'data/captures/carta-2026-09-25T04-13-54-278Z.jpg'))
    ap.add_argument('--tilt', type=float, default=0., help='film the table from the side: degrees from the vertical (0 = as captured)')
    ap.add_argument('--distance', type=float, default=0., help='with --tilt: mm from the camera to the mat centre (default: 1.25 x the capture\'s)')
    a = ap.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', a.port), Handler); server.lab = Lab(a.image, a.tilt, a.distance)
    k, cam = server.lab.scene['intrinsics'], server.lab.scene['camera']
    print(f'labo simulado en http://127.0.0.1:{a.port} (ciclo de {LOOP:.0f} s); cámara a {cam["tilt_deg"]:.0f} grados, '
          f'{k["hfov_deg"]:.0f} grados de campo ({k["source"]})', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
