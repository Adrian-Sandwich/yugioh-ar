"""The viewer's duel: playmat calibration, camera observations and player decisions.

Glue between camera_viewer (tracks every analysis), playmat (zone and position)
and duel_engine (rules). The camera never summons or moves anything: stable
observations go to Duel.observe, whose discrepancies ("a card appeared in
monster:2") are shown as questions; a player's answer becomes the duel event,
with the card's name, ATK, DEF and level from card_info.

Only changes reach the engine: an analysis every ~0.25 s would otherwise add
hundreds of thousands of identical observations per hour to the duel log.
The duel log is saved after every event and replayed when the viewer restarts.
"""
import json
import threading
from pathlib import Path

import numpy as np

from duel_engine import Duel, DuelError
from playmat import Mat, ZoneTracker, tcg_layout

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / 'data/playmat'
MODES = {'printed': 'Plantilla impresa (automática)', 'two': 'Dos tapetes frente a frente', 'one': 'Un tapete'}
# Printed mats (playmat_print) are found on every analysis; while a hand covers
# their markers the last good position is kept this long.
MARKER_HOLD_S = 5.
ZONE_NAMES = {'field': 'Zona de Campo', 'graveyard': 'Cementerio', 'extra_deck': 'Mazo Extra', 'deck': 'Mazo'}
# Answers a player can give to each kind of discrepancy, per zone family.
ACTIONS = {
    ('unexplained', 'monster'): [('normal_summon', 'Invocación Normal'), ('special_summon', 'Invocación Especial'), ('set_monster', 'Colocada boca abajo')],
    ('unexplained', 'spell'): [('activate_spell_trap', 'Activada'), ('set_spell_trap', 'Colocada boca abajo')],
    ('missing', 'any'): [('send_to_graveyard', 'Al Cementerio'), ('banish', 'Desterrada'), ('return_to_hand', 'A la mano')],
    ('conflict', 'monster'): [('change_position', 'Cambio de posición'), ('flip', 'Volteada (Invocación por Volteo)')],
}


# Virtual board: always drawn over the video, placed with sliders instead of clicks.
# cx, cy: centre (fraction of the image); width: near edge (fraction of image width);
# tilt: far edge / near edge (camera pitch); depth: height stretch; rotation: degrees;
# gap: space between the two boards, in board heights.
VIRTUAL_DEFAULT = {'cx': .5, 'cy': .55, 'width': .7, 'tilt': .75, 'depth': 1., 'rotation': 0., 'gap': .08}


