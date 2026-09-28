"""Duelo guionizado, acciones inválidas sin mutación, undo, JSON y conciliación con la cámara."""
import json
from pathlib import Path
from duel_engine import Duel,DuelError,EVENTS

ROOT=Path(__file__).resolve().parent
CHECKS=[]


def check(label):
    CHECKS.append(label)


def rejected(duel,event,fragment=None):
    """El evento debe fallar con DuelError y dejar estado y registro idénticos."""
    before=duel.snapshot();length=len(duel.log)
    try: duel.apply(event)
    except DuelError as error:
        assert fragment is None or fragment in str(error),(fragment,str(error))
    else: raise AssertionError(f'Se aceptó un evento inválido: {event}')
    assert duel.snapshot()==before and len(duel.log)==length,f'Un evento inválido mutó el estado: {event}'


def monster(copy_id,card_id,atk,defense,level=4,name=None):
    return {'copy_id':copy_id,'card_id':card_id,'name':name or card_id,'atk':atk,'def':defense,'level':level,'type':'monster'}


def to_main1(duel):
    duel.next_phase();duel.next_phase()
    assert duel.state['phase']=='main1'


def scripted_duel():
    d=Duel()
    rejected(d,{'type':'draw','player':0},'no ha empezado')
    d.start_duel(names=['Ana','Beto'],starting=0,deck_sizes=[10,10])
    st=d.state;assert st['turn']==1 and st['current']==0 and st['phase']=='draw'
    assert [p['hand'] for p in st['players']]==[5,5] and [p['deck'] for p in st['players']]==[5,5]
    assert [p['spell_zone_pendulum'] for p in st['players']]==[[True,False,False,False,True]]*2
    # Turno 1 (Ana): sin robo, sin Battle Phase.
    rejected(d,{'type':'draw','player':0},'primer turno')
    rejected(d,{'type':'normal_summon','player':0,'card':monster('t1','alpha',1700,1000),'zone':'monster:2'},'Main Phase')
    to_main1(d)
    rejected(d,{'type':'normal_summon','player':0,'card':monster('big','dragon',2500,2100,7),'zone':'monster:2'},'2 tributo')
    rejected(d,{'type':'normal_summon','player':1,'card':monster('t1','alpha',1700,1000),'zone':'monster:2'},'jugador del turno')
    rejected(d,{'type':'normal_summon','player':0,'card':monster('t1','alpha',1700,1000),'zone':'extra_monster:0'},'zona de monstruo principal')
    r=d.normal_summon(0,monster('t1','alpha',1700,1000),'monster:2')
    assert r['seq']==4 and d.state['players'][0]['monster'][2]['position']=='attack' and d.state['players'][0]['hand']==4
    rejected(d,{'type':'normal_summon','player':0,'card':monster('t9','beta',1000,1000),'zone':'monster:3'},'Ya se hizo la Invocación Normal')
    rejected(d,{'type':'special_summon','player':0,'card':monster('t1','alpha',1700,1000),'zone':'monster:3'},'ya está en')
    rejected(d,{'type':'change_position','player':0,'copy_id':'t1','position':'defense'},'turno en que se invocó')
    d.set_spell_trap(0,{'copy_id':'t2','type':'trap'},'spell:1')
    rejected(d,{'type':'activate_spell_trap','player':0,'copy_id':'t2'},'trampa no se activa el turno')
    d.next_phase();assert d.state['phase']=='end','El primer turno salta la Battle Phase'
    rejected(d,{'type':'declare_attack','player':0,'attacker':'t1'},'Battle Step')
    d.end_turn();assert (d.state['turn'],d.state['current'],d.state['phase'])==(2,1,'draw')
    check('turn 1: no draw, one normal summon, set trap, battle phase skipped')
    # Turno 2 (Beto): roba, coloca, invoca especial y ataca a un monstruo en ataque más fuerte.
    rejected(d,{'type':'next_phase'},'robar antes')
    assert d.draw(1)['deck']==4 and d.state['players'][1]['hand']==6
    rejected(d,{'type':'draw','player':1},'Ya se hizo el robo')
    to_main1(d)
    d.activate_spell_trap(0,copy_id='t2');assert d.state['players'][0]['spell'][1]['position']=='faceup'
    check('set trap activated on a later turn by its owner outside their turn')
    d.set_monster(1,{'copy_id':'t3'},'monster:2')
    fd=d.state['players'][1]['monster'][2];assert fd['position']=='facedown_defense' and fd['card_id'] is None and fd['def'] is None
    d.special_summon(1,monster('t4','gamma',1200,800,3),'monster:1')
    rejected(d,{'type':'flip','player':1,'copy_id':'t3'},'turno en que se colocó')
    d.next_phase();assert (d.state['phase'],d.state['battle_step'])==('battle','start')
    rejected(d,{'type':'declare_attack','player':1,'attacker':'t4','target':'t1'},'Battle Step')
    d.next_phase();assert d.state['battle_step']=='battle'
    rejected(d,{'type':'declare_attack','player':1,'attacker':'t3','target':'t1'},'posición de ataque')
    rejected(d,{'type':'declare_attack','player':1,'attacker':'t4'},'Ataque directo sólo')
    rejected(d,{'type':'resolve_battle'},'No hay ataque pendiente')
    d.declare_attack(1,'t4','t1');assert d.state['battle_step']=='damage'
    rejected(d,{'type':'next_phase'},'Resuelve el ataque')
    r=d.resolve_battle()
    assert r['outcome']=='attack_vs_attack' and r['destroyed']==['t4'] and d.state['players'][1]['lp']==7500,r
    assert [c['copy_id'] for c in d.state['players'][1]['graveyard']]==['t4'] and d.state['players'][1]['monster'][1] is None
    check('attack into a stronger attack-position monster: attacker destroyed, controller takes the difference')
    d.next_phase();d.next_phase();assert d.state['phase']=='main2'
    d.end_turn()
    # Turno 3 (Ana): ataca a un monstruo boca abajo (revelado al resolver) y luego ataca directamente.
    d.draw(0);to_main1(d)
    d.normal_summon(0,monster('t5','delta',2000,1500),'monster:0')
    d.change_position(0,'t1','defense');d.change_position  # cambia y no puede volver el mismo turno
    rejected(d,{'type':'change_position','player':0,'copy_id':'t1','position':'attack'},'ya cambió de posición')
    d.undo();assert d.state['players'][0]['monster'][2]['position']=='attack'
    check('undo restores the position change')
    d.next_phase();d.next_phase()
    d.declare_attack(0,'t1','t3')
    rejected(d,{'type':'resolve_battle'},'DEF desconocida')
    r=d.resolve_battle(reveal={'card_id':'wall','name':'Muro','atk':0,'def':1500})
    assert r['flipped']=='t3' and r['destroyed']==['t3'] and r['lp_changes']==[],r
    gy=d.state['players'][1]['graveyard'];assert gy[-1]['copy_id']=='t3' and gy[-1]['card_id']=='wall' and gy[-1]['def']==1500
    check('attack into a face-down defender: revealed at resolution, destroyed by ATK > DEF, no damage')
    rejected(d,{'type':'declare_attack','player':0,'attacker':'t1'},'ya atacó')
    r=d.declare_attack(0,'t5');assert r['direct'] is True
    r=d.resolve_battle();assert r['outcome']=='direct' and d.state['players'][1]['lp']==5500
    check('direct attack when the opponent controls no monsters')
    d.next_phase();d.next_phase();d.end_turn()
    # Turno 4 (Beto): revive desde el cementerio, pierde LP por efecto registrado y muere en batalla.
    d.draw(1);to_main1(d)
    r=d.special_summon(1,{'copy_id':'t4'},'monster:0',source='graveyard')
    revived=d.state['players'][1]['monster'][0];assert revived['atk']==1200 and revived['card_id']=='gamma' and not d.state['players'][1]['graveyard'][:0]
    assert [c['copy_id'] for c in d.state['players'][1]['graveyard']]==['t3']
    d.change_lp(1,-5000,'efecto registrado a mano');assert d.state['players'][1]['lp']==500
    d.next_phase();d.next_phase();d.declare_attack(1,'t4','t5');r=d.resolve_battle()
    assert r['destroyed']==['t4'] and d.state['players'][1]['lp']==-300
    assert d.finished() and d.state['result']=={'winner':0,'loser':1,'reason':'lp','turn':4},d.state['result']
    rejected(d,{'type':'next_phase'},'ha terminado')
    rejected(d,{'type':'change_lp','player':1,'delta':1000},'ha terminado')
    assert d.observe(0,'monster:0',copy_id='t5',card_id='delta',position='attack')['status']=='consistent'
    check('LP at or below zero ends the duel; only observations are accepted afterwards')
    return d


