"""Keyboard review of generated assets: the card's artwork on the left, what we generated on the right.

    python review_server.py                          # automatic sprites (data/auto-sprites)
    python review_server.py --kind gen3d             # models from research/gen3d_bench.py
    python review_server.py --order hologram         # uncertain (default) | hologram | random | all
    python review_server.py --lan                    # reachable from a tablet on the home network
    python review_server.py --refiner sam2           # mask corrections with SAM 2 (default: auto)
    python review_server.py --control-new 150        # freeze a random control set (once)
    python review_server.py --control antes          # blind review of the control set, round "antes"
    python review_server.py --stats                  # summary -> research/qa/<kind>-review.json
    python review_server.py --apply                  # corrections and approved hologram candidates go into use

Keys (also on-screen buttons for touch): -> approve, <- reject (1-9 and 0 toggle reasons, / writes a
note, Enter saves, Esc cancels), D corrects the mask by drawing (pen, finger or mouse), down skip,
up/Backspace go back, B changes the background behind the asset.

Corrections: green strokes = "the cut-out ate this", red = "this is background". mask_refine.py
turns them into a full mask (GrabCut, or SAM 2 when installed). The strokes go to the verdict
line (versioned); the corrected mask to data/reviews/masks/<code>.png (regenerable from strokes).

Control set: a fixed random sample, excluded from the normal queue and from training, reviewed
blind in rounds (before and after retraining) to measure whether anything really improved.

Verdicts are human decisions, so they live apart from the regenerable data and are versioned:
research/reviews/<kind>.jsonl, append-only; the last line for an item wins (going back and
judging again corrects it). research/auto_cutout.py calibrate can then learn from them.

"uncertain" shows first the sprites whose critic score sits closest to its threshold: that is
where a human label moves the critic most (and where the TDOANE ground truth never reaches).
"""
import argparse, json, math, random, re, secrets, sys, time
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parent
ART = ROOT / 'downloads/ygoprodeck-art/art'
SPRITES = ROOT / 'data/auto-sprites'
CRITIC = ROOT / 'research/auto_cutout_critic.json'
GEN3D = ROOT / 'downloads/gen3d/out'
GEN3D_REPORT = ROOT / 'research/qa/gen3d-bench.json'
REVIEWS = ROOT / 'research/reviews'
CONTROL = REVIEWS / 'control.json'
RETEST = REVIEWS / 'sprite-retest.jsonl'
RANDOM_SHARE = .25   # of the 'uncertain' queue, drawn at random (see items_sprite)
RETEST_SHARE = .05   # of the pending queue, blind repeats of cards already judged
CANDIDATES = SPRITES / 'candidates'
KEY_FILE = ROOT / '.runtime/review-key'
MASKS = ROOT / 'data/reviews/masks'
SAFE = re.compile(r'^[A-Za-z0-9_.-]+$')

REASONS = {
    'sprite': [
        ('falta', 'Le falta parte del monstruo'),
        ('fondo', 'Incluye fondo'),
        ('bordes', 'Bordes sucios o con halo'),
        ('marco', 'El arte corta la figura'),
        ('ruido', 'Manchas o partes sueltas'),
        ('equivocado', 'Recortó otra cosa'),
        ('holograma', 'Mejor el arte completo'),
        # A hologram's candidate that did not separate the figure: it is the artwork again.
        ('igual', 'Candidato igual al holograma'),
        ('varios', 'Hay varias figuras y eligió mal'),
        ('otro', 'Otro (escribe la nota)'),
    ],
    'gen3d': [
        ('forma', 'La forma no se parece'),
        ('partes', 'Le faltan partes o sobran'),
        ('espalda', 'Espalda o lados mal inventados'),
        ('textura', 'Textura borrosa o errónea'),
        ('base', 'Pegado a una base o al fondo'),
        ('proporcion', 'Proporciones raras'),
        ('pesado', 'Demasiado pesado para AR'),
        ('recorte', 'El recorte de entrada ya era malo'),
        ('otro', 'Otro (escribe la nota)'),
    ],
}


def card_names():
    """artwork code -> card name, when the catalog is there (only for display)."""
    path = ROOT / 'data/full/catalog.json'
    names = {}
    try:
        for e in json.loads(path.read_text(encoding='utf-8')):
            name = e.get('name') or e.get('name_en') or e.get('card_name')
            if name and e.get('source'): names[Path(e['source']).stem] = name
    except (OSError, ValueError):
        pass
    return names


def control_codes():
    return set(json.loads(CONTROL.read_text(encoding='utf-8'))['codes']) if CONTROL.exists() else set()


# Two or more tablets share the queue: whoever shows a pending card holds it for LEASE_S (released by
# a verdict or by moving to another card), so two reviewers never judge the same card by accident.
LEASE_S = 600
# Verdicts saved before reviewers had names (29/09/2026) were all Adrian's.
LEGACY_REVIEWER = 'Adrian'


