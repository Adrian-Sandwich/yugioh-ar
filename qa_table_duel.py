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
          'kuriboh': {'name': 'Kuriboh', 'card_type': 'monster', 'line': 'Monstruo Efecto', 'atk': 300, 'def': 200, 'level': 1}}


def track(table, player, track_id, card_id, cx, cy, sideways=False):
    mat = next(m for m in table.mats if m.player == player)
    return {'track_id': track_id, 'card_id': card_id, 'corners': mat.image_points(card_in_mat(cx, cy, sideways)).tolist()}


def feed(table, tracks, times=3):
    for _ in range(times): table.feed(tracks)


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
        assert any(c['name'] == 'Mago Oscuro' for c in auto.view()['board'])
        play = auto.view()['recent'][0]; assert play['text'].startswith('Invocación Especial: Mago Oscuro'), play
        auto.act({'type': 'revise', 'id': play['id']})
        assert not any(c['name'] == 'Mago Oscuro' for c in auto.view()['board'])
        feed(auto, [k1, dm])   # undone play does not come back by itself: it waits as a question
        assert not any(c['name'] == 'Mago Oscuro' for c in auto.view()['board']) and any(q['zone'] == 'monster:3' for q in auto.view()['questions'])
        checks.append('Special Summon when the Normal Summon is used; undo keeps it as a question')
        # A hand over Kuriboh for a moment does not send it to the Graveyard.
        feed(auto, [dm])
        assert any(c['name'] == 'Kuriboh' for c in auto.view()['board'])
        auto.first_seen = {k: t - 5 for k, t in auto.first_seen.items()}; feed(auto, [dm], times=1)
        view = auto.view(); assert not any(c['name'] == 'Kuriboh' for c in view['board']) and view['players'][0]['graveyard'] == 1, view['board']
        checks.append('a card gone briefly stays; gone for 3 s goes to the Graveyard')
        assert [c['name'] for c in view['players'][0]['graveyard_cards']] == ['Kuriboh'], view['players'][0]
        assert view['recent'][0]['card_id'] == 'kuriboh', view['recent'][0]
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
        feed(battle, [kb, dm_home])
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