def json_roundtrip(d):
    text=d.to_json();copy_=Duel.from_json(text)
    assert copy_.snapshot()==d.snapshot() and copy_.log==d.log
    assert json.loads(json.dumps(d.snapshot()))==d.snapshot(),'El snapshot debe ser JSON puro'
    assert [e['seq'] for e in d.log]==list(range(1,len(d.log)+1))
    tampered=json.loads(text);tampered['state']['players'][0]['lp']=1
    try: Duel.from_json(json.dumps(tampered))
    except DuelError: pass
    else: raise AssertionError('Un estado guardado que no coincide con el registro debe rechazarse')
    check('JSON round trip, deterministic replay, monotonic sequence numbers, tampered state rejected')


def deck_out_and_surrender():
    d=Duel();d.start_duel(deck_sizes=[5,5])
    assert d.state['players'][1]['deck']==0
    to_main1(d);d.end_turn()
    r=d.draw(1);assert r['drawn']==0 and d.state['result']['reason']=='deck_out' and d.state['result']['winner']==0
    check('deck-out on draw loses the duel')
    d=Duel();d.start_duel();d.surrender(1);assert d.state['result']=={'winner':0,'loser':1,'reason':'surrender','turn':1}
    rejected(d,{'type':'surrender','player':0},'ha terminado')
    check('surrender')
    d=Duel();rejected(d,{'type':'start_duel','deck_sizes':[3,40]},'mano inicial')
    rejected(d,{'type':'start_duel','starting':2},'starting')
    d.start_duel();rejected(d,{'type':'start_duel'},'ya empezó')
    rejected(d,{'type':'unknown_event'},'desconocido')
    rejected(d,{'type':'draw','player':0,'bogus':1},'Parámetros inválidos')
    rejected(d,{'type':'change_lp','player':0,'delta':'x'},'entero')
    check('start_duel validation, unknown events and unknown parameters rejected')