def reviewer_name(value):
    """The name a tablet gave itself (review.html asks once): short, printable, or None."""
    name = ' '.join(str(value or '').split())[:40]
    return name if name and name.isprintable() else None


def reviewer_of(v):
    return v.get('reviewer') or LEGACY_REVIEWER


def reviewer_counts(kind, control=None):
    """Verdicts per reviewer: every approve/reject line (skips left out)."""
    path = verdict_path(kind, control); out = Counter()
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                v = json.loads(line)
                if v['verdict'] != 'skip': out[reviewer_of(v)] += 1
    return dict(out.most_common())


def verdict_path(kind, control=None):
    return REVIEWS / 'control' / f'{control}.jsonl' if control else REVIEWS / f'{kind}.jsonl'


def load_verdicts(kind, control=None):
    path = verdict_path(kind, control)
    last = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                v = json.loads(line); last[v['id']] = v
    return last


def items_sprite(order, control=None):
    """Each item carries a fingerprint of the exact sprite shown (status, model, score): a verdict
    only counts while the sprite it judged is still the one on disk, so whatever build() redoes
    comes back to the queue. For a hologram, the item is the best cut-out that lost to it
    (research/hologram_candidates.py) when there is one: that is what the critic said no to."""
    index = json.loads((SPRITES / 'index.json').read_text(encoding='utf-8'))
    cands = json.loads((CANDIDATES / 'index.json').read_text(encoding='utf-8')) if (CANDIDATES / 'index.json').exists() else {}
    held = control_codes()
    # The candidate replaces a hologram only while nobody approved that hologram: on 29/09/2026 the
    # candidates arrived after 540 holograms had been judged, and the approved ones came back to the queue.
    judged = load_verdicts('sprite') if not control else {}
    threshold = json.loads(CRITIC.read_text(encoding='utf-8'))['threshold'] if CRITIC.exists() else .5
    out = []
    for code, e in index.items():
        if e.get('status') not in ('ok', 'hologram') or not (SPRITES / f'{code}.png').exists(): continue
        if (code in held) != bool(control): continue  # control cards only in control rounds
        c = cands.get(code) if e['status'] == 'hologram' else None
        if c and not (CANDIDATES / f'{code}.png').exists(): c = None
        if order == 'hologram' and e['status'] != 'hologram': continue
        if control: c = None  # control rounds judge what is in use, the hologram itself
        before = judged.get(code) if e['status'] == 'hologram' else None
        if before and before.get('fp') != sprite_fp(e): before = None  # it judged an earlier sprite
        if before and before['verdict'] == 'approve': c = None  # the approved hologram stays
        if c:
            item = {'right': f'/img/candidate/{code}.png', '_png': CANDIDATES / f'{code}.png', 'fp': f"cand|{c['model']}|{c['score']}",
                    'meta': {'código': code, 'estado': 'candidato', 'modelo': c['model'], 'crítico': c['score']}, '_score': c['score']}
            if before and before['verdict'] == 'reject': item['meta']['holograma'] = 'ya lo rechazaste'
        else:
            item = {'right': f'/img/sprite/{code}.png', '_png': SPRITES / f'{code}.png',
                    'fp': sprite_fp(e),
                    'meta': {'código': code, 'estado': e['status'], 'modelo': e.get('model'), 'crítico': e.get('score')}, '_score': e.get('score')}
        out.append({'id': code, 'left': f'/img/art/{code}.jpg', 'right_type': 'image', **item,
                    '_key': abs((item['_score'] if item['_score'] is not None else 1.) - threshold)})
    if control:
        random.Random(9).shuffle(out); tag = 'control'
    elif order == 'uncertain':
        # Uncertainty sampling alone biases what the critic learns: labels bunch up near the old
        # threshold (Settles 2009; Mussmann & Liang 2018). One card in four comes from a plain random
        # draw instead, tagged 'random', and critic_human.py sets thresholds and reports AUC on those.
        unc = sorted(out, key=lambda i: i['_key']); rnd = out[:]; random.Random(5).shuffle(rnd)
        used, merged, iu, ir = set(), [], 0, 0
        every = round(1 / RANDOM_SHARE)
        while len(merged) < len(out):
            take_random = len(merged) % every == every - 1
            src, k = (rnd, ir) if take_random else (unc, iu)
            while k < len(src) and src[k]['id'] in used: k += 1
            if k == len(src):  # that source is exhausted: take from the other
                take_random = not take_random; src, k = (rnd, ir) if take_random else (unc, iu)
                while src[k]['id'] in used: k += 1
            item = src[k]; used.add(item['id']); merged.append(dict(item, sampling='random' if take_random else 'uncertain'))
            if take_random: ir = k + 1
            else: iu = k + 1
        return merged
    elif order == 'random':
        random.Random(5).shuffle(out); tag = 'random'
    elif order == 'hologram':
        random.Random(5).shuffle(out); tag = 'hologram'
    else:
        out.sort(key=lambda i: i['id']); tag = 'all'
    return [dict(i, sampling=tag) for i in out]


