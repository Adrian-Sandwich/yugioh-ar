"""Viewer duel: calibration, camera questions, player answers, deduplication, persistence."""
import json
import shutil
from pathlib import Path

from qa_playmat import card_in_mat
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
        table = TableDuel(folder, sheet=SHEETS.get)
        try: table.calibrate('two', [{'player': 0, 'corners': NEAR}], [1920, 1080]); raise AssertionError('two mats need both players')
        except ValueError: pass
        overlay = table.calibrate('two', [{'player': 0, 'corners': NEAR}, {'player': 1, 'corners': FAR}], [1920, 1080])
            # 16 zones per mat (4 piles, 5 + 5 zones, 2 Extra Monster Zones); the shared two are drawn once.
        assert len(overlay['zones']) == 16 + 14 and overlay['mode'] == 'two', len(overlay['zones'])
        checks.append('calibration validated; zone outlines for both mats')
        # Before the duel starts, cards on the table are not sent to the engine.
        kuriboh = track(table, 0, 1, 'kuriboh', 2.5 / 7, .25)
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
        feed(table, [track(table, 0, 1, 'kuriboh', 2.5 / 7, .25, sideways=True)])
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
        # A monster seen in a Spell & Trap Zone gets no answers, only a hint to check the mat.
        feed(table, [track(table, 0, 3, 'dm', 3.5 / 7, .75)])
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
