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

from duel_engine import Duel, DuelError
from playmat import Mat, ZoneTracker, tcg_layout

ROOT = Path(__file__).resolve().parent
FOLDER = ROOT / 'data/playmat'
MODES = {'two': 'Dos tapetes frente a frente', 'one': 'Un tapete'}
ZONE_NAMES = {'field': 'Zona de Campo', 'graveyard': 'Cementerio', 'extra_deck': 'Mazo Extra', 'deck': 'Mazo'}
# Answers a player can give to each kind of discrepancy, per zone family.
ACTIONS = {
    ('unexplained', 'monster'): [('normal_summon', 'Invocación Normal'), ('special_summon', 'Invocación Especial'), ('set_monster', 'Colocada boca abajo')],
    ('unexplained', 'spell'): [('activate_spell_trap', 'Activada'), ('set_spell_trap', 'Colocada boca abajo')],
    ('missing', 'any'): [('send_to_graveyard', 'Al Cementerio'), ('banish', 'Desterrada'), ('return_to_hand', 'A la mano')],
    ('conflict', 'monster'): [('change_position', 'Cambio de posición'), ('flip', 'Volteada (Invocación por Volteo)')],
}


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
        self.mode = None; self.mats = []; self.image_size = None; self.tracker = None
        self.duel = Duel(); self.observed = {}; self.cards = {}; self.missing = {}
        calibration = self.folder / 'calibration.json'
        if calibration.exists():
            data = json.loads(calibration.read_text(encoding='utf-8'))
            self._set_mats(data['mode'], data['mats'], data.get('image_size'))
        saved = self.folder / 'duel.json'
        if saved.exists():
            try: self.duel = Duel.replay(json.loads(saved.read_text(encoding='utf-8'))['log'])
            except (DuelError, KeyError, ValueError): self.duel = Duel()  # unreadable: start clean, keep the file for inspection

    # --- calibration -----------------------------------------------------------
    def _set_mats(self, mode, mats, image_size):
        if mode not in MODES: raise ValueError(f'Modo desconocido: {mode!r}')
        players = sorted(m['player'] for m in mats)
        if players != ([0, 1] if mode == 'two' else [0]):
            raise ValueError('Dos tapetes: un tapete por jugador (0 y 1). Un tapete: sólo el jugador 0.')
        self.mats = [Mat(m['player'], m['corners']) for m in mats]
        self.mode = mode; self.image_size = image_size
        self.tracker = ZoneTracker(self.mats, stable=self.stable); self.observed.clear(); self.missing.clear()

    def calibrate(self, mode, mats, image_size):
        with self.lock:
            self._set_mats(mode, mats, image_size)
            self.folder.mkdir(parents=True, exist_ok=True)
            (self.folder / 'calibration.json').write_text(json.dumps({'mode': mode, 'image_size': image_size, 'layout': 'tcg-single',
                'mats': [{'player': m.player, 'corners': m.corners.tolist()} for m in self.mats]}, indent=2), encoding='utf-8')
            return self.overlay()

    def overlay(self):
        """Zone outlines in image pixels, for drawing over the video."""
        with self.lock:
            zones = []
            for mat in self.mats:
                for name, x0, y0, x1, y1 in tcg_layout():
                    if name.startswith('extra_monster') and mat.player != 0: continue  # shared: drawn once
                    zones.append({'player': mat.player, 'zone': name, 'label': zone_label(name),
                                  'polygon': mat.image_points([[x0, y0], [x1, y0], [x1, y1], [x0, y1]]).round(1).tolist()})
            return {'mode': self.mode, 'modes': MODES, 'image_size': self.image_size, 'zones': zones,
                    'mats': [{'player': m.player, 'corners': m.corners.tolist()} for m in self.mats]}

    # --- camera ----------------------------------------------------------------
    def feed(self, tracks):
        """Stable zone readings from this analysis; only changes are sent to the engine."""
        with self.lock:
            if self.tracker is None: return []
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
            return observations

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

    def act(self, event):
        """A player's decision. Camera-answer events carry `copy_id` (and `card_id`);
        the card description is completed from the registry here."""
        with self.lock:
            event = dict(event); kind = event.get('type')
            if kind in ('normal_summon', 'set_monster', 'special_summon', 'set_spell_trap') or (kind == 'activate_spell_trap' and event.get('copy_id') is not None and 'card' not in event):
                spec = self.card_spec(event.pop('copy_id'), event.pop('card_id', None))
                if kind in ('set_monster', 'set_spell_trap'): spec['card_id'] = None  # face-down: identity stays hidden
                event['card'] = spec
            if kind == 'reset':
                self.duel = Duel(); self.observed.clear(); self.missing.clear(); self._save(); return {'reset': True}
            if kind == 'undo':
                self.duel.undo(); self.observed.clear(); self._save(); return {'undone': True}
            result = self.duel.apply(event)
            if kind == 'start_duel': self.observed.clear()
            else:
                # Re-observe the zones the answer touched, so their questions clear at once.
                for key, signature in list(self.observed.items()):
                    if signature is not None and key[1] == event.get('zone'): del self.observed[key]
            self._save()
            return result

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
            players = [{k: ps[k] for k in ('name', 'lp', 'hand', 'deck', 'extra_deck')} | {'graveyard': len(ps['graveyard']), 'banished': len(ps['banished'])} for ps in st['players']]
            return {'started': st['started'], 'turn': st['turn'], 'current': st['current'], 'phase': st['phase'], 'battle_step': st['battle_step'],
                    'result': st['result'], 'players': players, 'board': board, 'questions': questions, 'pending_attack': st['pending_attack'],
                    'calibrated': bool(self.mats), 'mode': self.mode, 'events': len(self.duel.log)}