def items_gen3d(order):
    report = json.loads(GEN3D_REPORT.read_text(encoding='utf-8'))
    out = []
    for gen, r in report['generators'].items():
        for stem, m in (r.get('models') or {}).items():
            if 'error' in m: continue
            left = f'/img/art/{stem}.jpg' if (ART / f'{stem}.jpg').exists() else f'/img/input/{stem}.png'
            out.append({'id': f'{gen}/{stem}', 'left': left, 'right': f'/img/gen3d/{gen}/{stem}.glb', 'right_type': 'model',
                        'fp': f"{report['date']}|{m['kb']}|{m['triangles']}",
                        'meta': {'código': stem, 'generador': gen, 'triángulos': m['triangles'],
                                 'color': 'textura' if m['textured'] else 'por vértice' if m.get('vertex_colors') else 'no', 'KB': m['kb']}})
    if order != 'all': random.Random(5).shuffle(out)
    return out


def load_retests():
    last = {}
    if RETEST.exists():
        for line in RETEST.read_text(encoding='utf-8').splitlines():
            if line.strip():
                v = json.loads(line); last[v['id']] = v
    return last


def add_retests(items):
    """Blind repeats: about 5 % of the pending cards are cards already judged, shown again without
    their verdict, badge or model (id 'retest:<code>'). Agreement with the first verdict is the
    ceiling on what any critic can learn from one reviewer (review_server.py --stats)."""
    verdicts = load_verdicts('sprite'); done = load_retests()
    judged = [i for i in items if (v := verdicts.get(i['id'])) and v['verdict'] in ('approve', 'reject')
              and not v.get('correction') and same_asset(v, i['fp']) and f"retest:{i['id']}" not in done]
    pending = sum(1 for i in items if not ((v := verdicts.get(i['id'])) and same_asset(v, i['fp'])))
    k = min(len(judged), round(pending * RETEST_SHARE))
    if not k: return items
    picks = random.Random(time.strftime('%Y%m%d')).sample(judged, k)
    repeats = [{**i, 'id': f"retest:{i['id']}", 'retest_of': i['id'], 'sampling': 'retest', 'no_draw': True,
                'meta': {'código': i['meta']['código']}} for i in picks]
    out, step = [], max(1, len(items) // (k + 1))
    for n, item in enumerate(items):
        out.append(item)
        if repeats and (n + 1) % step == 0: out.append(repeats.pop())
    return out + repeats


def build_queue(kind, order, control=None):
    items = items_sprite(order, control) if kind == 'sprite' else items_gen3d(order)
    if kind == 'sprite' and not control: items = add_retests(items)
    names = card_names()
    for i in items:
        i.pop('_key', None); i.pop('_score', None)
        name = names.get(i['meta']['código'])
        if name and not i.get('retest_of'): i['meta'] = {'carta': name, **i['meta']}
    return items


def base_mask(code, png, from_sprite):
    """Full-artwork mask of the cut-out shown. Sprites and candidates are cropped to their alpha's
    bounding box (auto_cutout.rgba) but keep the artwork's pixels, so the crop is found exactly by
    template matching. A hologram without candidate starts empty: the figure is drawn from scratch."""
    import cv2, numpy as np
    art = cv2.imread(str(ART / f'{code}.jpg'))
    mask = np.zeros(art.shape[:2], np.float32)
    sprite = cv2.imread(str(png), cv2.IMREAD_UNCHANGED) if from_sprite else None
    if sprite is not None and sprite.ndim == 3 and sprite.shape[2] == 4:
        h, w = sprite.shape[:2]
        if h <= art.shape[0] and w <= art.shape[1]:
            res = cv2.matchTemplate(art, np.ascontiguousarray(sprite[..., :3]), cv2.TM_SQDIFF)
            _, _, (x, y), _ = cv2.minMaxLoc(res)
            mask[y:y + h, x:x + w] = sprite[..., 3] / 255.
    return art, mask


def sprite_fp(e):
    """Fingerprint of the sprite in use for an index entry (see items_sprite)."""
    return f"{e.get('status')}|{e.get('model')}|{e.get('score')}|{e.get('correction', '')}"


def same_asset(v, fp):
    """Does verdict v still apply to the asset with fingerprint fp? Yes if it judged that very
    asset, or if the asset is what the verdict itself put in use (its correction, or the
    hologram candidate it approved, now promoted by --apply)."""
    old = v.get('fp')
    if old is None or old == fp: return True
    c = v.get('correction')
    if c and fp.startswith('ok|human|') and fp.endswith('|' + c['mask_sha1']): return True
    if v['verdict'] == 'approve' and old.startswith('cand|') and fp == 'ok|' + old[5:] + '|': return True
    return False


def mask_png(mask):
    """White RGBA with alpha = mask: the page uses it to dim what is outside the figure."""
    import cv2, numpy as np
    a = np.clip(mask * 255, 0, 255).astype(np.uint8)
    return cv2.imencode('.png', np.dstack([np.full_like(a, 255)] * 3 + [a]))[1].tobytes()


def clean_strokes(raw):
    out = []
    for st in (raw or [])[:80]:
        if st.get('mode') not in ('add', 'remove'): continue
        pts = [[float(p[0]), float(p[1]), min(max(float(p[2]) if len(p) > 2 else .5, 0.), 1.)] for p in st.get('pts', [])[:4000]]
        if pts: out.append({'mode': st['mode'], 'w': min(max(float(st.get('w', 8)), 1.), 120.), 'pts': pts})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def reply(self, status, body, ctype='application/json; charset=utf-8', headers=None):
        if isinstance(body, (dict, list)): body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        for k, v in (headers or {}).items(): self.send_header(k, v)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store'); self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers(); self.wfile.write(body)

    def file(self, path, ctype):
        if not path.is_file(): return self.reply(404, {'error': 'no existe'})
        self.reply(200, path.read_bytes(), ctype)

    def allowed(self):
        """On --lan every request needs the access key: ?k=... once (sets a cookie), then the cookie."""
        key = self.server.access_key
        if not key: return True
        q = parse_qs(urlsplit(self.path).query).get('k', [''])[0]
        cookie = SimpleCookie(self.headers.get('Cookie', '')).get('rk')
        ok = secrets.compare_digest(q, key) or (cookie is not None and secrets.compare_digest(cookie.value, key))
        if not ok:  # which device, which path, and whether a key or cookie came at all (never the values)
            hint = (f" largo={len(q)}/{len(key)} mayus={q.lower() == key.lower()} contiene={key in q}"
                    f" extra={sorted({c for c in q if not (c.isalnum() or c in '-_')})!r}") if q else ''
            print(f"403 {self.client_address[0]} {urlsplit(self.path).path} clave={'mal' if q else 'no'} cookie={'mal' if cookie else 'no'}{hint}"
                  f" agente={self.headers.get('User-Agent', '')[:60]!r}", file=sys.stderr, flush=True)
        return ok

    def do_GET(self):
        s = self.server; url = urlsplit(self.path); path = url.path
        if not self.allowed(): return self.reply(403, {'error': 'falta la clave de acceso (?k=...)'})
        if path == '/' and s.access_key and 'k=' in url.query:
            # Serve the page here, no redirect: the address keeps its ?k=, so a Home Screen web app
            # on the iPad (which keeps its own cookies, apart from Safari's) still opens with it.
            return self.reply(200, (ROOT / 'web/review.html').read_bytes(), 'text/html; charset=utf-8',
                              {'Set-Cookie': f'rk={s.access_key}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000'})
        if path.startswith('/api/mask/') and s.kind == 'sprite':
            code = path.rsplit('/', 1)[1]
            if not SAFE.match(code) or code not in s.known: return self.reply(404, {'error': 'no existe'})
            return self.reply(200, mask_png(self.base(code)[1]), 'image/png')
        if path == '/':
            return self.reply(200, (ROOT / 'web/review.html').read_bytes(), 'text/html; charset=utf-8')
        if path == '/api/queue':
            current = self.current_verdicts()
            items = [{k: x for k, x in dict(i, verdict=current(i)).items() if not k.startswith('_')} for i in s.items]
            if s.control:  # blind: the page never sees earlier rounds, only this round's own progress
                items = [dict(i, meta={'código': i['meta']['código']}) for i in items]
            if not s.revisit:  # pending first, then what is already judged (still reachable going back)
                pending = [i for i in items if not i['verdict']]
                # Blind repeats spread evenly over what is pending: placed among the whole queue, they
                # bunched at its front once the early cards were judged (290 in a row, no drawing).
                repeats = [i for i in pending if i.get('retest_of')]; rest = [i for i in pending if not i.get('retest_of')]
                step = max(1, len(rest) // (len(repeats) + 1)); spread = []
                for n, item in enumerate(rest):
                    spread.append(item)
                    if repeats and (n + 1) % step == 0: spread.append(repeats.pop(0))
                items = [i for i in items if i['verdict']] + spread + repeats
            start = sum(1 for i in items if i['verdict']) if not s.revisit else 0
            return self.reply(200, {'kind': s.kind, 'token': s.token, 'start': min(start, max(len(items) - 1, 0)),
                                    'control': s.control, 'can_draw': s.kind == 'sprite' and not s.control,
                                    'blind_repeats': sum(1 for i in s.items if i.get('retest_of')),
                                    'reasons': [{'id': k, 'label': l} for k, l in REASONS[s.kind]], 'items': items})
        parts = path.split('/')
        if len(parts) >= 4 and parts[1] == 'img' and all(SAFE.match(p) for p in parts[3:]):
            kind, rest = parts[2], parts[3:]
            if kind == 'art' and len(rest) == 1: return self.file(ART / rest[0], 'image/jpeg')
            if kind == 'sprite' and len(rest) == 1: return self.file(SPRITES / rest[0], 'image/png')
            if kind == 'candidate' and len(rest) == 1: return self.file(CANDIDATES / rest[0], 'image/png')
            if kind == 'input' and len(rest) == 1: return self.file(GEN3D / 'inputs' / rest[0], 'image/png')
            if kind == 'gen3d' and len(rest) == 2: return self.file(GEN3D / rest[0] / rest[1], 'model/gltf-binary')
        self.reply(404, {'error': 'ruta desconocida'})

    def body(self, limit):
        n = int(self.headers.get('Content-Length', 0))
        if n > limit: raise ValueError('demasiado grande')
        return json.loads(self.rfile.read(n))

    def base(self, code):
        it = self.server.known[code]
        return base_mask(code, it['_png'], it['meta'].get('estado') != 'hologram')

    def refined(self, code, strokes):
        art, base = self.base(code)
        with self.server.refine_lock:
            if self.server.refiner is None:
                import mask_refine; self.server.refiner = mask_refine.make(self.server.refiner_kind)
            r = self.server.refiner
            mask = r.refine(art, base, strokes, image_key=code) if r.name == 'sam2' else r.refine(art, base, strokes)
        return mask, r.name

    def current_verdicts(self):
        """item -> its standing verdict (None when unjudged, or when it judged a sprite since redone)."""
        s = self.server
        verdicts = load_verdicts(s.kind, s.control)
        if s.kind == 'sprite' and not s.control: verdicts = {**verdicts, **load_retests()}
        def current(i):
            v = verdicts.get(i['id'])
            if not v or not same_asset(v, i['fp']): return None
            return {'verdict': v['verdict'], 'reasons': v['reasons'], 'corrected': bool(v.get('correction'))}
        return current

    def claim(self, body):
        """Hold a pending card for this reviewer; say so when someone else holds or already judged it."""
        s = self.server; who = reviewer_name(body.get('reviewer')) or LEGACY_REVIEWER
        item = s.known.get(body.get('id'))
        if item is None: return self.reply(400, {'error': 'id'})
        verdict = self.current_verdicts()(item)
        now = time.monotonic(); counts = reviewer_counts(s.kind, s.control)
        with s.lock:
            # One card per reviewer: showing another releases the previous one.
            s.leases = {k: v for k, v in s.leases.items() if now - v[1] < LEASE_S and v[0] != who}
            if verdict: return self.reply(200, {'ok': False, 'why': 'judged', 'verdict': verdict, 'counts': counts})
            holder = s.leases.get(item['id'])
            if holder: return self.reply(200, {'ok': False, 'why': 'taken', 'by': holder[0], 'counts': counts})
            s.leases[item['id']] = (who, now)
        return self.reply(200, {'ok': True, 'counts': counts})

    def do_POST(self):
        s = self.server; path = urlsplit(self.path).path
        if not self.allowed(): return self.reply(403, {'error': 'falta la clave de acceso'})
        if path not in ('/api/verdict', '/api/refine', '/api/claim'): return self.reply(404, {'error': 'ruta desconocida'})
        if self.headers.get('X-Review-Token') != s.token: return self.reply(403, {'error': 'token'})
        try:
            body = self.body(2_000_000)
        except ValueError:
            return self.reply(400, {'error': 'json'})
        if path == '/api/claim': return self.claim(body)
        if path == '/api/refine':
            if s.kind != 'sprite' or s.control or body.get('id') not in s.known: return self.reply(400, {'error': 'id'})
            mask, _ = self.refined(body['id'], clean_strokes(body.get('strokes')))
            return self.reply(200, mask_png(mask), 'image/png')
        valid = {k for k, _ in REASONS[s.kind]}
        if body.get('id') not in s.known or body.get('verdict') not in ('approve', 'reject', 'skip'):
            return self.reply(400, {'error': 'id o veredicto'})
        if body['verdict'] == 'skip' and s.known[body['id']].get('retest_of'):
            return self.reply(200, {'ok': True, 'reasons': []})  # a skipped repeat is simply not counted
        reasons = [r for r in body.get('reasons', []) if r in valid]
        note = str(body.get('note', ''))[:500].strip()
        item = s.known[body['id']]
        strokes = clean_strokes(body.get('strokes')) if s.kind == 'sprite' and not s.control and not item.get('no_draw') else []
        if strokes and body['verdict'] == 'reject' and not reasons:
            # A correction without a chosen reason still says why: green = something was missing,
            # red = something extra. A reason the reviewer picked always wins over this guess.
            if any(st['mode'] == 'add' for st in strokes): reasons.append('falta')
            if any(st['mode'] == 'remove' for st in strokes): reasons.append('fondo')
        if body['verdict'] == 'reject' and not (reasons or note):
            return self.reply(400, {'error': 'un rechazo necesita un motivo o una nota'})
        line = {'id': item['id'], 'verdict': body['verdict'], 'reasons': reasons, 'note': note,
                'meta': {k: v for k, v in item['meta'].items() if k != 'carta'}, 'fp': item['fp'],
                'sampling': item.get('sampling'), 'ms': int(body.get('ms', 0)),
                'at': time.strftime('%Y-%m-%dT%H:%M:%S')}
        who = reviewer_name(body.get('reviewer'))
        if who: line['reviewer'] = who
        if strokes and body['verdict'] == 'reject':
            import cv2, hashlib
            mask, refiner = self.refined(item['id'], strokes)
            MASKS.mkdir(parents=True, exist_ok=True)
            png = cv2.imencode('.png', (mask * 255).astype('uint8'))[1].tobytes()
            (MASKS / f"{item['id']}.png").write_bytes(png)
            line['correction'] = {'strokes': [dict(st, pts=[[round(x, 1), round(y, 1), round(p, 2)] for x, y, p in st['pts']]) for st in strokes],
                                  'refiner': refiner, 'mask': f"data/reviews/masks/{item['id']}.png",
                                  'mask_sha1': hashlib.sha1(png).hexdigest()[:12]}
        if s.control: line['round'] = s.control
        path_out = verdict_path(s.kind, s.control)
        if item.get('retest_of'):
            first = load_verdicts('sprite').get(item['retest_of'], {})
            line.update(retest_of=item['retest_of'], first={'verdict': first.get('verdict'), 'reasons': first.get('reasons', [])})
            path_out = RETEST
        path_out.parent.mkdir(parents=True, exist_ok=True)
        with s.lock, open(path_out, 'a', encoding='utf-8') as f:
            f.write(json.dumps(line, ensure_ascii=False) + '\n')
            s.leases.pop(item['id'], None)
        self.reply(200, {'ok': True, 'reasons': reasons, 'counts': reviewer_counts(s.kind, s.control)})


def stats(kind):
    verdicts = load_verdicts(kind)
    judged = [v for v in verdicts.values() if v['verdict'] != 'skip']
    by = lambda key: {k: {'n': len(vs), 'approved': round(sum(v['verdict'] == 'approve' for v in vs) / len(vs), 3)}
                      for k, vs in sorted(group(judged, key).items(), key=lambda kv: str(kv[0]))}
    report = {'date': time.strftime('%Y-%m-%d'), 'kind': kind, 'judged': len(judged),
              'skipped': sum(v['verdict'] == 'skip' for v in verdicts.values()),
              'approved_share': round(sum(v['verdict'] == 'approve' for v in judged) / len(judged), 3) if judged else None,
              'reasons': Counter(r for v in judged for r in v['reasons']).most_common(),
              'median_ms': sorted(v.get('ms', 0) for v in judged)[len(judged) // 2] if judged else None}
    report['corrections'] = sum(1 for v in judged if v.get('correction'))
    # Who did how many: every approve/reject line (changing a verdict later counts again), and the
    # standing verdicts each one holds now, with their approval rate.
    mine = lambda who: [v for v in judged if reviewer_of(v) == who]
    report['by_reviewer'] = {who: {'verdicts': n, 'standing': len(mine(who)),
                                   'approved': round(sum(v['verdict'] == 'approve' for v in mine(who)) / max(1, len(mine(who))), 3)}
                             for who, n in reviewer_counts(kind).items()}
    if kind == 'sprite' and (REVIEWS / 'control').exists():
        # Same cards, judged blind in each round: the honest measure of improvement.
        report['control_rounds'] = {}; rounds = []
        for f in sorted((REVIEWS / 'control').glob('*.jsonl'), key=lambda p: p.stat().st_mtime):
            last = {c: v['verdict'] for c, v in load_verdicts(kind, f.stem).items() if v['verdict'] != 'skip'}
            vs = [v for v in load_verdicts(kind, f.stem).values() if v['verdict'] != 'skip']
            if vs:
                rounds.append((f.stem, last))
                report['control_rounds'][f.stem] = {'n': len(vs), 'approved': round(sum(v['verdict'] == 'approve' for v in vs) / len(vs), 3),
                                                    'approved_95ci': wilson(sum(v['verdict'] == 'approve' for v in vs), len(vs)),
                                                    'reasons': Counter(r for v in vs for r in v['reasons']).most_common(5)}
        # Paired: the same cards before and after. Only cards that changed carry information
        # (McNemar's exact test), far more sensitive than comparing two percentages.
        report['control_paired'] = [paired(a, b) for a, b in zip(rounds, rounds[1:])]
    if kind == 'sprite' and RETEST.exists():
        pairs = [(v['first']['verdict'], v['verdict']) for v in load_retests().values()
                 if v['verdict'] in ('approve', 'reject') and v.get('first', {}).get('verdict') in ('approve', 'reject')]
        if pairs:
            agree = sum(a == b for a, b in pairs) / len(pairs)
            pa = sum(a == 'approve' for a, _ in pairs) / len(pairs); pb = sum(b == 'approve' for _, b in pairs) / len(pairs)
            chance = pa * pb + (1 - pa) * (1 - pb)
            report['retest'] = {'n': len(pairs), 'agreement': round(agree, 3),
                                'kappa': round((agree - chance) / (1 - chance), 3) if chance < 1 else None,
                                'note': 'consistencia contigo mismo: el techo de lo que un crítico puede aprender de estas etiquetas'}
    if kind == 'sprite':
        report['by_model'] = by(lambda v: v['meta'].get('modelo'))
        report['by_status'] = by(lambda v: v['meta'].get('estado'))  # 'candidato' = cut-outs that lost to a hologram
        # Does the critic agree with people? Approval per score band is what calibrate needs.
        report['by_critic_band'] = by(lambda v: None if v['meta'].get('crítico') is None else round(int(v['meta']['crítico'] * 10) / 10, 1))
    else:
        report['by_generator'] = by(lambda v: v['meta'].get('generador'))
    out = ROOT / f'research/qa/{kind}-review.json'
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))


def wilson(k, n, z=1.96):
    """95 % interval of a proportion (Wilson): with 150 cards, about +-8 points around 60 %."""
    if not n: return None
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 3), round(c + h, 3)]