def virtual_corners(mode, params, image_size):
    """[{player, corners}] for the virtual board(s), corners TL, TR, BR, BL as each player sees them.

    With two players one quadrilateral spans both boards (player 2's above, turned
    180 degrees) and a single homography places them, so the far board comes out
    smaller with the right perspective instead of being tilted on its own.
    """
    import cv2
    import numpy as np
    from playmat import OFFICIAL_PX
    p = {**VIRTUAL_DEFAULT, **(params or {})}
    W, H = image_size
    rows = 1. if mode == 'one' else 2. + p['gap']
    near = p['width'] * W; far = near * p['tilt']
    height = near * OFFICIAL_PX[1] / OFFICIAL_PX[0] * rows * p['depth']
    cx, cy = p['cx'] * W, p['cy'] * H
    quad = np.float32([[cx - far / 2, cy - height / 2], [cx + far / 2, cy - height / 2], [cx + near / 2, cy + height / 2], [cx - near / 2, cy + height / 2]])
    angle = np.radians(p['rotation']); rot = np.float32([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    quad = (quad - [cx, cy]) @ rot.T + [cx, cy]
    table = cv2.getPerspectiveTransform(np.float32([[0, 0], [1, 0], [1, rows], [0, rows]]), np.float32(quad))
    place = lambda pts: cv2.perspectiveTransform(np.float32(pts).reshape(-1, 1, 2), table).reshape(-1, 2).tolist()
    mats = [{'player': 0, 'corners': place([[0, rows - 1], [1, rows - 1], [1, rows], [0, rows]])}]
    if mode == 'two':
        mats.append({'player': 1, 'corners': place([[1, 1], [0, 1], [0, 0], [1, 0]])})
    return mats


PHASE_ORDER = ('draw', 'standby', 'main1', 'battle', 'main2', 'end')
MISSING_GRACE_S = 3.
EXTRA_DECK_WORDS = ('Sincronía', 'Xyz', 'Fusión', 'Link')
# Monsters sent to the Graveyard automatically this recently can still turn out to be the
# materials (or tributes) of the next monster placed.
MATERIAL_WINDOW_S = 20.
# Analyses (~0.2 s each) a zone keeps its back's id without seeing it: a hand over a set card.
BACK_HOLD = 20
SUMMON_EVENTS = ('normal_summon', 'set_monster', 'special_summon', 'set_spell_trap', 'activate_spell_trap', 'flip')


def zone_label(zone):
    kind, _, index = zone.partition(':')
    if kind == 'monster': return f'Zona de Monstruo {int(index) + 1}'
    if kind == 'spell': return f'Zona de Magia/Trampa {int(index) + 1}'
    if kind == 'extra_monster': return f'Zona de Monstruo Extra {int(index) + 1}'
    return ZONE_NAMES.get(zone, zone)


def family(zone):
    return 'monster' if zone.startswith(('monster:', 'extra_monster:')) else 'spell' if zone.startswith('spell:') or zone == 'field' else 'pile'


class TableDuel:
    def __init__(self, folder=None, sheet=None, stable=3):
        """`sheet(card_id)` returns the card's facts (card_info.card_sheet); None disables it.
        `folder` defaults to FOLDER read at call time, so tests can redirect it."""
        self.folder = Path(folder or FOLDER); self.sheet = sheet; self.stable = stable
        self.lock = threading.RLock()
        self.mode = None; self.mats = []; self.image_size = None; self.tracker = None; self.virtual = None
        self.duel = Duel(); self.observed = {}; self.cards = {}; self.missing = {}
        # Automatic plays (a card placed counts as the obvious play); `recent` lets the
        # players change or undo them, `tried` keeps an undone play from coming back.
        self.auto = True; self.recent = []; self.tried = set(); self.first_seen = {}; self.gestures = {}
        import time
        self.back_ids = {}; self.back_age = {}; self.back_seq = 0; self.back_session = f'{time.time():.0f}'
        calibration = self.folder / 'calibration.json'
        if calibration.exists():
            data = json.loads(calibration.read_text(encoding='utf-8'))
            self.virtual = data.get('virtual')
            self._set_mats(data['mode'], data['mats'], data.get('image_size'))
        saved = self.folder / 'duel.json'
        if saved.exists():
            try: self.duel = Duel.replay(json.loads(saved.read_text(encoding='utf-8'))['log'])
            except (DuelError, KeyError, ValueError): self.duel = Duel()  # unreadable: start clean, keep the file for inspection

    # --- calibration -----------------------------------------------------------
    def _set_mats(self, mode, mats, image_size):
        if mode not in MODES: raise ValueError(f'Modo desconocido: {mode!r}')
        if mode == 'printed':
            # No corners: the mats come from the markers of each analysed frame.
            self.mode = mode; self.mats = []; self.image_size = image_size; self.found = {}
            self.tracker = ZoneTracker([], stable=self.stable); self.observed.clear(); self.missing.clear()
            return
        players = sorted(m['player'] for m in mats)
        if players != ([0, 1] if mode == 'two' else [0]):
            raise ValueError('Dos tapetes: un tapete por jugador (0 y 1). Un tapete: sólo el jugador 0.')
        self.mats = [Mat(m['player'], m['corners']) for m in mats]
        self.mode = mode; self.image_size = image_size
        self.tracker = ZoneTracker(self.mats, stable=self.stable); self.observed.clear(); self.missing.clear()

    def preview(self, mode, virtual, image_size):
        """Zone outlines for virtual-board sliders, without changing the saved calibration."""
        if mode not in ('one', 'two'): raise ValueError('El tablero virtual es de uno o dos jugadores')
        mats = [Mat(m['player'], m['corners']) for m in virtual_corners(mode, virtual, image_size)]
        return self.overlay(mats) | {'mode': mode, 'virtual': {**VIRTUAL_DEFAULT, **(virtual or {})}, 'preview': True}

    def calibrate(self, mode, mats, image_size, virtual=None):
        """Clicked corners (`mats`), a printed template, or a virtual board placed with sliders (`virtual`)."""
        with self.lock:
            if virtual is not None:
                if mode not in ('one', 'two'): raise ValueError('El tablero virtual es de uno o dos jugadores')
                virtual = {**VIRTUAL_DEFAULT, **virtual}; mats = virtual_corners(mode, virtual, image_size)
            self.virtual = virtual
            self._set_mats(mode, mats, image_size)
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / 'calibration.json').write_text(json.dumps({'mode': mode, 'image_size': image_size, 'layout': 'printed' if mode == 'printed' else 'tcg-single',
                'virtual': virtual, 'mats': [] if mode == 'printed' else [{'player': m.player, 'corners': m.corners.tolist()} for m in self.mats]}, indent=2), encoding='utf-8')
            return self.overlay()

    def see_markers(self, image, now=None):
        """Printed mode: locate the mats in this frame; keep a mat MARKER_HOLD_S after its markers vanish."""
        import time
        from playmat_print import detect_mats
        with self.lock:
            if self.mode != 'printed': return
            now = time.time() if now is None else now
            for player, mat in detect_mats(image).items(): self.found[player] = (mat, now)
            self.found = {p: (m, t) for p, (m, t) in self.found.items() if now - t <= MARKER_HOLD_S}
            self.mats = [m for m, _ in sorted(self.found.values(), key=lambda v: v[0].player)]
            self.tracker.mats = self.mats

    def field_regions(self):
        """Image polygons of the field zones (Monster, Spell & Trap, Field, Extra Monster) of the
        current board, or None without a board: the recognizer skips cards outside them."""
        with self.lock:
            if not self.mats: return None
            return [mat.image_points([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]).tolist()
                    for mat in self.mats for name, x0, y0, x1, y1 in mat.layout if family(name) in ('monster', 'spell')]

    def zone_polygon(self, player, zone):
        with self.lock:
            mat = next((m for m in self.mats if m.player == player), None)
            rect = next((r for r in (mat.layout if mat else []) if r[0] == zone), None)
            if rect is None: return None
            _, x0, y0, x1, y1 = rect
            return mat.image_points([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]).tolist()

    def back_zones(self):
        """Zones where a face-down card can be (Main Monster, Spell & Trap, Field), for card_backs:
        [{'id': 'player|zone', 'polygon'}]. None without a board or before the duel starts."""
        with self.lock:
            if not self.mats or not self.duel.state['started']: return None
            return [{'id': f'{mat.player}|{name}', 'polygon': mat.image_points([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]).tolist()}
                    for mat in self.mats for name, x0, y0, x1, y1 in mat.layout if name.startswith(('monster:', 'spell:')) or name == 'field']

    def _back_tracks(self, backs):
        """Card backs seen this analysis as tracks: one id per zone while the back stays there
        (a hand over it for a moment keeps the id), a new id when a back comes back later."""
        self.back_age = {k: a + 1 for k, a in self.back_age.items()}
        tracks = []
        for back in backs or ():
            player, zone = back['id'].split('|'); key = (int(player), zone)
            polygon = self.zone_polygon(*key)
            if polygon is None: continue
            # Unique across restarts: a saved duel may hold older backs in its Graveyard.
            if key not in self.back_ids: self.back_seq += 1; self.back_ids[key] = f'back-{self.back_session}-{self.back_seq}'
            self.back_age[key] = 0
            tracks.append({'track_id': self.back_ids[key], 'corners': polygon, 'card_id': None, 'facedown': True})
        for key in [k for k, a in self.back_age.items() if a > BACK_HOLD]:
            del self.back_age[key]; self.back_ids.pop(key, None)
        return tracks

    def overlay(self, mats=None):
        """Zone outlines in image pixels, for drawing over the video (`mats`: a preview instead of the saved ones)."""
        with self.lock:
            zones = []
            for mat in (self.mats if mats is None else mats):
                for name, x0, y0, x1, y1 in mat.layout:
                    if name.startswith('extra_monster') and mat.player != 0: continue  # shared: drawn once
                    zones.append({'player': mat.player, 'zone': name, 'label': zone_label(name),
                                  'polygon': mat.image_points([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]).round(1).tolist()})
            return {'mode': self.mode, 'modes': MODES, 'image_size': self.image_size, 'zones': zones, 'virtual': self.virtual,
                    'mats': [{'player': m.player, 'corners': m.corners.tolist(), 'markers': getattr(m, 'markers', None)} for m in (self.mats if mats is None else mats)]}

    # --- camera ----------------------------------------------------------------
    def feed(self, tracks, backs=None):
        """Stable zone readings from this analysis; only changes are sent to the engine.
        `backs`: zones where card_backs saw a card back ([{'id': 'player|zone', ...}])."""
        with self.lock:
            if self.tracker is None: return []
            tracks = list(tracks) + self._back_tracks(backs)
            observations = self.tracker.update(tracks)
            for track in tracks:
                if track.get('card_id'): self.cards[track['track_id']] = track['card_id']
            now = {(o['player'], o['zone']): o for o in observations if family(o['zone']) != 'pile'}
            # A zone seen occupied that stops being reported for `stable` analyses is observed empty.
            for key in list(self.observed):
                if key in now or self.observed[key] is None: self.missing.pop(key, None); continue
                self.missing[key] = self.missing.get(key, 0) + 1
                if self.missing[key] >= self.stable: now[key] = {'player': key[0], 'zone': key[1], 'copy_id': None, 'card_id': None, 'position': None}
            if not self.duel.state['started']:
                self.observed.update({k: tuple(sorted(v.items())) for k, v in now.items()}); return observations
            for key, obs in now.items():
                signature = tuple(sorted(obs.items()))
                if self.observed.get(key) == signature: continue
                self.observed[key] = signature if obs['copy_id'] is not None else None; self.missing.pop(key, None)
                try: self.duel.observe(obs['player'], obs['zone'], obs['copy_id'], obs['card_id'], obs['position'])
                except DuelError: continue
                self._save()
            self._retrack()
            carried = self._gesture(tracks)
            if self.auto:
                import time
                now = time.monotonic(); keys = set()
                for pending in list(self.duel.state['pending']):
                    if pending not in self.duel.state['pending']: continue  # resolved by an earlier play (materials)
                    key = (pending['key'], pending.get('kind'), pending.get('copy_id'), pending.get('expected_copy'), pending.get('position'))
                    keys.add(key); first = self.first_seen.setdefault(key, now)
                    if key in self.tried: continue
                    # A monster that needs materials may be placed just before they are taken away.
                    if self._needs_materials(pending) and now - first < MISSING_GRACE_S: continue
                    # A monster being carried to attack leaves its zone empty on purpose.
                    if pending.get('expected_copy') in carried or pending.get('copy_id') in carried: continue
                    # A hand over a card also empties its zone for a moment: a card only
                    # "left the field" after MISSING_GRACE_S without it.
                    if pending.get('kind') == 'missing' and now - first < MISSING_GRACE_S: continue
                    self.tried.add(key)
                    if not self._came_back(pending): self._auto_play(pending)
                self.first_seen = {k: t for k, t in self.first_seen.items() if k in keys}
            return observations

    def _came_back(self, pending):
        """A card the table sent to the Graveyard (or banished) on its own is seen again in the zone it
        left, under the same track: it never left (a hand, a misreading covered it for a few seconds).
        Undo that automatic play instead of reading it as a card coming back from its pile."""
        if pending.get('kind') != 'moved' or (pending.get('known_at') or {}).get('zone') not in ('graveyard', 'banished'):
            return False
        play = next((r for r in self.recent if (r.get('event') or {}).get('type') in ('send_to_graveyard', 'banish')
                     and r['event'].get('copy_id') == pending.get('copy_id') and r['pending']['zone'] == pending['zone']), None)
        if play is None or any(r['start'] > play['start'] for r in self.recent):
            return False
        try: self.revise(play['id'])
        except (ValueError, DuelError): return False
        return True

    def _retrack(self):
        """The same face-up card seen again in its zone under a new track (the tracker lost it for a
        moment): follow it with the new copy_id instead of asking. Bookkeeping only, even with
        automatic plays off."""
        for p in list(self.duel.state['pending']):
            if p.get('kind') != 'different_copy' or p.get('known_at') is not None or not p.get('card_id'): continue
            known = self._model_card(p['player'], p['zone'])
            if not known or known['position'] in ('facedown', 'facedown_defense') or known.get('card_id') != p['card_id']: continue
            try: self.duel.apply({'type': 'retrack', 'player': p['player'], 'zone': p['zone'], 'copy_id': p['copy_id']})
            except DuelError: continue
            self._save()

    # --- automatic plays --------------------------------------------------------
    def _facts(self, pending):
        # A card that left its zone is known by the track it had there (expected_copy).
        card_id = pending.get('card_id') or self.cards.get(pending.get('copy_id')) or self.cards.get(pending.get('expected_copy'))
        return (self.sheet(card_id) if self.sheet and card_id else None) or {}

    def _plays(self, p):
        """Candidate events for one discrepancy, most likely first: (event, label)."""
        fam, kind, pos, facts = family(p['zone']), p.get('kind'), p.get('position'), self._facts(p)
        line, level, ctype = facts.get('line') or '', facts.get('level'), facts.get('card_type')
        base = {'player': p['player'], 'zone': p['zone'], 'copy_id': p.get('copy_id'), 'card_id': p.get('card_id')}
        if kind == 'moved' and fam == 'monster' and pos in ('attack', 'defense') and (p.get('known_at') or {}).get('zone') in ('graveyard', 'banished'):
            source = p['known_at']['zone']   # the same tracked card came back from its pile
            return [({**base, 'type': 'special_summon', 'position': pos if pos in ('attack', 'defense') else 'attack', 'source': source},
                     'Invocación Especial desde el ' + ('Cementerio' if source == 'graveyard' else 'destierro'))]
        if kind == 'different_copy' and p.get('known_at') is None and pos not in ('facedown_defense', 'facedown', None):
            # The back was there and now its face: the same card turned face-up, under the face's track.
            known = self._model_card(p['player'], p['zone'])
            reveal = self.card_spec(p.get('copy_id'), p.get('card_id')); reveal.pop('copy_id', None)
            flip = {'player': p['player'], 'copy_id': p['expected_copy'], 'reveal': reveal, 'as_copy': p.get('copy_id')}
            if known and known['position'] == 'facedown_defense' and pos in ('attack', 'defense'):
                label = 'Invocación por Volteo' if pos == 'attack' else 'Volteado por un efecto'
                return [({**flip, 'type': 'flip', 'position': pos}, label)] + ([({**flip, 'type': 'flip', 'position': 'defense'}, 'Volteado por un efecto')] if pos == 'attack' else [])
            if known and known['position'] == 'facedown' and fam == 'spell':
                return [({**flip, 'type': 'activate_spell_trap'}, 'Activada')]
        if kind == 'different_copy' and fam == 'monster' and p.get('known_at') is None:
            # Placed on top of one of its own materials (or tributes): only a summon using it explains it.
            return self._material_plays(p, facts, pos, base, forced=p.get('expected_copy'))
        if kind == 'unexplained' and fam == 'monster':
            if ctype and ctype != 'monster': return []
            extra = any(w in line for w in EXTRA_DECK_WORDS)
            materials = self._material_plays(p, facts, pos, base)
            if pos == 'facedown_defense': return materials + [({**base, 'type': 'set_monster'}, 'Colocado boca abajo')]
            special = ({**base, 'type': 'special_summon', 'position': pos if pos in ('attack', 'defense') else 'attack',
                        'source': 'extra_deck' if extra else 'hand'}, 'Invocación Especial')
            revive = self._revive(p, pos, base)
            if extra or p['zone'].startswith('extra_monster:'): return materials + revive + [special]
            plays = []
            if pos == 'attack' and (level is None or level <= 4): plays.append(({**base, 'type': 'normal_summon'}, 'Invocación Normal'))
            # A Level 5+ monster with no tributes more likely came back from the Graveyard.
            return materials + (plays + revive if plays else revive + plays) + [special]
        if kind == 'unexplained' and fam == 'spell':
            if ctype == 'monster' and 'Péndulo' not in line: return []
            if p.get('card_id') and pos != 'facedown': return [({**base, 'type': 'activate_spell_trap'}, 'Activada')]
            return [({**base, 'type': 'set_spell_trap'}, 'Colocada boca abajo')]
        if kind == 'missing':
            return [({'type': 'send_to_graveyard', 'player': p['player'], 'copy_id': p['expected_copy']}, 'Al Cementerio')]
        if kind == 'conflict' and 'position' in p.get('fields', []) and fam == 'monster':
            if p.get('expected_position') == 'facedown_defense' and pos == 'attack':
                return [({'type': 'flip', 'player': p['player'], 'copy_id': p['copy_id']}, 'Volteada')]
            if pos in ('attack', 'defense'):
                return [({'type': 'change_position', 'player': p['player'], 'copy_id': p['copy_id'], 'position': pos}, 'Cambio de posición')]
        return []

    def _model_card(self, player, zone):
        st = self.duel.state
        if zone.startswith('extra_monster:'): return st['shared']['extra_monster'][int(zone[-1])]
        kind, _, index = zone.partition(':')
        return st['players'][player]['field'][0] if zone == 'field' else st['players'][player][kind][int(index)]

    # --- summons with materials -------------------------------------------------
    def _material_facts(self, card):
        facts = (self.sheet(card.get('card_id')) if self.sheet and card.get('card_id') else None) or {}
        line = facts.get('line') or card.get('type') or ''
        level = facts.get('level') if facts else card.get('level')
        return {'copy_id': card['copy_id'], 'name': facts.get('name') or card.get('name') or 'monstruo', 'level': level, 'tuner': 'Cantante' in line}

    def _material_pool(self, player):
        """Own monsters that just left the field, as possible materials: the ones the camera no
        longer sees (still on the model's field), then the ones already sent to the Graveyard
        automatically (`reclaim`: those plays, newest first, undone if they are used)."""
        st = self.duel.state; pool = []
        field = {c['copy_id']: c for ps in st['players'] for c in ps['monster'] if c}
        field.update({c['copy_id']: c for c in st['shared']['extra_monster'] if c})
        for p in st['pending']:
            copy = p.get('expected_copy')
            if p['player'] == player and p.get('kind') in ('missing', 'different_copy') and family(p['zone']) == 'monster' and copy in field \
                    and field[copy]['controller'] == player and all(m['copy_id'] != copy for m in pool):
                pool.append(self._material_facts(field[copy]) | {'reclaim': None})
        import time
        now = time.monotonic(); reclaim = []
        for r in self.recent:
            e = r.get('event') or {}
            if e.get('type') != 'send_to_graveyard' or r['pending']['player'] != player or family(r['pending']['zone']) != 'monster' \
                    or now - r.get('time', 0) > MATERIAL_WINDOW_S: break
            reclaim.append(r)
        if reclaim:
            # Only observations may have happened since: anything else would be undone with them.
            ours = {i for r in reclaim for i in range(r['start'], r['end'])}
            if any(i not in ours and self.duel.log[i]['type'] != 'observe' for i in range(min(r['start'] for r in reclaim), len(self.duel.log))): reclaim = []
        grave = {c['copy_id']: c for c in st['players'][player]['graveyard']}
        for i, r in enumerate(reclaim):
            card = grave.get(r['event']['copy_id'])
            if card is None: break
            pool.append(self._material_facts(card) | {'reclaim': i})
        return pool, reclaim

    def _material_plays(self, p, facts, pos, base, forced=None):
        """Tribute, Synchro, Xyz, Link and Fusion Summons whose materials fit the monsters that
        just left the field: (event, label) with the materials named, most likely first."""
        import itertools
        line, level, rank, link = facts.get('line') or '', facts.get('level'), facts.get('rank'), facts.get('link')
        pool, reclaim = self._material_pool(p['player'])
        if not pool: return []
        position = pos if pos in ('attack', 'defense') else 'attack'
        def fits(rule, sizes):
            for n in sizes:
                for combo in itertools.combinations(pool, n):
                    ids = {m['copy_id'] for m in combo}
                    used = sorted(m['reclaim'] for m in combo if m['reclaim'] is not None)
                    # Reclaimed plays are undone newest first: the ones used must be the newest ones.
                    if (forced is None or forced in ids) and used == list(range(len(used))) and rule(combo): return list(combo)
        def play(event, label, ms):
            used = [m['reclaim'] for m in ms if m['reclaim'] is not None]
            return ({**base, **event, '_reclaim': reclaim[:max(used) + 1] if used else [], '_with': ' + '.join(m['name'] for m in ms)}, label)
        ids = lambda ms: [m['copy_id'] for m in ms]
        extra = {'type': 'special_summon', 'position': position, 'source': 'extra_deck'}
        every = range(len(pool), 0, -1); plays = []
        if 'Sincronía' in line and level:
            ms = fits(lambda c: sum(m['tuner'] for m in c) == 1 and all(m['level'] for m in c) and sum(m['level'] for m in c) == level, every)
            if ms: plays.append(play({**extra, 'materials': ids(ms)}, 'Invocación Sincronía', ms))
        if 'Xyz' in line and rank:
            ms = fits(lambda c: len(c) >= 2 and all(m['level'] == rank for m in c), every)
            if ms: plays.append(play({**extra, 'materials': ids(ms), 'attach': True}, 'Invocación Xyz', ms))
        if 'Link' in line and link:
            ms = fits(lambda c: True, [link])
            if ms: plays.append(play({**extra, 'materials': ids(ms)}, 'Invocación Link', ms))
        if 'Fusión' in line:
            ms = fits(lambda c: len(c) >= 2, every)
            if ms: plays.append(play({**extra, 'materials': ids(ms)}, 'Invocación por Fusión', ms))
        if not any(w in line for w in EXTRA_DECK_WORDS) and level and level >= 5 and p['zone'].startswith('monster:'):
            ms = fits(lambda c: True, [1 if level <= 6 else 2])
            if ms and pos == 'attack': plays.append(play({'type': 'normal_summon', 'tributes': ids(ms)}, 'Invocación por Tributo', ms))
            elif ms and pos == 'facedown_defense': plays.append(play({'type': 'set_monster', 'tributes': ids(ms)}, 'Colocado con Tributo', ms))
        return plays

    def _revive(self, p, pos, base):
        """The same card is in its player's Graveyard: it may have come back (followed now as a new track)."""
        card_id = base.get('card_id') or self.cards.get(base.get('copy_id'))
        grave = self.duel.state['players'][p['player']]['graveyard']
        old = next((c for c in reversed(grave) if card_id and c.get('card_id') == card_id), None)
        if old is None: return []
        return [({**base, 'type': 'special_summon', 'position': pos if pos in ('attack', 'defense') else 'attack', 'source': 'graveyard',
                  'from_copy': old['copy_id']}, 'Invocación Especial desde el Cementerio')]

    def _needs_materials(self, p):
        """A face-up monster that is normally summoned with materials (Extra Deck, Level 5+) and has none
        to use yet: wait a moment for them to leave the field before deciding."""
        if p.get('kind') != 'unexplained' or family(p['zone']) != 'monster' or p.get('position') not in ('attack', 'defense'): return False
        facts = self._facts(p); line, level = facts.get('line') or '', facts.get('level')
        if not (any(w in line for w in EXTRA_DECK_WORDS) or (level or 0) >= 5): return False
        return not self._material_pool(p['player'])[0]

    def _rollback(self, length):
        while len(self.duel.log) > length: self.duel.undo()

    def _to_main_phase(self, player):
        """Placing a card during your own Draw or Standby Phase means you are in your Main Phase:
        draw (the physical card is already in hand) and advance, as a player would."""
        st = self.duel.state
        if st['current'] != player: return
        while st['phase'] in ('draw', 'standby'):
            if st['phase'] == 'draw' and st['turn'] > 1 and not st['turn_flags']['drew']: self.duel.draw(player)
            self.duel.next_phase(); st = self.duel.state

    def _auto_play(self, pending):
        import time
        facts = self._facts(pending); plays = self._plays(pending)
        # The card that was in the zone, before the play moves it (its name after a restart,
        # when the track's card_id is no longer known).
        was = self._model_card(pending['player'], pending['zone']) if pending.get('kind') == 'missing' else None
        was_name = (was or {}).get('name') or ('carta boca abajo' if (was or {}).get('position') in ('facedown', 'facedown_defense') else None)
        def attempt(n, allow_warnings):
            """Apply play n; None if the engine refuses it (or, first pass, only accepts it with warnings)."""
            event = dict(plays[n][0]); reclaim = event.pop('_reclaim', []); used = event.pop('_with', None)
            saved = list(self.duel.log); start = len(saved)
            try:
                if reclaim:
                    # The materials had already gone to the Graveyard on their own: undo those plays and
                    # repeat the camera observations since, so the materials are back on the field.
                    first = min(r['start'] for r in reclaim)
                    self._rollback(first)
                    for e in saved[first:]:
                        if e['type'] == 'observe': self.duel.apply({'type': 'observe', **e['params']})
                    start = len(self.duel.log)
                if event['type'] in SUMMON_EVENTS: self._to_main_phase(event['player'])
                self.act(event, record=False)
            except DuelError:
                self.duel = Duel.replay(saved); return None
            warnings = [w for e in self.duel.log[start:] for w in e.get('warnings', [])]
            if warnings and not allow_warnings: self.duel = Duel.replay(saved); return None
            return event, reclaim, used, start, warnings
        # Notary mode accepts almost anything with a warning: prefer the first play that breaks no rule
        # (a second Normal Summon is more likely a Special Summon), then the first one at all.
        done = None
        for allow in (False, True):
            for n in range(len(plays)):
                done = attempt(n, allow)
                if done: break
            if done: break
        if done:
            event, reclaim, used, start, warnings = done; label = plays[n][1]
            self.recent = [r for r in self.recent if r not in reclaim]
            name = facts.get('name') or was_name or 'carta'
            options = ACTIONS.get((pending.get('kind'), family(pending['zone']))) or ACTIONS.get((pending.get('kind'), 'any')) or []
            if pending['zone'].startswith('extra_monster:') or any(w in (facts.get('line') or '') for w in EXTRA_DECK_WORDS):
                options = [o for o in options if o[0] == 'special_summon']
            # Other summons that fit (with their materials, or from the Graveyard), then the plain answers.
            special = lambda e: e.get('materials') or e.get('tributes') or e.get('source') in ('graveyard', 'banished')
            others = [(e, l) for i, (e, l) in enumerate(plays) if i != n and (reclaim or not e.get('_reclaim')) and special(e)]
            alternatives = [{'type': f'play:{i}', 'label': l + (f" con {e['_with']}" if e.get('_with') else '')} for i, (e, l) in enumerate(others)]
            alternatives += [{'type': t, 'label': l} for t, l in options if t != event['type'] or special(event)]
            card_id = pending.get('card_id') or self.cards.get(pending.get('copy_id')) or self.cards.get(pending.get('expected_copy'))
            self.recent.insert(0, {'id': f'{start}-{len(self.duel.log)}', 'start': start, 'end': len(self.duel.log), 'time': time.monotonic(),
                                   'card_id': card_id, 'text': f"{label}: {name}{f' con {used}' if used else ''} ({zone_label(pending['zone'])}, {self.duel.state['players'][pending['player']]['name']})",
                                   'pending': pending, 'event': event, 'materials': event.get('materials') or event.get('tributes') or [],
                                   'plays': [{k: v for k, v in e.items() if k not in ('_reclaim', '_with')} for e, _ in others], 'alternatives': alternatives,
                                   'warnings': warnings})
            del self.recent[8:]
            self._save()
            return True
        return False

    def revise(self, play_id, replacement=None):
        """Undo an automatic play (everything logged since it) and apply `replacement` instead."""
        with self.lock:
            play = next((r for r in self.recent if r['id'] == play_id), None)
            if play is None: raise ValueError('Esa jugada ya no se puede cambiar')
            later = [r for r in self.recent if r['start'] > play['start']]
            if later: raise ValueError('Hay jugadas posteriores: cámbialas primero o usa Deshacer')
            saved = list(self.duel.log); self._rollback(play['start']); self.recent.remove(play)
            if replacement:
                p = play['pending']
                if replacement.startswith('play:'):
                    event = dict(play['plays'][int(replacement[5:])])   # another summon that fit, with its materials
                else:
                    event = {'type': replacement, 'player': p['player']}
                    if p.get('kind') == 'missing': event['copy_id'] = p['expected_copy']
                    elif replacement in ('change_position', 'flip'): event.update(copy_id=p['copy_id'], position=p.get('position'))
                    else: event.update(zone=p['zone'], copy_id=p.get('copy_id'), card_id=p.get('card_id'))
                    if replacement == 'special_summon':
                        event['position'] = p['position'] if p.get('position') in ('attack', 'defense') else 'attack'
                        if any(w in (self._facts(p).get('line') or '') for w in EXTRA_DECK_WORDS): event['source'] = 'extra_deck'
                unused = [m for m in play.get('materials') or [] if m not in (event.get('materials') or event.get('tributes') or [])]
                try:
                    # The camera saw them leave the field: without the materials role they went to the Graveyard.
                    for copy_id in unused: self.duel.send_to_graveyard(p['player'], copy_id=copy_id)
                    if event['type'] in SUMMON_EVENTS: self._to_main_phase(p['player'])
                    self.act(event, record=False)
                except DuelError:
                    self.duel = Duel.replay(saved); self.recent.append(play); self.recent.sort(key=lambda r: -r['start']); raise
            else:
                # Undone: the materials are back on the field, unseen, and may go to the Graveyard on their own again.
                unused = set(play.get('materials') or [])
                self.tried = {k for k in self.tried if not (k[1] == 'missing' and k[3] in unused)}
            self.observed.clear(); self._save()
            return {'revised': play_id}

    def goto_phase(self, target):
        """Jump to a phase of the current turn, as the phase buttons of Master Duel do."""
        with self.lock:
            if target not in PHASE_ORDER: raise ValueError(f'Fase desconocida: {target!r}')
            if self.duel.state['turn'] == 1 and target in ('battle', 'main2'):
                raise DuelError('En el primer turno no hay Battle Phase ni Main Phase 2')
            start = len(self.duel.log)
            try:
                for _ in range(12):
                    st = self.duel.state
                    if st['phase'] == target: break
                    if PHASE_ORDER.index(target) < PHASE_ORDER.index(st['phase']): raise DuelError('No se puede volver a una fase anterior')
                    if st['phase'] == 'draw' and st['turn'] > 1 and not st['turn_flags']['drew']: self.duel.draw(st['current'])
                    self.duel.next_phase(skip_battle=target == 'end' and st['phase'] == 'main1')
            except DuelError:
                self._rollback(start); raise
            self._save()
            return {'phase': self.duel.state['phase']}

    # --- battle -----------------------------------------------------------------
    def attack(self, attacker, target=None):
        """Declare an attack (click on the video or the carry-and-return gesture), moving to
        the Battle Step first if needed. Nothing is applied: `battle_preview` shows the result
        and the players confirm with resolve_battle, or cancel it."""
        with self.lock:
            start = len(self.duel.log); st = self.duel.state
            try:
                if st['phase'] != 'battle': self.goto_phase('battle')
                if self.duel.state['battle_step'] == 'start': self.duel.next_phase()
                self.duel.declare_attack(self.duel.state['current'], attacker, target)
            except DuelError:
                self._rollback(start); raise
            self.attack_start = start; self._save()
            return {'attacker': attacker, 'target': target}

    def cancel_attack(self):
        """Take back a declared attack (an effect stopped it, or it was a mistake)."""
        with self.lock:
            if not self.duel.state['pending_attack']: raise DuelError('No hay ataque declarado')
            self._rollback(getattr(self, 'attack_start', len(self.duel.log) - 1)); self._save()
            return {'cancelled': True}

    def battle_preview(self):
        """What resolving the declared attack would do, computed on a copy of the duel."""
        st = self.duel.state; pa = st['pending_attack']
        if not pa: return None
        def card(copy_id):
            for p in st['players']:
                for c in p['monster']:
                    if c and c['copy_id'] == copy_id: return c
            return next((c for c in st['shared']['extra_monster'] if c and c['copy_id'] == copy_id), None)
        a, t = card(pa['attacker']), card(pa['target']) if pa['target'] is not None else None
        names = [p['name'] for p in st['players']]
        stats = lambda c: f"ATK {c['atk']}" if c['position'] == 'attack' else f"DEF {c['def'] if c['def'] is not None else '?'}"
        text = f"{a['name'] or 'Monstruo'} (ATK {a['atk']}) ataca " + (f"a {t['name'] or 'un monstruo boca abajo'} ({stats(t)})" if t else 'directamente')
        try:
            result = Duel.replay(self.duel.log).resolve_battle()
        except DuelError as error:
            return {'text': text, 'outcome': None, 'problem': str(error)}
        parts = []
        for copy_id in result['destroyed']:
            c = card(copy_id); parts.append(f"{(c or {}).get('name') or 'monstruo'} es destruido")
        for change in result['lp_changes']:
            parts.append(f"{names[change['player']]} {'pierde' if change['delta'] < 0 else 'gana'} {abs(change['delta'])} LP")
        if not parts: parts.append('sin daño ni destrucción')
        return {'text': text, 'outcome': '; '.join(parts), 'problem': None}

    def _gesture(self, tracks):
        """Battle Phase: a monster carried next to an opponent's monster and brought back to its
        zone declares that attack. Returns copy_ids in the middle of a gesture."""
        import time
        st = self.duel.state
        if not st['started'] or st['result'] or st['phase'] != 'battle' or st['pending_attack'] or not self.mats:
            self.gestures = {}; return set()
        now = time.monotonic(); me = st['current']
        center = {t['track_id']: np.float32(t['corners']).mean(0) for t in tracks}
        def home(player, zone):
            mat = next((m for m in self.mats if m.player == (0 if zone.startswith('extra_monster') else player)), None)
            rect = next((z for z in (mat.layout if mat else []) if z[0] == zone), None)
            if rect is None: return None, None
            _, x0, y0, x1, y1 = rect; pts = mat.image_points([[x0, (y0 + y1) / 2], [x1, (y0 + y1) / 2], [(x0 + x1) / 2, (y0 + y1) / 2]])
            return pts[2], float(np.linalg.norm(pts[1] - pts[0]))
        board = [(p, f'{k}:{i}', c) for p, ps in enumerate(st['players']) for k in ('monster',) for i, c in enumerate(ps[k]) if c]
        board += [(c['controller'], f'extra_monster:{i}', c) for i, c in enumerate(st['shared']['extra_monster']) if c]
        enemies = [(c['copy_id'], center.get(c['copy_id'], home(p, zone)[0])) for p, zone, c in board if p != me]
        for p, zone, c in board:
            copy = c['copy_id']
            if p != me or c['position'] != 'attack' or c.get('attacked_turn') == st['turn'] or copy not in center: continue
            base, size = home(p, zone)
            if base is None: continue
            here = center[copy]; away = float(np.linalg.norm(here - base)); gesture = self.gestures.get(copy)
            near = [(float(np.linalg.norm(here - pos)), tid) for tid, pos in enemies if pos is not None and float(np.linalg.norm(here - pos)) < .6 * size]
            if near and away > .6 * size:
                self.gestures[copy] = {'target': min(near)[1], 'at': now}
            elif gesture and away < .35 * size:
                del self.gestures[copy]
                if now - gesture['at'] < 8:
                    try: self.attack(copy, gesture['target'])
                    except DuelError: pass
        self.gestures = {k: g for k, g in self.gestures.items() if now - g['at'] < 8}
        return set(self.gestures)

    def end_turn(self):
        """End the turn from any phase: advance to a phase where the rules allow it first."""
        with self.lock:
            start = len(self.duel.log)
            try:
                st = self.duel.state
                if st['phase'] in ('draw', 'standby'): self.goto_phase('main1')
                elif st['phase'] == 'battle': self.goto_phase('main2')
                self.duel.end_turn()
            except DuelError:
                self._rollback(start); raise
            self._save()
            return {'turn': self.duel.state['turn']}

    # --- players ---------------------------------------------------------------
    def card_spec(self, copy_id, card_id=None):
        card_id = card_id or self.cards.get(copy_id)
        spec = {'copy_id': copy_id, 'card_id': card_id}
        facts = self.sheet(card_id) if self.sheet and card_id else None
        if facts:
            spec.update(name=facts['name'], type=facts.get('line'))
            for k in ('atk', 'def', 'level'):
                if isinstance(facts.get(k), int) and facts[k] >= 0: spec[k] = facts[k]
            if facts.get('rank') is not None: spec['level'] = facts['rank']
        return spec

    def act(self, event, record=True):
        """A player's decision. Camera-answer events carry `copy_id` (and `card_id`);
        the card description is completed from the registry here. Also the panel's own
        actions: goto_phase, end_turn, revise (change or undo an automatic play), auto."""
        with self.lock:
            event = dict(event); kind = event.get('type')
            # Players decide and resolve: new duels record rule breaks as warnings (duel_engine notary mode).
            if kind == 'start_duel': event.setdefault('rules', 'notary')
            if kind == 'goto_phase': return self.goto_phase(event.get('phase'))
            if kind == 'end_turn': return self.end_turn()
            if kind == 'revise': return self.revise(event.get('id'), event.get('replacement'))
            if kind == 'auto': self.auto = bool(event.get('enabled')); return {'auto': self.auto}
            if kind == 'attack': return self.attack(event.get('attacker'), event.get('target'))
            if kind == 'cancel_attack': return self.cancel_attack()
            if kind in ('normal_summon', 'set_monster', 'special_summon', 'set_spell_trap') or (kind == 'activate_spell_trap' and event.get('copy_id') is not None and 'card' not in event and 'reveal' not in event):
                spec = self.card_spec(event.pop('copy_id'), event.pop('card_id', None))
                if kind in ('set_monster', 'set_spell_trap'): spec['card_id'] = None  # face-down: identity stays hidden
                event['card'] = spec
            if kind == 'reset':
                archived = self.archive()
                self.duel = Duel(); self.observed.clear(); self.missing.clear(); self.recent.clear(); self.tried.clear(); self._save(); return {'reset': True, 'archived': archived}
            if kind == 'undo':
                self.duel.undo(); self.observed.clear()
                self.recent = [r for r in self.recent if r['start'] < len(self.duel.log)]
                self._save(); return {'undone': True}
            result = self.duel.apply(event)
            if kind == 'start_duel': self.observed.clear()
            else:
                # Re-observe the zones the answer touched, so their questions clear at once.
                # (kept as seen, so the card leaving before it is seen again still counts as missing).
                for key, signature in list(self.observed.items()):
                    if signature is not None and key[1] == event.get('zone'): self.observed[key] = ('resend',)
            self._save()
            return result

    def archive(self):
        """Keep a finished or abandoned duel in history/ before starting another (full log, replayable)."""
        import time
        st = self.duel.state
        if not st['started']: return None
        names = [p['name'] for p in st['players']]
        stamp = time.strftime('%Y%m%d-%H%M%S')
        path = self.folder / 'history' / f'{stamp}.json'; path.parent.mkdir(parents=True, exist_ok=True)
        winner = st['result']['winner'] if st['result'] else None
        path.write_text(json.dumps({'saved_at': time.strftime('%Y-%m-%dT%H:%M:%S'), 'players': names, 'winner': winner,
                                    'reason': (st['result'] or {}).get('reason'), 'turns': st['turn'], 'lp': [p['lp'] for p in st['players']],
                                    'events': len(self.duel.log), 'log': self.duel.log}, ensure_ascii=False), encoding='utf-8')
        return path.name

    def history(self, limit=20):
        """Most recent archived duels, newest first (summary only)."""
        folder = self.folder / 'history'
        if not folder.exists(): return []
        out = []
        for path in sorted(folder.glob('*.json'), reverse=True)[:limit]:
            try: data = json.loads(path.read_text(encoding='utf-8'))
            except ValueError: continue
            out.append({k: data.get(k) for k in ('saved_at', 'players', 'winner', 'reason', 'turns', 'lp', 'events')} | {'file': path.name})
        return out

    def _save(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.folder / 'duel.json.tmp'
        tmp.write_text(self.duel.to_json(), encoding='utf-8'); tmp.replace(self.folder / 'duel.json')

    def view(self):
        """Duel state for the panel: players, turn, phase, board and open questions with their answers."""
        with self.lock:
            st = self.duel.snapshot()
            questions = []
            for p in st['pending']:
                fam = family(p['zone'])
                options = ACTIONS.get((p.get('kind'), fam)) or ACTIONS.get((p.get('kind'), 'any')) or []
                card_id = p.get('card_id') or self.cards.get(p.get('copy_id'))
                facts = self.sheet(card_id) if self.sheet and card_id else None
                hint = None
                # Extra Monster Zones are reached only by Special Summon (Link, Fusion, Synchro, Xyz...).
                if p['zone'].startswith('extra_monster:'):
                    options = [o for o in options if o[0] == 'special_summon']
                # The engine checks structure, not card types: a monster (other than a Pendulum
                # Scale) in a Spell & Trap Zone, or a Spell/Trap in a Monster Zone, is almost
                # always a stale calibration or a misplaced card, so no answer is offered.
                if facts and p.get('kind') == 'unexplained':
                    kind = facts.get('card_type')
                    if fam == 'spell' and kind == 'monster' and 'Péndulo' not in (facts.get('line') or ''):
                        options, hint = [], 'Un monstruo en una Zona de Magia/Trampa: revisa que la carta esté en su zona o vuelve a calibrar el tapete.'
                    elif fam == 'monster' and kind in ('spell', 'trap'):
                        options, hint = [], 'Una Magia/Trampa en una Zona de Monstruo: revisa que la carta esté en su zona o vuelve a calibrar el tapete.'
                questions.append({**p, 'zone_label': zone_label(p['zone']), 'card_name': facts['name'] if facts else None, 'hint': hint,
                                  'level': (facts or {}).get('level'), 'options': [{'type': t, 'label': l} for t, l in options]})
            board = []
            for i, ps in enumerate(st['players']):
                for kind in ('monster', 'spell'):
                    for j, c in enumerate(ps[kind]):
                        if c: board.append({'player': i, 'zone': f'{kind}:{j}', 'zone_label': zone_label(f'{kind}:{j}'), **c})
                if ps['field'][0]: board.append({'player': i, 'zone': 'field', 'zone_label': zone_label('field'), **ps['field'][0]})
            for j, c in enumerate(st['shared']['extra_monster']):
                if c: board.append({'player': c['controller'], 'zone': f'extra_monster:{j}', 'zone_label': zone_label(f'extra_monster:{j}'), **c})
            pile = lambda cards: [{'copy_id': c.get('copy_id'), 'card_id': c.get('card_id'), 'name': c.get('name')} for c in cards]
            players = [{k: ps[k] for k in ('name', 'lp', 'hand', 'deck', 'extra_deck')} | {'graveyard': len(ps['graveyard']), 'banished': len(ps['banished']),
                        'graveyard_cards': pile(ps['graveyard']), 'banished_cards': pile(ps['banished'])} for ps in st['players']]
            return {'started': st['started'], 'turn': st['turn'], 'current': st['current'], 'phase': st['phase'], 'battle_step': st['battle_step'],
                    'result': st['result'], 'players': players, 'board': board, 'questions': questions, 'pending_attack': st['pending_attack'],
                    'calibrated': self.mode is not None, 'mode': self.mode, 'mats_seen': [m.player for m in self.mats], 'events': len(self.duel.log),
                    'auto': self.auto, 'recent': [{k: r.get(k) for k in ('id', 'text', 'alternatives', 'card_id', 'warnings')} for r in self.recent],
                    'battle_preview': self.battle_preview(), 'carrying': sorted(self.gestures), 'card_backs': self._backs_summary()}

    def _backs_summary(self):
        try:
            from card_backs import summary
            return summary()
        except (ImportError, OSError, ValueError): return None