def equal_attack_and_tributes():
    d=Duel();d.start_duel();to_main1(d)
    d.normal_summon(0,monster('a','x',1500,0),'monster:0');d.end_turn()
    d.draw(1);to_main1(d);d.normal_summon(1,monster('b','y',1500,0),'monster:4')
    d.next_phase();d.next_phase();d.declare_attack(1,'b','a');r=d.resolve_battle()
    assert sorted(r['destroyed'])==['a','b'] and [p['lp'] for p in d.state['players']]==[8000,8000]
    assert d.state['players'][0]['monster'][0] is None and d.state['players'][1]['monster'][4] is None
    check('equal ATK: both destroyed, no damage')
    d=Duel();d.start_duel(opening_hand=6);to_main1(d);d.special_summon(0,monster('s1','p',1000,1000),'monster:1')
    d.special_summon(0,monster('s2','q',1000,1000),'extra_monster:0',source='hand',position='defense')
    rejected(d,{'type':'normal_summon','player':0,'card':monster('big','dragon',2500,2100,7),'zone':'monster:1','tributes':['s1']},'requiere 2')
    rejected(d,{'type':'normal_summon','player':0,'card':monster('big','dragon',2500,2100,7),'zone':'monster:1','tributes':['s1','zz']},'no es un monstruo')
    r=d.normal_summon(0,monster('big','dragon',2500,2100,7),'monster:1',tributes=['s1','s2'])
    assert r['tributed']==['s1','s2'] and d.state['shared']['extra_monster'][0] is None
    assert sorted(c['copy_id'] for c in d.state['players'][0]['graveyard'])==['s1','s2'] and d.state['players'][0]['monster'][1]['copy_id']=='big'
    check('tribute summon frees the zone it lands on and uses the shared extra monster zone')
    d.set_spell_trap(0,{'copy_id':'f1','type':'spell'},'field')
    rejected(d,{'type':'activate_spell_trap','player':0,'card':{'copy_id':'f2'},'zone':'field'},'ocupada')
    d.activate_spell_trap(0,copy_id='f1');assert d.state['players'][0]['field'][0]['position']=='faceup'
    rejected(d,{'type':'activate_spell_trap','player':0,'card':{'copy_id':'pen','type':'monster'},'zone':'spell:1','as_pendulum':True},'zona péndulo')
    d.activate_spell_trap(0,{'copy_id':'pen','type':'monster'},zone='spell:0',as_pendulum=True)
    rejected(d,{'type':'activate_spell_trap','player':0,'card':{'copy_id':'tr','type':'trap'},'zone':'spell:2'},'se coloca boca abajo')
    d.send_to_graveyard(0,copy_id='pen');d.banish(0,copy_id='pen');d.return_to_hand(0,'pen')
    assert d.state['players'][0]['hand']==2 and not d.state['players'][0]['banished']
    d.send_to_graveyard(0,card={'copy_id':'disc','card_id':'z'},source='hand');assert d.state['players'][0]['hand']==1
    rejected(d,{'type':'send_to_graveyard','player':0,'copy_id':'nope'},'no conoce')
    check('field and pendulum zone flags, trap from hand rejected, graveyard/banish/hand moves')