def paired(a, b):
    (na, va), (nb, vb) = a, b
    both = [c for c in va if c in vb]
    gained = sum(va[c] == 'reject' and vb[c] == 'approve' for c in both)
    lost = sum(va[c] == 'approve' and vb[c] == 'reject' for c in both)
    n = gained + lost
    # Exact two-sided McNemar: binomial test of `gained` among the n discordant cards, p = 1/2.
    p = min(1., 2 * sum(math.comb(n, k) for k in range(0, min(gained, lost) + 1)) / 2 ** n) if n else 1.
    return {'from': na, 'to': nb, 'cards_in_both': len(both), 'rejected_to_approved': gained,
            'approved_to_rejected': lost, 'mcnemar_p': round(p, 4),
            'reading': 'mejora clara' if p < .05 and gained > lost else 'empeora' if p < .05 else 'sin diferencia demostrable'}


def group(rows, key):
    g = defaultdict(list)
    for r in rows: g[key(r)].append(r)
    return g


def apply_reviews():
    """Put reviews to work in the sprites in use:
    - a correction replaces the sprite (model 'human');
    - an approved hologram candidate replaces the hologram (its own model and score).
    critic_human.py --requeue / --requeue-all never redo either, so no rebuild undoes them."""
    import cv2, numpy as np, shutil
    index_path = SPRITES / 'index.json'; index = json.loads(index_path.read_text(encoding='utf-8'))
    cands = json.loads((CANDIDATES / 'index.json').read_text(encoding='utf-8')) if (CANDIDATES / 'index.json').exists() else {}
    fixed = promoted = 0
    for code, v in load_verdicts('sprite').items():
        e = index.get(code, {}); c = v.get('correction')
        if v['verdict'] == 'reject' and c:
            if e.get('correction') == c['mask_sha1']: continue
            art = cv2.imread(str(ART / f'{code}.jpg')); mask = cv2.imread(str(ROOT / c['mask']), cv2.IMREAD_GRAYSCALE)
            if art is None or mask is None: print('falta', code); continue
            out = np.dstack([art, mask]); ys, xs = np.nonzero(mask > 16)
            if not len(ys): continue
            cv2.imwrite(str(SPRITES / f'{code}.png'), out[ys.min():ys.max() + 1, xs.min():xs.max() + 1], [cv2.IMWRITE_PNG_COMPRESSION, 6])
            index[code] = {'status': 'ok', 'model': 'human', 'score': None, 'correction': c['mask_sha1']}; fixed += 1
        elif v['verdict'] == 'approve' and v['meta'].get('estado') == 'candidato' and e.get('status') == 'hologram':
            cand = cands.get(code)
            if not cand or v.get('fp') != f"cand|{cand['model']}|{cand['score']}" or not (CANDIDATES / f'{code}.png').exists(): continue
            shutil.copy(CANDIDATES / f'{code}.png', SPRITES / f'{code}.png')
            index[code] = {'status': 'ok', 'model': cand['model'], 'score': cand['score'], 'promoted': True}; promoted += 1
    tmp = index_path.with_suffix('.tmp'); tmp.write_text(json.dumps(index), encoding='utf-8'); tmp.replace(index_path)
    print(f'{fixed} sprites reemplazados por su corrección · {promoted} hologramas pasan a recorte')


