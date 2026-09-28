"""Viewer duel: calibration, camera questions, player answers, deduplication, persistence."""
import json
import numpy as np
import shutil
from pathlib import Path

from qa_playmat import card_in_mat, center
from table_duel import TableDuel

ROOT = Path(__file__).resolve().parent
NEAR = [[420, 610], [1500, 610], [1640, 1020], [280, 1020]]
FAR = [[1430, 470], [490, 470], [560, 170], [1360, 170]]
SHEETS = {'dm': {'name': 'Mago Oscuro', 'card_type': 'monster', 'line': 'Monstruo Normal', 'atk': 2500, 'def': 2100, 'level': 7},
          'kuriboh': {'name': 'Kuriboh', 'card_type': 'monster', 'line': 'Monstruo Efecto', 'atk': 300, 'def': 200, 'level': 1},
          'pot': {'name': 'Olla de la Codicia', 'card_type': 'spell', 'line': 'Magia Normal'},
          'tuner': {'name': 'Sincronón', 'card_type': 'monster', 'line': 'Monstruo Cantante / Efecto · Máquina · Nivel 2', 'atk': 500, 'def': 500, 'level': 2},
          'warrior': {'name': 'Guerrero', 'card_type': 'monster', 'line': 'Monstruo Normal · Guerrero · Nivel 4', 'atk': 1800, 'def': 1000, 'level': 4},
          'soldier': {'name': 'Soldado', 'card_type': 'monster', 'line': 'Monstruo Normal · Guerrero · Nivel 4', 'atk': 1600, 'def': 1200, 'level': 4},
          'synchro': {'name': 'Dragón Sincro', 'card_type': 'monster', 'line': 'Monstruo Sincronía / Efecto · Dragón · Nivel 6', 'atk': 2400, 'def': 2000, 'level': 6},
          'xyz': {'name': 'Caballero Xyz', 'card_type': 'monster', 'line': 'Monstruo Xyz / Efecto · Guerrero · Rango 4', 'atk': 2500, 'def': 1500, 'level': None, 'rank': 4}}


def track(table, player, track_id, card_id, cx, cy, sideways=False):
    mat = next(m for m in table.mats if m.player == player)
    return {'track_id': track_id, 'card_id': card_id, 'corners': mat.image_points(card_in_mat(cx, cy, sideways)).tolist()}


def feed(table, tracks, times=3):
    for _ in range(times): table.feed(tracks)


def settle(table, tracks):
    """As if MISSING_GRACE_S had passed since the current discrepancies were first seen."""
    table.first_seen = {k: t - 5 for k, t in table.first_seen.items()}; table.feed(tracks)