def summon_materials():
    d=Duel();d.start_duel(opening_hand=6,extra_deck_sizes=(3,0));to_main1(d)
    d.special_summon(0,monster('m1','tuner',1000,0,2),'monster:0');d.special_summon(0,monster('m2','body',1500,0,4),'monster:1')
    rejected(d,{'type':'special_summon','player':0,'card':monster('sy','synchro',2500,2000,6),'zone':'extra_monster:0','source':'extra_deck','materials':['m1','m1']},'repetidos')
    rejected(d,{'type':'special_summon','player':0,'card':monster('sy','synchro',2500,2000,6),'zone':'extra_monster:0','source':'extra_deck','materials':['m1','zz']},'no es un monstruo')
    r=d.special_summon(0,monster('sy','synchro',2500,2000,6),'monster:0',source='extra_deck',materials=['m1','m2'])
    p=d.state['players'][0]
    assert r['materials']==['m1','m2'] and p['extra_deck']==2 and p['monster'][0]['copy_id']=='sy' and p['monster'][1] is None
    assert [c['copy_id'] for c in p['graveyard']]==['m1','m2']
    check('synchro/fusion/link: materials to the Graveyard, the new monster may take a material zone')
    d.special_summon(0,{'copy_id':'m3','card_id':'m1'},'monster:1',source='graveyard',from_copy='m1')
    d.special_summon(0,monster('m4','body',1500,0,4),'monster:2');p=d.state['players'][0]
    assert p['monster'][1]['copy_id']=='m3' and p['monster'][1]['name']=='tuner' and [c['copy_id'] for c in p['graveyard']]==['m2']
    rejected(d,{'type':'special_summon','player':0,'card':{'copy_id':'m4'},'zone':'monster:3','source':'graveyard','from_copy':'m2'},'ya está en el modelo')
    check('revive from the Graveyard under the new track copy_id')
    d.special_summon(0,monster('xz','xyz',2000,1000,4),'extra_monster:0',source='extra_deck',materials=['m3','m4'],attach=True)
    x=d.state['shared']['extra_monster'][0];p=d.state['players'][0]
    assert [c['copy_id'] for c in x['materials']]==['m3','m4'] and [c['copy_id'] for c in p['graveyard']]==['m2']
    assert Duel.from_json(d.to_json()).snapshot()==d.snapshot()
    d.send_to_graveyard(0,copy_id='xz');p=d.state['players'][0]
    assert [c['copy_id'] for c in p['graveyard']]==['m2','m3','m4','xz'] and 'materials' not in p['graveyard'][-1]
    check('xyz materials stay attached and go to the Graveyard when the monster leaves the field')


def facedown_and_flip():
    d=Duel();d.start_duel(opening_hand=6);to_main1(d)
    d.set_monster(0,{'copy_id':'back1'},'monster:0');d.set_spell_trap(0,{'copy_id':'back2'},'spell:1');d.end_turn()
    d.draw(1);to_main1(d);d.end_turn();d.draw(0);to_main1(d)
    d.observe(0,'monster:0',copy_id='face1',card_id='m',position='attack')
    assert d.discrepancies()[0]['kind']=='different_copy'
    rejected(d,{'type':'flip','player':0,'copy_id':'back1','as_copy':'back2'},'ya está en el modelo')
    r=d.flip(0,'back1',reveal={'card_id':'m','name':'Monstruo Volteo','atk':1200,'def':800,'level':3},as_copy='face1')
    card=d.state['players'][0]['monster'][0]
    assert r['copy_id']=='face1' and card['copy_id']=='face1' and card['card_id']=='m' and card['position']=='attack' and d.discrepancies()==[]
    assert d.observe(0,'monster:0',copy_id='face1',card_id='m',position='attack')['status']=='consistent'
    check('flip summon of a set monster, revealed and followed under the camera\'s new track')
    d.set_monster(0,{'copy_id':'back3'},'monster:1')
    rejected(d,{'type':'flip','player':0,'copy_id':'back3'},'el turno en que se colocó')
    d.flip(0,'back3',reveal={'card_id':'n'},as_copy='face3',position='defense')
    assert d.state['players'][0]['monster'][1]['position']=='defense'
    check('turned face-up by an effect: defense, no Flip Summon limits')
    d.activate_spell_trap(0,copy_id='back2',reveal={'card_id':'s','name':'Magia'},as_copy='face2')
    c=d.state['players'][0]['spell'][1];assert c['copy_id']=='face2' and c['card_id']=='s' and c['position']=='faceup'
    assert Duel.from_json(d.to_json()).snapshot()==d.snapshot()
    check('set Spell/Trap activated, revealed under a new track')
    d.observe(0,'spell:1',copy_id='again',card_id='s',position='faceup')
    r=d.apply({'type':'retrack','player':0,'zone':'spell:1','copy_id':'again'})
    assert r['from']=='face2' and d.state['players'][0]['spell'][1]['copy_id']=='again' and d.discrepancies()==[]
    rejected(d,{'type':'retrack','player':0,'zone':'spell:4','copy_id':'x'},'vacía')
    rejected(d,{'type':'retrack','player':0,'zone':'spell:1','copy_id':'face1'},'ya está en el modelo')
    check('retrack: the same card found again under a new track keeps everything else')