def lan_addresses():
    import socket
    addrs = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sk:
            sk.connect(('10.255.255.255', 1)); addrs.add(sk.getsockname()[0])  # no packet is sent
    except OSError:
        pass
    try:
        addrs |= {a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)}
    except OSError:
        pass
    return sorted(a for a in addrs if not a.startswith('127.'))


def lan_key():
    """Kept in .runtime/ (not versioned) so the tablet's cookie and bookmark survive restarts.
    Delete the file to revoke every device."""
    if KEY_FILE.exists(): return KEY_FILE.read_text(encoding='utf-8').strip()
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_urlsafe(9); KEY_FILE.write_text(key, encoding='utf-8'); return key


def new_control(n):
    if CONTROL.exists(): sys.exit(f'ya existe {CONTROL.relative_to(ROOT)}; bórralo a mano si de verdad quieres otro')
    index = json.loads((SPRITES / 'index.json').read_text(encoding='utf-8'))
    reviewed = set(load_verdicts('sprite'))
    pool = sorted(c for c, e in index.items() if e.get('status') in ('ok', 'hologram') and c not in reviewed)
    codes = sorted(random.Random(int(time.time())).sample(pool, min(n, len(pool))))
    REVIEWS.mkdir(parents=True, exist_ok=True)
    CONTROL.write_text(json.dumps({'created': time.strftime('%Y-%m-%d'), 'codes': codes}, indent=1), encoding='utf-8')
    print(f'{len(codes)} cartas de control en {CONTROL.relative_to(ROOT)}; fuera de la cola normal y del entrenamiento')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--kind', choices=('sprite', 'gen3d'), default='sprite')
    ap.add_argument('--order', choices=('uncertain', 'hologram', 'random', 'all'), default='uncertain')
    ap.add_argument('--revisit', action='store_true', help='start at the beginning, judged items included')
    ap.add_argument('--port', type=int, default=8770)
    ap.add_argument('--lan', action='store_true', help='listen on the home network, with an access key')
    ap.add_argument('--refiner', choices=('auto', 'sam2', 'grabcut'), default='auto')
    ap.add_argument('--control', metavar='ROUND', help='blind review of the control set for this round')
    ap.add_argument('--control-new', type=int, metavar='N')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--apply', '--apply-corrections', dest='apply', action='store_true', help='use corrections and approved candidates')
    a = ap.parse_args()
    if a.stats: return stats(a.kind)
    if a.apply: return apply_reviews()
    if a.control_new: return new_control(a.control_new)
    if a.control and not SAFE.match(a.control): sys.exit('nombre de ronda: letras, números, - y _')
    if a.control and not CONTROL.exists(): sys.exit('primero: python review_server.py --control-new 150')
    import threading
    server = ThreadingHTTPServer(('0.0.0.0' if a.lan else '127.0.0.1', a.port), Handler)
    server.kind, server.revisit, server.token, server.lock = a.kind, a.revisit, secrets.token_urlsafe(24), threading.Lock()
    server.leases = {}  # item id -> (reviewer, monotonic time): see LEASE_S
    server.control = a.control if a.kind == 'sprite' else None
    server.access_key = lan_key() if a.lan else None
    server.refiner, server.refiner_kind, server.refine_lock = None, a.refiner, threading.Lock()
    server.items = build_queue(a.kind, a.order, server.control)
    server.known = {i['id']: i for i in server.items}
    print(f'{len(server.items)} elementos' + (f' · ronda de control «{a.control}» (a ciegas)' if server.control else ''), flush=True)
    if a.lan:
        for ip in lan_addresses(): print(f'  tableta: http://{ip}:{a.port}/?k={server.access_key}', flush=True)
        print('  (misma red; si no conecta, revisa el firewall de Windows: ver PLAN_3D_Y_REVISION.md)', flush=True)
    else:
        print(f'  http://127.0.0.1:{a.port}/', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