def main():
    folder = ROOT / 'research/qa/table-duel-tmp'
    shutil.rmtree(folder, ignore_errors=True)
    checks = []
    try:
        table = TableDuel(folder, sheet=SHEETS.get); table.auto = False   # question mode
        try: table.calibrate('two', [{'player': 0, 'corners': NEAR}], [1920, 1080]); raise AssertionError('two mats need both players')
        except ValueError: pass
        overlay = table.calibrate('two', [{'player': 0, 'corners': NEAR}, {'player': 1, 'corners': FAR}], [1920, 1080])
            # 17 zones per mat (5 piles, 5 + 5 zones, 2 Extra Monster Zones); the shared two are drawn once.
        assert len(overlay['zones']) == 17 + 15 and overlay['mode'] == 'two', len(overlay['zones'])
        checks.append('calibration validated; zone outlines for both mats')
        # Before the duel starts, cards on the table are not sent to the engine.
        kuriboh = track(table, 0, 1, 'kuriboh', *center('monster:1'))
        feed(table, [kuriboh]); assert table.duel.log == []
        table.act({'type': 'start_duel', 'names': ['Ana', 'Beto'], 'starting': 0})
        for _ in range(2): table.act({'type': 'next_phase'})          # draw -> standby -> main1
        assert table.view()['phase'] == 'main1', table.view()['phase']
        # Kuriboh appears in Main Monster Zone 2: one question, with the summon answers.
        feed(table, [kuriboh])
        view = table.view(); q = view['questions']
        assert len(q) == 1 and q[0]['kind'] == 'unexplained' and q[0]['zone'] == 'monster:1' and q[0]['card_name'] == 'Kuriboh', q
        assert [o['type'] for o in q[0]['options']] == ['normal_summon', 'special_summon', 'set_monster']
        checks.append('new card on the mat becomes a question with summon options')
        # Repeated identical sightings do not grow the duel log.
        events = len(table.duel.log); feed(table, [kuriboh], times=20); assert len(table.duel.log) == events
        checks.append('identical observations are not re-sent')
        # The player answers: the card enters with the registry's stats and the question clears.
        table.act({'type': 'normal_summon', 'player': 0, 'zone': 'monster:1', 'copy_id': 1})
        feed(table, [kuriboh])
        view = table.view(); card = next(c for c in view['board'] if c['zone'] == 'monster:1')
        assert card['name'] == 'Kuriboh' and card['atk'] == 300 and card['position'] == 'attack' and view['questions'] == [], view
        checks.append('answer summons with registry stats; question cleared by the next sighting')
        # Defense position seen on the mat but not declared: a position conflict with its answers.
        feed(table, [track(table, 0, 1, 'kuriboh', *center('monster:1'), sideways=True)])
        q = table.view()['questions']
        assert len(q) == 1 and q[0]['kind'] == 'conflict' and 'position' in q[0]['fields'] and q[0]['options'][0]['type'] == 'change_position', q
        feed(table, [kuriboh])  # back upright: consistent again
        assert table.view()['questions'] == []
        checks.append('position mismatch asks; back in place clears')
        # The card leaves: after three analyses without it the zone is observed empty.
        feed(table, [])
        q = table.view()['questions']
        assert len(q) == 1 and q[0]['kind'] == 'missing' and [o['type'] for o in q[0]['options']] == ['send_to_graveyard', 'banish', 'return_to_hand'], q
        table.act({'type': 'send_to_graveyard', 'player': 0, 'copy_id': 1})
        view = table.view(); assert view['players'][0]['graveyard'] == 1 and not any(c['zone'] == 'monster:1' for c in view['board'])
        checks.append('card leaving the zone asks; graveyard answer applied')
        # An Extra Monster Zone only offers Special Summon.
        feed(table, [kuriboh, track(table, 0, 4, 'dm', *center('extra_monster:0'))])
        q = [x for x in table.view()['questions'] if x['zone'] == 'extra_monster:0']
        assert len(q) == 1 and [o['type'] for o in q[0]['options']] == ['special_summon'], q
        feed(table, [kuriboh])
        checks.append('Extra Monster Zone: Special Summon only')
        # A monster seen in a Spell & Trap Zone gets no answers, only a hint to check the mat.
        feed(table, [track(table, 0, 3, 'dm', *center('spell:2'))])
        q = [x for x in table.view()['questions'] if x['zone'] == 'spell:2']
        assert len(q) == 1 and q[0]['options'] == [] and 'Magia/Trampa' in q[0]['hint'], q
        feed(table, [])
        checks.append('monster in a Spell & Trap Zone: no answers, a hint')
        # Invalid answers leave the duel untouched and say why.
        events = len(table.duel.log)
        try: table.act({'type': 'normal_summon', 'player': 0, 'zone': 'monster:3', 'copy_id': 5}); raise AssertionError('second normal summon accepted')
        except Exception as error: assert 'Normal' in str(error) or 'turno' in str(error), error
        assert len(table.duel.log) == events
        checks.append('invalid answer rejected with a reason, state unchanged')
        # Restart: calibration and duel come back from disk.
        again = TableDuel(folder, sheet=SHEETS.get)
        assert again.mode == 'two' and again.duel.state == table.duel.state and len(again.duel.log) == len(table.duel.log)
        checks.append('calibration and duel survive a restart')
        # Virtual boards from sliders: preview changes nothing; saving places both boards,
        # the far one smaller (one perspective for the whole table), and cards land in its zones.
        virtual = TableDuel(folder / 'virtual', sheet=SHEETS.get); virtual.auto = False
        preview = virtual.preview('two', {'tilt': .7}, [1920, 1080])
        assert preview['preview'] and len(preview['zones']) == 32 and virtual.mode is None
        virtual.calibrate('two', [], [1920, 1080], virtual={'tilt': .7})
        near_w = np.linalg.norm(virtual.mats[0].corners[1] - virtual.mats[0].corners[0]); far_w = np.linalg.norm(virtual.mats[1].corners[1] - virtual.mats[1].corners[0])
        assert far_w < near_w, (near_w, far_w)
        virtual.act({'type': 'start_duel'})
        feed(virtual, [track(virtual, player, 20 + player, 'kuriboh', *center(zone)) for player, zone in ((0, 'monster:2'), (1, 'spell:0'))])
        q = {(x['player'], x['zone']) for x in virtual.view()['questions']}
        assert (0, 'monster:2') in q and (1, 'spell:0') in q, q
        again = TableDuel(folder / 'virtual', sheet=SHEETS.get)
        assert again.virtual['tilt'] == .7 and again.mode == 'two'
        checks.append('virtual boards: preview, perspective, zones, sliders saved')
        # Automatic plays: placing a card is the obvious play, with the phase advanced for it.
        auto = TableDuel(folder / 'auto', sheet=SHEETS.get)
        auto.calibrate('two', [{'player': 0, 'corners': NEAR}, {'player': 1, 'corners': FAR}], [1920, 1080])
        auto.act({'type': 'start_duel', 'names': ['Ana', 'Beto'], 'starting': 0, 'extra_deck_sizes': [15, 15]})
        assert auto.view()['phase'] == 'draw'
        k1 = track(auto, 0, 1, 'kuriboh', *center('monster:1'))
        feed(auto, [k1])
        view = auto.view(); card = next((c for c in view['board'] if c['zone'] == 'monster:1'), None)
        assert card and card['name'] == 'Kuriboh' and view['phase'] == 'main1' and view['questions'] == [], view
        assert view['recent'][0]['text'].startswith('Invocación Normal: Kuriboh') and 'special_summon' in [a['type'] for a in view['recent'][0]['alternatives']]
        checks.append('card placed in Draw Phase: advanced to Main Phase 1 and Normal Summoned, no question')
        # Level 7 with the Normal Summon used: Special Summon; then changed to... undone.
        dm = track(auto, 0, 2, 'dm', *center('monster:3'))
        feed(auto, [k1, dm])
        # Level 7 with no tributes gone: it waits a moment for materials before deciding.
        assert not any(c['name'] == 'Mago Oscuro' for c in auto.view()['board'])
        settle(auto, [k1, dm])
        assert any(c['name'] == 'Mago Oscuro' for c in auto.view()['board'])
        play = auto.view()['recent'][0]; assert play['text'].startswith('Invocación Especial: Mago Oscuro'), play
        auto.act({'type': 'revise', 'id': play['id']})
        assert not any(c['name'] == 'Mago Oscuro' for c in auto.view()['board'])
        feed(auto, [k1, dm])   # undone play does not come back by itself: it waits as a question
        assert not any(c['name'] == 'Mago Oscuro' for c in auto.view()['board']) and any(q['zone'] == 'monster:3' for q in auto.view()['questions'])
        checks.append('Special Summon when the Normal Summon is used; undo keeps it as a question')
        # The tracker loses Kuriboh and finds it again as another track: same card, no question.
        k1 = track(auto, 0, 7, 'kuriboh', *center('monster:1'))
        events = len(auto.duel.log); feed(auto, [k1, dm])
        view = auto.view(); card = next(c for c in view['board'] if c['zone'] == 'monster:1')
        assert card['copy_id'] == 7 and not any(q['zone'] == 'monster:1' for q in view['questions']), (card, view['questions'])
        assert [e['type'] for e in auto.duel.log[events:]] == ['observe', 'retrack'], auto.duel.log[events:]
        checks.append('same card found again under a new track: followed silently (retrack)')
        # A hand over Kuriboh for a moment does not send it to the Graveyard.
        feed(auto, [dm])
        assert any(c['name'] == 'Kuriboh' for c in auto.view()['board'])
        auto.first_seen = {k: t - 5 for k, t in auto.first_seen.items()}; feed(auto, [dm], times=1)
        view = auto.view(); assert not any(c['name'] == 'Kuriboh' for c in view['board']) and view['players'][0]['graveyard'] == 1, view['board']
        checks.append('a card gone briefly stays; gone for 3 s goes to the Graveyard')
        assert [c['name'] for c in view['players'][0]['graveyard_cards']] == ['Kuriboh'], view['players'][0]
        assert view['recent'][0]['card_id'] == 'kuriboh' and view['recent'][0]['text'].startswith('Al Cementerio: Kuriboh'), view['recent'][0]
        checks.append('Graveyard contents with names; plays carry their card')
        # Phase buttons: jump to End Phase (turn 1 has no Battle Phase) and end the turn from anywhere.
        try: auto.act({'type': 'goto_phase', 'phase': 'battle'}); raise AssertionError('battle on turn 1')
        except Exception as error: assert 'primer turno' in str(error)
        auto.act({'type': 'goto_phase', 'phase': 'end'}); assert auto.view()['phase'] == 'end'
        auto.act({'type': 'end_turn'}); auto.act({'type': 'end_turn'})   # turn 2 ends from its Draw Phase
        assert auto.view()['turn'] == 3 and auto.view()['phase'] == 'draw'
        checks.append('phase jumps and End Turn from any phase')
        # Ending the duel keeps it in the history, replayable.
        result = auto.act({'type': 'reset'})
        history = auto.history()
        assert result['archived'] and len(history) == 1 and history[0]['players'] == ['Ana', 'Beto'] and history[0]['turns'] == 3, history
        saved = json.loads((folder / 'auto' / 'history' / history[0]['file']).read_text(encoding='utf-8'))
        from duel_engine import Duel
        assert Duel.replay(saved['log']).state['turn'] == 3 and not auto.duel.state['started']
        checks.append('reset archives the duel; the archived log replays')
        # Battle: carry-and-return gesture declares the attack; the result is proposed, not applied.
        battle = TableDuel(folder / 'battle', sheet=SHEETS.get)
        battle.calibrate('two', [{'player': 0, 'corners': NEAR}, {'player': 1, 'corners': FAR}], [1920, 1080])
        battle.act({'type': 'start_duel', 'names': ['Ana', 'Beto'], 'starting': 0})
        kb = track(battle, 0, 1, 'kuriboh', *center('monster:2'))
        feed(battle, [kb]); battle.act({'type': 'end_turn'})
        dm_home = track(battle, 1, 2, 'dm', *center('monster:2'))
        feed(battle, [kb, dm_home]); settle(battle, [kb, dm_home])
        assert {c['name'] for c in battle.view()['board']} == {'Kuriboh', 'Mago Oscuro'}, battle.view()['board']
        battle.act({'type': 'goto_phase', 'phase': 'battle'})
        kb_center = np.float32(kb['corners']).mean(0); dm_center = np.float32(dm_home['corners']).mean(0)
        dm_near = {**dm_home, 'corners': (np.float32(dm_home['corners']) + (kb_center - dm_center) * .9).tolist()}
        battle.feed([kb, dm_near]); assert battle.view()['carrying'] == [2] and not battle.duel.state['pending_attack']
        battle.feed([kb, dm_home])
        preview = battle.view()['battle_preview']
        assert preview and 'Mago Oscuro (ATK 2500) ataca a Kuriboh (ATK 300)' in preview['text'] and 'Kuriboh es destruido' in preview['outcome'] and 'Ana pierde 2200 LP' in preview['outcome'], preview
        assert battle.view()['players'][0]['lp'] == 8000, 'the result must not be applied before confirming'
        checks.append('carry-and-return gesture declares the attack; damage proposed, not applied')
        battle.act({'type': 'resolve_battle'})
        view = battle.view(); assert view['players'][0]['lp'] == 5800 and [c['name'] for c in view['players'][0]['graveyard_cards']] == ['Kuriboh'], view['players'][0]
        checks.append('confirming applies the proposed result')
        # A click-declared attack can be cancelled (an effect stopped it).
        kb2 = track(battle, 0, 3, 'kuriboh', *center('monster:0'))
        battle.duel.special_summon(0, {'copy_id': 3, 'card_id': 'kuriboh', 'name': 'Kuriboh', 'atk': 300, 'def': 200}, 'monster:0', source='hand')
        try: battle.act({'type': 'attack', 'attacker': 2, 'target': 3}); raise AssertionError('second attack of the same monster accepted')
        except Exception as error: assert 'ya atacó' in str(error), error
        checks.append('the engine refuses a second attack by the same monster')
        # Summons with materials, deduced from the monsters that just left the field.
        s = TableDuel(folder / 'summons', sheet=SHEETS.get)
        s.calibrate('two', [{'player': 0, 'corners': NEAR}, {'player': 1, 'corners': FAR}], [1920, 1080])
        s.act({'type': 'start_duel', 'names': ['Ana', 'Beto'], 'starting': 0, 'extra_deck_sizes': [15, 15]})
        at = lambda tid, card, zone, player=0: track(s, player, tid, card, *center(zone))
        names = lambda cards: sorted(c['name'] for c in cards)
        tuner, warrior = at(10, 'tuner', 'monster:0'), at(11, 'warrior', 'monster:1')
        feed(s, [tuner]); feed(s, [tuner, warrior])
        assert [r['text'].split(':')[0] for r in s.view()['recent'][:2]] == ['Invocación Especial', 'Invocación Normal']
        synchro = at(12, 'synchro', 'extra_monster:0')
        feed(s, [synchro])   # materials taken away and the Synchro placed at once
        view = s.view(); play = view['recent'][0]
        assert play['text'].startswith('Invocación Sincronía: Dragón Sincro con ') and 'Sincronón' in play['text'] and 'Guerrero' in play['text'], play
        assert names(view['players'][0]['graveyard_cards']) == ['Guerrero', 'Sincronón'] and view['questions'] == [], view
        assert s.duel.state['players'][0]['extra_deck'] == 14
        checks.append('Synchro Summon: Tuner + non-Tuner of the right Levels, materials to the Graveyard')
        s1, s2 = at(13, 'soldier', 'monster:2'), at(14, 'soldier', 'monster:3')
        feed(s, [synchro, s1]); feed(s, [synchro, s1, s2])
        feed(s, [synchro]); settle(s, [synchro])   # both gone long enough: sent to the Graveyard on their own
        assert names(s.view()['players'][0]['graveyard_cards']) == ['Guerrero', 'Sincronón', 'Soldado', 'Soldado']
        xyz = at(15, 'xyz', 'monster:2')
        feed(s, [synchro, xyz])
        view = s.view(); play = view['recent'][0]; card = next(c for c in s.duel.state['players'][0]['monster'] if c)
        assert play['text'].startswith('Invocación Xyz: Caballero Xyz con Soldado + Soldado'), play
        assert [a['label'] for a in play['alternatives']] == ['Invocación Especial'], play['alternatives']
        assert sorted(m['copy_id'] for m in card['materials']) == [13, 14] and names(view['players'][0]['graveyard_cards']) == ['Guerrero', 'Sincronón']
        assert not any(r['text'].startswith('Al Cementerio') for r in view['recent']), 'the Graveyard plays became the materials'
        checks.append('Xyz Summon from materials already sent to the Graveyard: those plays undone, materials attached')
        plain = next(a for a in play['alternatives'] if a['label'] == 'Invocación Especial')
        s.act({'type': 'revise', 'id': play['id'], 'replacement': plain['type']})
        card = next(c for c in s.duel.state['players'][0]['monster'] if c and c['copy_id'] == 15)
        assert not card.get('materials') and names(s.view()['players'][0]['graveyard_cards']) == ['Guerrero', 'Sincronón', 'Soldado', 'Soldado'], s.view()['players'][0]
        settle(s, [synchro, xyz]); assert s.view()['questions'] == [], s.view()['questions']
        checks.append('changed to a plain Special Summon: the unused materials go to the Graveyard')
        s.act({'type': 'end_turn'}); s.act({'type': 'end_turn'})
        dm = at(16, 'dm', 'monster:2')
        feed(s, [dm])   # Draw Phase of turn 3: the Synchro and the Xyz leave, Dark Magician on the Xyz's zone
        view = s.view(); play = view['recent'][0]
        assert play['text'].startswith('Invocación por Tributo: Mago Oscuro') and view['phase'] == 'main1', play
        assert {'Dragón Sincro', 'Caballero Xyz'} <= set(names(view['players'][0]['graveyard_cards'])) and view['questions'] == [], view
        checks.append('Tribute Summon on top of a tribute\'s zone, Level 7 with two tributes')
        again = at(30, 'tuner', 'monster:4')
        feed(s, [dm, again])
        view = s.view(); card = s.duel.state['players'][0]['monster'][4]
        assert view['recent'][0]['text'].startswith('Invocación Especial desde el Cementerio: Sincronón') and card['copy_id'] == 30, view['recent'][0]
        assert 'Sincronón' not in names(view['players'][0]['graveyard_cards'])
        checks.append('the same card seen again while in the Graveyard: revived from it, followed under its new track')
        # Face-down cards: card_backs reports zones with a back; the table follows them as tracks.
        f = TableDuel(folder / 'facedown', sheet=SHEETS.get)
        f.calibrate('two', [{'player': 0, 'corners': NEAR}, {'player': 1, 'corners': FAR}], [1920, 1080])
        assert f.back_zones() is None, 'no back checks before the duel starts'
        f.act({'type': 'start_duel', 'names': ['Ana', 'Beto'], 'starting': 0})
        zones = f.back_zones(); ids = {z['id'] for z in zones}
        assert len(zones) == 22 and '0|monster:0' in ids and '1|field' in ids and not any('extra_monster' in i or 'graveyard' in i for i in ids), sorted(ids)
        backs = lambda *zs: [{'id': z, 'score': .8} for z in zs]
        for _ in range(3): f.feed([], backs=backs('0|monster:0', '0|spell:1'))
        view = f.view(); down = {c['zone']: c for c in view['board']}
        assert down['monster:0']['position'] == 'facedown_defense' and down['spell:1']['position'] == 'facedown' and view['questions'] == [], view
        assert [r['text'].split(':')[0] for r in view['recent'][:2]] == ['Colocada boca abajo', 'Colocado boca abajo'], view['recent']
        checks.append('card backs in zones: face-down monster and set Spell/Trap')
        back_id = down['monster:0']['copy_id']
        for _ in range(4): f.feed([], backs=backs('0|spell:1'))          # a hand over the set monster
        assert any(q['kind'] == 'missing' for q in f.view()['questions'])
        for _ in range(3): f.feed([], backs=backs('0|monster:0', '0|spell:1'))
        view = f.view(); assert view['questions'] == [] and {c['copy_id'] for c in view['board']} >= {back_id}, view
        checks.append('a hand over a face-down card keeps it (same back id)')
        f.act({'type': 'end_turn'}); f.act({'type': 'end_turn'})
        face = track(f, 0, 40, 'kuriboh', *center('monster:0'))
        for _ in range(3): f.feed([face], backs=backs('0|spell:1'))
        view = f.view(); card = next(c for c in view['board'] if c['zone'] == 'monster:0')
        assert card['copy_id'] == 40 and card['name'] == 'Kuriboh' and card['position'] == 'attack' and view['phase'] == 'main1', card
        assert view['recent'][0]['text'].startswith('Invocación por Volteo: Kuriboh') and view['questions'] == [], view['recent'][0]
        checks.append('the back replaced by its face: Flip Summon, revealed, followed under the face\'s track')
        pot = track(f, 0, 41, 'pot', *center('spell:1'))
        for _ in range(3): f.feed([face, pot])
        view = f.view(); card = next(c for c in view['board'] if c['zone'] == 'spell:1')
        assert card['copy_id'] == 41 and card['name'] == 'Olla de la Codicia' and card['position'] == 'faceup' and view['recent'][0]['text'].startswith('Activada: Olla'), view['recent'][0]
        checks.append('a set Spell turned face-up: activated and revealed')
        # One-mat mode: player 0 only.
        solo = TableDuel(folder / 'solo', sheet=SHEETS.get)
        assert solo.calibrate('one', [{'player': 0, 'corners': NEAR}], [1920, 1080])['mode'] == 'one'
        try: solo.calibrate('one', [{'player': 1, 'corners': NEAR}], [1920, 1080]); raise AssertionError('one mat must be player 0')
        except ValueError: pass
        checks.append('one-mat mode')
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    print(json.dumps({'status': 'passed', 'checks': checks}, ensure_ascii=False))


if __name__ == '__main__':
    main()