def observation_reconciliation():
    d=Duel();d.start_duel();to_main1(d)
    r=d.observe(0,'monster:3',copy_id='x9',card_id='c9',position='attack')
    assert r['status']=='unexplained' and d.state['players'][0]['monster'][3] is None,'Una carta vista no es una invocación'
    d.observe(0,'monster:3',copy_id='x9',card_id='c9',position='attack')
    pending=d.discrepancies();assert len(pending)==1 and pending[0]['kind']=='unexplained' and pending[0]['zone']=='monster:3'
    d.special_summon(0,{'copy_id':'x9','card_id':'c9','atk':100,'def':100},'monster:3')
    assert d.discrepancies()==[],'Explicar la carta limpia la discrepancia de esa zona'
    assert d.observe(0,'monster:3',copy_id='x9',card_id='c9',position='attack')['status']=='consistent'
    r=d.observe(0,'monster:3',copy_id='x9',card_id='other',position='defense')
    assert r['status']=='conflict' and d.discrepancies()[0]['fields']==['identity','position']
    assert d.state['players'][0]['monster'][3]['card_id']=='c9','La cámara no sobrescribe una identidad conocida'
    assert d.observe(0,'monster:4',copy_id='x9')['status']=='moved' and d.discrepancies()[-1]['known_at']=={'player':0,'zone':'monster:3'}
    assert d.observe(0,'monster:3')['status']=='missing'
    assert d.observe(0,'monster:3',copy_id='zz')['status']=='different_copy'
    assert len(d.discrepancies())==2,'Cada zona guarda sólo su última discrepancia'
    d.special_summon(0,{'copy_id':'anon'},'monster:1')
    r=d.observe(0,'monster:1',copy_id='anon',card_id='seen',position='attack')
    assert r['notes']==['identified'] and d.state['players'][0]['monster'][1]['card_id']=='seen'
    d.set_monster(0,{'copy_id':'hidden'},'monster:2')
    r=d.observe(0,'monster:2',copy_id='hidden',card_id='guess',position='facedown_defense')
    assert r['notes']==['identity_on_facedown_ignored'] and r['status']=='consistent' and d.state['players'][0]['monster'][2]['card_id'] is None
    r=d.observe(0,'monster:2',copy_id='hidden',card_id='guess',position='attack')
    assert r['status']=='conflict' and d.state['players'][0]['monster'][2]['card_id'] is None,'Ninguna observación identifica una carta boca abajo del modelo'
    assert d.observe(1,'extra_monster:0')['status']=='empty'
    rejected(d,{'type':'observe','player':0,'zone':'graveyard'},'Zona desconocida')
    rejected(d,{'type':'observe','player':0,'zone':'monster:0','position':'sideways'},'Posición desconocida')
    assert all(e['type']!='observe' or e['params']['zone'] for e in d.log)
    check('observation: unexplained card reported not summoned, per-zone latest discrepancy, identity never inferred face down')


def main():
    assert len(EVENTS)==20
    d=scripted_duel()
    json_roundtrip(d)
    deck_out_and_surrender()
    equal_attack_and_tributes()
    summon_materials()
    facedown_and_flip()
    observation_reconciliation()
    final=d.snapshot()
    result={'status':'passed','date':'2026-09-26','engine':'duel_engine.py','events_supported':list(EVENTS),
        'scripted_duel':{'turns':final['turn'],'events_logged':len(d.log),'final_lp':[p['lp'] for p in final['players']],
            'result':final['result'],'graveyards':[[c['copy_id'] for c in p['graveyard']] for p in final['players']]},
        'checks':CHECKS,
        'limits':'Reglas estructurales sólo; sin efectos de cartas, cadenas ni prioridad. No probado en duelos reales ni conectado al reconocedor.'}
    (ROOT/'research/qa/duel-engine.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
