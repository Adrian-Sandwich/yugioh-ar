"""Motor de duelo determinista para dos jugadores, dirigido por eventos.

Lógica pura: sin cámara, sin GPU y sin efectos de cartas. Modela zonas, fases,
puntos de vida y las reglas estructurales conocidas. Cada evento válido queda en
un registro con número de secuencia; un evento inválido lanza DuelError y no
cambia nada. Las observaciones de la cámara se concilian contra el modelo, pero
nunca se convierten por sí solas en una invocación.
"""
import copy
import json

PHASES=('draw','standby','main1','battle','main2','end')
BATTLE_STEPS=('start','battle','damage','end')
MONSTER_POSITIONS=('attack','defense','facedown_defense')
SPELL_POSITIONS=('faceup','facedown')
STATS=('name','atk','def','level','type')
FORMAT='duel_engine/1'


class DuelError(Exception):
    """Evento inválido; el estado del duelo no cambia."""


def _need(condition,message):
    if not condition: raise DuelError(message)


def _empty():
    return {'started':False,'turn':0,'current':None,'starting':None,'phase':None,'battle_step':None,'result':None,
        'players':[],'shared':{'extra_monster':[None,None]},'pending':[],'pending_attack':None,'turn_flags':{}}


def _player_state(name,deck,extra,lp,hand):
    # Las zonas péndulo son la primera y la última zona de magia/trampa (reglas vigentes).
    return {'name':name,'lp':lp,'deck':deck,'extra_deck':extra,'hand':hand,'monster':[None]*5,'spell':[None]*5,
        'spell_zone_pendulum':[True,False,False,False,True],'field':[None],'graveyard':[],'banished':[]}


def _player(st,player):
    _need(isinstance(player,int) and not isinstance(player,bool) and player in (0,1),'player debe ser 0 o 1')
    return st['players'][player]


def _merge(card,spec):
    """Copia identidad y estadísticas conocidas; un None nunca borra un valor previo."""
    _need(isinstance(spec,dict),'La carta se describe con un dict')
    for k in ('card_id',*STATS):
        v=spec.get(k)
        if v is None: continue
        if k in ('atk','def','level'): _need(isinstance(v,int) and not isinstance(v,bool) and v>=0,f'{k} debe ser un entero no negativo')
        elif k=='card_id': _need(isinstance(v,(int,str)) and not isinstance(v,bool),'card_id debe ser entero o texto')
        else: _need(isinstance(v,str),f'{k} debe ser texto')
        card[k]=v


def _new_card(st,spec,owner):
    """Carta que entra al modelo desde mano, mazo o mazo extra; copy_id viene de la pista del reconocedor."""
    _need(isinstance(spec,dict) and spec.get('copy_id') is not None,'La carta necesita copy_id (la pista del reconocedor)')
    copy_id=spec['copy_id'];_need(isinstance(copy_id,(int,str)) and not isinstance(copy_id,bool),'copy_id debe ser entero o texto')
    loc=_locate(st,copy_id)
    if loc is not None: raise DuelError(f'copy_id {copy_id!r} ya está en {loc[1]} del jugador {loc[0]}')
    card={'copy_id':copy_id,'card_id':None,'owner':owner,'controller':None,'position':None,
        'summoned_turn':None,'position_changed_turn':None,'attacked_turn':None,'set_turn':None,**{k:None for k in STATS}}
    _merge(card,spec)
    return card


def _is_monster_zone(zone): return zone.startswith('monster:') or zone.startswith('extra_monster:')
def _is_spell_zone(zone): return zone.startswith('spell:') or zone=='field'
def _key(player,zone): return 'shared:'+zone if zone.startswith('extra_monster:') else f'{player}:{zone}'


def _slot(st,player,zone):
    """(lista, índice) de una zona visible: monster:0-4, spell:0-4, field, extra_monster:0-1."""
    _need(isinstance(zone,str),'La zona se indica como texto, p. ej. "monster:2"')
    kind,_,index=zone.partition(':')
    if kind=='extra_monster' and index in ('0','1'): _player(st,player);return st['shared']['extra_monster'],int(index)
    p=_player(st,player)
    if kind in ('monster','spell') and index in ('0','1','2','3','4'): return p[kind],int(index)
    if zone=='field': return p['field'],0
    raise DuelError(f'Zona desconocida: {zone!r}')


def _everywhere(st):
    """Genera (controlador o dueño, zona, contenedor, índice) de cada carta conocida por el modelo."""
    for p,ps in enumerate(st['players']):
        for kind in ('monster','spell'):
            for i,c in enumerate(ps[kind]):
                if c is not None: yield p,f'{kind}:{i}',ps[kind],i
        if ps['field'][0] is not None: yield p,'field',ps['field'],0
        for kind in ('graveyard','banished'):
            for i in range(len(ps[kind])): yield p,kind,ps[kind],i
    for i,c in enumerate(st['shared']['extra_monster']):
        if c is not None: yield c['controller'],f'extra_monster:{i}',st['shared']['extra_monster'],i


def _locate(st,copy_id):
    for p,zone,cont,i in _everywhere(st):
        if cont[i]['copy_id']==copy_id: return p,zone,cont,i
    return None


def _monsters(st,player):
    return [(zone,cont[i]) for p,zone,cont,i in _everywhere(st) if p==player and _is_monster_zone(zone)]


def _own_monster(st,player,copy_id):
    loc=_locate(st,copy_id)
    _need(loc is not None and loc[0]==player and _is_monster_zone(loc[1]),f'{copy_id!r} no es un monstruo controlado por el jugador {player}')
    return loc[2][loc[3]]


def _clear_pending(st,key):
    st['pending']=[e for e in st['pending'] if e['key']!=key]


def _place(st,player,zone,card,position):
    slot,i=_slot(st,player,zone);_need(slot[i] is None,f'La zona {zone} del jugador {player} está ocupada')
    card.update(controller=player,position=position);slot[i]=card;_clear_pending(st,_key(player,zone))


def _take(st,copy_id):
    loc=_locate(st,copy_id);_need(loc is not None,f'El modelo no conoce la carta {copy_id!r}')
    player,zone,cont,i=loc;card=cont[i]
    if zone in ('graveyard','banished'): cont.pop(i)
    else: cont[i]=None;_clear_pending(st,_key(player,zone))
    card.update(controller=None,position=None,summoned_turn=None,position_changed_turn=None,attacked_turn=None,set_turn=None)
    return card


def _to_graveyard(st,card): st['players'][card['owner']]['graveyard'].append(card)
def _to_banished(st,card): st['players'][card['owner']]['banished'].append(card)


def _finish(st,winner,reason):
    st['result']={'winner':winner,'loser':None if winner is None else 1-winner,'reason':reason,'turn':st['turn']}


def _check_end(st):
    if st['result'] is not None: return
    dead=[i for i,p in enumerate(st['players']) if p['lp']<=0]
    if len(dead)==2: _finish(st,None,'lp')
    elif dead: _finish(st,1-dead[0],'lp')


def _main_phase(st,player):
    _need(player==st['current'],'Sólo el jugador del turno puede hacer esto')
    _need(st['phase'] in ('main1','main2'),'Esta acción sólo se hace en una Main Phase')


def _pick(st,player,copy_id,card,source,allowed):
    """Carta que sale de una zona conocida (copy_id) o de mano/mazo/mazo extra (card + source)."""
    if copy_id is not None:
        _need(card is None and source is None,'Indica copy_id (carta conocida) o card + source (mano, mazo o mazo extra), no ambos')
        loc=_locate(st,copy_id);_need(loc is not None,f'El modelo no conoce la carta {copy_id!r}')
        zone=loc[1];kind=zone if zone in ('graveyard','banished') else 'field'
        _need(kind in allowed,f'{copy_id!r} está en {zone}; ese movimiento no aplica desde ahí')
        return _take(st,copy_id)
    p=_player(st,player);_need(source in ('hand','deck','extra_deck'),'source debe ser hand, deck o extra_deck')
    _need(p[source]>0,f'No hay cartas en {source} del jugador {player}')
    new=_new_card(st,card,player);p[source]-=1
    return new


# --- Eventos -----------------------------------------------------------------

def _h_start_duel(st,names=('Jugador 1','Jugador 2'),starting=0,deck_sizes=(40,40),extra_deck_sizes=(0,0),lp=8000,opening_hand=5):
    _need(not st['started'],'El duelo ya empezó')
    _need(starting in (0,1),'starting debe ser 0 o 1')
    _need(len(names)==2 and len(deck_sizes)==2 and len(extra_deck_sizes)==2,'Se necesitan exactamente dos jugadores')
    _need(isinstance(lp,int) and lp>0,'lp debe ser un entero positivo')
    _need(isinstance(opening_hand,int) and opening_hand>=0,'opening_hand debe ser un entero no negativo')
    for size in (*deck_sizes,*extra_deck_sizes): _need(isinstance(size,int) and size>=0,'Los tamaños de mazo deben ser enteros no negativos')
    _need(min(deck_sizes)>=opening_hand,'El mazo no alcanza para la mano inicial')
    st.update(started=True,turn=1,current=starting,starting=starting,phase='draw',battle_step=None,result=None,pending=[],
        pending_attack=None,turn_flags={'drew':False,'normal_summoned':False},shared={'extra_monster':[None,None]},
        players=[_player_state(str(names[i]),deck_sizes[i]-opening_hand,extra_deck_sizes[i],lp,opening_hand) for i in (0,1)])
    return {'turn':1,'current':starting,'phase':'draw'}


def _h_draw(st,player,count=1,effect=False):
    p=_player(st,player);_need(isinstance(count,int) and not isinstance(count,bool) and count>=1,'count debe ser un entero positivo')
    if not effect:
        _need(player==st['current'],'Sólo el jugador del turno roba en su Draw Phase')
        _need(st['phase']=='draw','El robo normal ocurre en la Draw Phase')
        _need(st['turn']>1,'El jugador que empieza no roba en el primer turno')
        _need(not st['turn_flags']['drew'],'Ya se hizo el robo normal de este turno')
        _need(count==1,'El robo normal es de una sola carta')
        st['turn_flags']['drew']=True
    drawn=0
    for _ in range(count):
        if p['deck']==0: _finish(st,1-player,'deck_out');break
        p['deck']-=1;p['hand']+=1;drawn+=1
    return {'drawn':drawn,'deck':p['deck'],'hand':p['hand']}


def _normal(st,player,spec,zone,tributes,position):
    p=_player(st,player);_main_phase(st,player)
    _need(not st['turn_flags']['normal_summoned'],'Ya se hizo la Invocación Normal o colocación de este turno')
    _need(p['hand']>0,f'No hay cartas en la mano del jugador {player}')
    _need(isinstance(zone,str) and zone.startswith('monster:'),'La Invocación Normal o colocación va a una zona de monstruo principal (monster:0-4)')
    new=_new_card(st,spec,player);tributes=list(tributes)
    _need(len(set(tributes))==len(tributes),'Tributos repetidos')
    level=new['level']
    if level is not None:
        needed=0 if level<=4 else 1 if level<=6 else 2
        _need(len(tributes)==needed,f'Nivel {level} requiere {needed} tributo(s); se indicaron {len(tributes)}')
    for copy_id in tributes:
        _own_monster(st,player,copy_id);_to_graveyard(st,_take(st,copy_id))
    _place(st,player,zone,new,position);new['summoned_turn']=st['turn'];p['hand']-=1;st['turn_flags']['normal_summoned']=True
    return {'copy_id':new['copy_id'],'zone':zone,'position':position,'tributed':tributes}


def _h_normal_summon(st,player,card,zone,tributes=()): return _normal(st,player,card,zone,tributes,'attack')
def _h_set_monster(st,player,card,zone,tributes=()): return _normal(st,player,card,zone,tributes,'facedown_defense')


def _h_special_summon(st,player,card,zone,source='hand',position='attack'):
    p=_player(st,player);_need(position in ('attack','defense'),'La Invocación Especial es boca arriba: attack o defense')
    _need(isinstance(zone,str) and _is_monster_zone(zone),'Zona de monstruo requerida (monster:0-4 o extra_monster:0-1)')
    _need(isinstance(card,dict) and card.get('copy_id') is not None,'La carta necesita copy_id')
    if source in ('hand','deck','extra_deck'):
        _need(p[source]>0,f'No hay cartas en {source} del jugador {player}');new=_new_card(st,card,player);p[source]-=1
    elif source in ('graveyard','banished'):
        loc=_locate(st,card['copy_id']);_need(loc is not None and loc[1]==source,f'{card["copy_id"]!r} no está en {source}')
        new=_take(st,card['copy_id']);_merge(new,card)
    else: raise DuelError(f'Origen desconocido: {source!r}')
    _place(st,player,zone,new,position);new['summoned_turn']=st['turn']
    return {'copy_id':new['copy_id'],'zone':zone,'position':position,'source':source}


def _h_flip(st,player,copy_id,reveal=None):
    _player(st,player);_main_phase(st,player);card=_own_monster(st,player,copy_id)
    _need(card['position']=='facedown_defense','Sólo se voltea (Flip Summon) un monstruo boca abajo')
    _need(card['summoned_turn']!=st['turn'],'No se voltea un monstruo el turno en que se colocó')
    _need(card['position_changed_turn']!=st['turn'],'Ese monstruo ya cambió de posición este turno')
    if reveal is not None: _merge(card,reveal)
    card['position']='attack';card['position_changed_turn']=st['turn']
    return {'copy_id':copy_id,'position':'attack','card_id':card['card_id']}


def _h_change_position(st,player,copy_id,position):
    _player(st,player);_main_phase(st,player);card=_own_monster(st,player,copy_id)
    _need(position in ('attack','defense'),'position debe ser attack o defense (boca abajo sólo con set_monster)')
    _need(card['position'] in ('attack','defense'),'Un monstruo boca abajo se voltea con flip')
    _need(card['position']!=position,'El monstruo ya está en esa posición')
    _need(card['summoned_turn']!=st['turn'],'No cambia de posición el turno en que se invocó o colocó')
    _need(card['position_changed_turn']!=st['turn'],'Ese monstruo ya cambió de posición este turno')
    _need(card['attacked_turn']!=st['turn'],'Ese monstruo ya atacó este turno')
    card['position']=position;card['position_changed_turn']=st['turn']
    return {'copy_id':copy_id,'position':position}


def _h_activate_spell_trap(st,player,card=None,copy_id=None,zone=None,as_pendulum=False):
    p=_player(st,player)
    if copy_id is not None:
        _need(card is None,'Indica card (desde la mano) o copy_id (carta colocada), no ambos')
        loc=_locate(st,copy_id)
        _need(loc is not None and loc[0]==player and _is_spell_zone(loc[1]),f'{copy_id!r} no es una carta colocada del jugador {player}')
        c=loc[2][loc[3]];_need(c['position']=='facedown','La carta ya está boca arriba')
        _need(c['type']!='trap' or c['set_turn']!=st['turn'],'Una trampa no se activa el turno en que se colocó')
        c['position']='faceup';return {'copy_id':copy_id,'zone':loc[1],'position':'faceup'}
    _main_phase(st,player);_need(p['hand']>0,f'No hay cartas en la mano del jugador {player}')
    _need(isinstance(zone,str) and _is_spell_zone(zone),'Zona de magia/trampa requerida (spell:0-4 o field)')
    if as_pendulum:
        _need(zone.startswith('spell:') and p['spell_zone_pendulum'][int(zone[-1])],f'{zone} no es una zona péndulo')
    new=_new_card(st,card,player);_need(new['type']!='trap','Una trampa se coloca boca abajo antes de activarse')
    _place(st,player,zone,new,'faceup');new['set_turn']=st['turn'];p['hand']-=1
    return {'copy_id':new['copy_id'],'zone':zone,'position':'faceup','as_pendulum':bool(as_pendulum)}


def _h_set_spell_trap(st,player,card,zone):
    p=_player(st,player);_main_phase(st,player);_need(p['hand']>0,f'No hay cartas en la mano del jugador {player}')
    _need(isinstance(zone,str) and _is_spell_zone(zone),'Zona de magia/trampa requerida (spell:0-4 o field)')
    new=_new_card(st,card,player);_place(st,player,zone,new,'facedown');new['set_turn']=st['turn'];p['hand']-=1
    return {'copy_id':new['copy_id'],'zone':zone,'position':'facedown'}


def _h_send_to_graveyard(st,player,copy_id=None,card=None,source=None):
    moved=_pick(st,player,copy_id,card,source,('field','banished'));_to_graveyard(st,moved)
    return {'copy_id':moved['copy_id'],'owner':moved['owner']}


def _h_banish(st,player,copy_id=None,card=None,source=None):
    moved=_pick(st,player,copy_id,card,source,('field','graveyard'));_to_banished(st,moved)
    return {'copy_id':moved['copy_id'],'owner':moved['owner']}


def _h_return_to_hand(st,player,copy_id,to='hand'):
    _need(to in ('hand','extra_deck','deck'),'to debe ser hand, extra_deck o deck')
    moved=_pick(st,player,copy_id,None,None,('field','graveyard','banished'))
    # La mano y los mazos son sólo conteos: la copia deja de estar en el modelo.
    st['players'][moved['owner']][to]+=1
    return {'copy_id':copy_id,'owner':moved['owner'],'to':to}


def _h_declare_attack(st,player,attacker,target=None):
    _player(st,player);_need(player==st['current'],'Sólo ataca el jugador del turno')
    _need(st['phase']=='battle' and st['battle_step']=='battle','Los ataques se declaran en el Battle Step de la Battle Phase')
    card=_own_monster(st,player,attacker)
    _need(card['position']=='attack','Sólo ataca un monstruo boca arriba en posición de ataque')
    _need(card['attacked_turn']!=st['turn'],'Ese monstruo ya atacó este turno')
    enemies=[c['copy_id'] for _,c in _monsters(st,1-player)]
    if target is None: _need(not enemies,'Ataque directo sólo si el oponente no controla monstruos')
    else: _need(target in enemies,f'{target!r} no es un monstruo del oponente')
    st['pending_attack']={'attacker':attacker,'target':target,'player':player};st['battle_step']='damage'
    return {'attacker':attacker,'target':target,'direct':target is None}


def _lp(st,player,delta,reason):
    st['players'][player]['lp']+=delta
    return {'player':player,'delta':delta,'reason':reason,'lp':st['players'][player]['lp']}


def _h_resolve_battle(st,reveal=None):
    pa=st['pending_attack'];_need(pa is not None and st['battle_step']=='damage','No hay ataque pendiente que resolver')
    me=pa['player'];opp=1-me;result={'attacker':pa['attacker'],'target':pa['target'],'destroyed':[],'lp_changes':[]}
    st['pending_attack']=None;st['battle_step']='battle'
    loc=_locate(st,pa['attacker'])
    if loc is None or loc[0]!=me or not _is_monster_zone(loc[1]): result['outcome']='cancelled_attacker_gone';return result
    attacker=loc[2][loc[3]];attacker['attacked_turn']=st['turn']
    atk=attacker['atk'];_need(atk is not None,f'ATK desconocido del atacante {pa["attacker"]!r}; regístralo con sus estadísticas')
    if pa['target'] is None:
        result['lp_changes'].append(_lp(st,opp,-atk,'battle_direct'));result['outcome']='direct';return result
    tloc=_locate(st,pa['target'])
    if tloc is None or tloc[0]!=opp or not _is_monster_zone(tloc[1]): result['outcome']='cancelled_target_gone';return result
    target=tloc[2][tloc[3]]
    if target['position']=='facedown_defense':
        # La carta se revela al ser atacada; la identidad la aporta quien la ve, no el modelo.
        if reveal is not None: _merge(target,reveal)
        target['position']='defense';result['flipped']=pa['target']
    if target['position']=='attack':
        tatk=target['atk'];_need(tatk is not None,f'ATK desconocido del objetivo {pa["target"]!r}')
        if atk>tatk: result['destroyed'].append(pa['target']);result['lp_changes'].append(_lp(st,opp,tatk-atk,'battle'))
        elif atk<tatk: result['destroyed'].append(pa['attacker']);result['lp_changes'].append(_lp(st,me,atk-tatk,'battle'))
        elif atk>0: result['destroyed'].extend([pa['attacker'],pa['target']])
        result['outcome']='attack_vs_attack'
    else:
        tdef=target['def'];_need(tdef is not None,f'DEF desconocida del objetivo {pa["target"]!r}; indica reveal con sus estadísticas')
        if atk>tdef: result['destroyed'].append(pa['target'])
        elif atk<tdef: result['lp_changes'].append(_lp(st,me,atk-tdef,'battle'))
        result['outcome']='attack_vs_defense'
    for copy_id in result['destroyed']: _to_graveyard(st,_take(st,copy_id))
    return result


def _h_change_lp(st,player,delta,reason=''):
    _player(st,player);_need(isinstance(delta,int) and not isinstance(delta,bool),'delta debe ser entero')
    _need(isinstance(reason,str),'reason debe ser texto')
    return _lp(st,player,delta,reason)


def _h_next_phase(st,skip_battle=False):
    phase=st['phase']
    if phase=='draw':
        _need(st['turn_flags']['drew'] or st['turn']==1,'Hay que robar antes de salir de la Draw Phase');st['phase']='standby'
    elif phase=='standby': st['phase']='main1'
    elif phase=='main1':
        if st['turn']==1 or skip_battle: st['phase']='end'
        else: st['phase']='battle';st['battle_step']='start'
    elif phase=='battle':
        step=st['battle_step']
        _need(step!='damage','Resuelve el ataque pendiente antes de avanzar')
        # El Damage Step sólo se entra declarando un ataque; sin ataque, Battle Step pasa al End Step.
        if step=='end': st['phase']='main2';st['battle_step']=None
        else: st['battle_step']='battle' if step=='start' else 'end'
    elif phase=='main2': st['phase']='end'
    else: raise DuelError('En la End Phase el turno se cierra con end_turn')
    return {'phase':st['phase'],'battle_step':st['battle_step']}


def _h_end_turn(st):
    _need(st['phase'] in ('main1','main2','end'),'El turno se termina desde Main Phase 1, Main Phase 2 o End Phase')
    st['turn']+=1;st['current']=1-st['current'];st['phase']='draw';st['battle_step']=None;st['pending_attack']=None
    st['turn_flags']={'drew':False,'normal_summoned':False}
    return {'turn':st['turn'],'current':st['current'],'phase':'draw'}


def _h_surrender(st,player):
    _player(st,player);_finish(st,1-player,'surrender');return dict(st['result'])


def _h_observe(st,player,zone,copy_id=None,card_id=None,position=None):
    """Concilia lo que ve la cámara con el modelo. Nunca invoca ni mueve cartas por sí solo.

    Registra en `pending` la última discrepancia de cada zona; una observación
    consistente la borra. Lo único que completa es el card_id de una carta boca
    arriba que el modelo tenía sin identidad.
    """
    slot,i=_slot(st,player,zone);current=slot[i];key=_key(player,zone);notes=[]
    _need(position is None or position in MONSTER_POSITIONS+SPELL_POSITIONS,f'Posición desconocida: {position!r}')
    facedown=position in ('facedown_defense','facedown')
    if facedown and card_id is not None:
        notes.append('identity_on_facedown_ignored');card_id=None
    _clear_pending(st,key);entry={'key':key,'player':player,'zone':zone,'copy_id':copy_id,'card_id':card_id,'position':position}
    if copy_id is None:
        status='empty' if current is None else 'missing'
        if current is not None: entry.update(kind='missing',expected_copy=current['copy_id'])
    elif current is None:
        where=_locate(st,copy_id)
        status='moved' if where else 'unexplained'
        entry.update(kind=status,known_at=None if where is None else {'player':where[0],'zone':where[1]})
    elif current['copy_id']!=copy_id:
        where=_locate(st,copy_id);status='different_copy'
        entry.update(kind=status,expected_copy=current['copy_id'],known_at=None if where is None else {'player':where[0],'zone':where[1]})
    else:
        conflicts=[]
        model_facedown=current['position'] in ('facedown_defense','facedown')
        if card_id is not None and not model_facedown and not facedown:
            if current['card_id'] is None: current['card_id']=card_id;notes.append('identified')
            elif current['card_id']!=card_id: conflicts.append('identity')
        elif card_id is not None and model_facedown: conflicts.append('identity')
        if position is not None and position!=current['position']: conflicts.append('position')
        status='conflict' if conflicts else 'consistent'
        if conflicts: entry.update(kind='conflict',fields=conflicts,expected_card_id=current['card_id'],expected_position=current['position'])
    if status not in ('empty','consistent'): st['pending'].append(entry)
    return {'status':status,'notes':notes,'pending':len(st['pending'])}


HANDLERS={'start_duel':_h_start_duel,'draw':_h_draw,'normal_summon':_h_normal_summon,'set_monster':_h_set_monster,
    'special_summon':_h_special_summon,'flip':_h_flip,'change_position':_h_change_position,
    'activate_spell_trap':_h_activate_spell_trap,'set_spell_trap':_h_set_spell_trap,'send_to_graveyard':_h_send_to_graveyard,
    'banish':_h_banish,'return_to_hand':_h_return_to_hand,'declare_attack':_h_declare_attack,'resolve_battle':_h_resolve_battle,
    'change_lp':_h_change_lp,'next_phase':_h_next_phase,'end_turn':_h_end_turn,'surrender':_h_surrender,'observe':_h_observe}
EVENTS=tuple(HANDLERS)


class Duel:
    """Máquina de estados del duelo. El estado se deriva sólo del registro de eventos."""

    def __init__(self):
        self.state=_empty();self.log=[]

    def apply(self,event):
        _need(isinstance(event,dict) and isinstance(event.get('type'),str),'El evento debe ser un dict con "type"')
        kind=event['type'];handler=HANDLERS.get(kind);_need(handler is not None,f'Evento desconocido: {kind!r}')
        try: params=json.loads(json.dumps({k:v for k,v in event.items() if k!='type'}))
        except (TypeError,ValueError): raise DuelError('Los parámetros del evento deben ser serializables a JSON') from None
        # Se trabaja sobre una copia: un DuelError deja el estado real intacto.
        working=copy.deepcopy(self.state)
        if kind!='start_duel':
            _need(working['started'],'El duelo no ha empezado')
            if kind!='observe': _need(working['result'] is None,'El duelo ha terminado')
        try: result=handler(working,**params)
        except TypeError as error: raise DuelError(f'Parámetros inválidos para {kind}: {error}') from None
        if kind!='observe': _check_end(working)
        seq=len(self.log)+1;self.log.append({'seq':seq,'type':kind,'params':params});self.state=working
        return {'seq':seq,**(result or {})}

    # Envolturas explícitas de cada evento.
    def start_duel(self,**params): return self.apply({'type':'start_duel',**params})
    def draw(self,player,count=1,effect=False): return self.apply({'type':'draw','player':player,'count':count,'effect':effect})
    def normal_summon(self,player,card,zone,tributes=()): return self.apply({'type':'normal_summon','player':player,'card':card,'zone':zone,'tributes':list(tributes)})
    def set_monster(self,player,card,zone,tributes=()): return self.apply({'type':'set_monster','player':player,'card':card,'zone':zone,'tributes':list(tributes)})
    def special_summon(self,player,card,zone,source='hand',position='attack'): return self.apply({'type':'special_summon','player':player,'card':card,'zone':zone,'source':source,'position':position})
    def flip(self,player,copy_id,reveal=None): return self.apply({'type':'flip','player':player,'copy_id':copy_id,'reveal':reveal})
    def change_position(self,player,copy_id,position): return self.apply({'type':'change_position','player':player,'copy_id':copy_id,'position':position})
    def activate_spell_trap(self,player,card=None,copy_id=None,zone=None,as_pendulum=False): return self.apply({'type':'activate_spell_trap','player':player,'card':card,'copy_id':copy_id,'zone':zone,'as_pendulum':as_pendulum})
    def set_spell_trap(self,player,card,zone): return self.apply({'type':'set_spell_trap','player':player,'card':card,'zone':zone})
    def send_to_graveyard(self,player,copy_id=None,card=None,source=None): return self.apply({'type':'send_to_graveyard','player':player,'copy_id':copy_id,'card':card,'source':source})
    def banish(self,player,copy_id=None,card=None,source=None): return self.apply({'type':'banish','player':player,'copy_id':copy_id,'card':card,'source':source})
    def return_to_hand(self,player,copy_id,to='hand'): return self.apply({'type':'return_to_hand','player':player,'copy_id':copy_id,'to':to})
    def declare_attack(self,player,attacker,target=None): return self.apply({'type':'declare_attack','player':player,'attacker':attacker,'target':target})
    def resolve_battle(self,reveal=None): return self.apply({'type':'resolve_battle','reveal':reveal})
    def change_lp(self,player,delta,reason=''): return self.apply({'type':'change_lp','player':player,'delta':delta,'reason':reason})
    def next_phase(self,skip_battle=False): return self.apply({'type':'next_phase','skip_battle':skip_battle})
    def end_turn(self): return self.apply({'type':'end_turn'})
    def surrender(self,player): return self.apply({'type':'surrender','player':player})
    def observe(self,player,zone,copy_id=None,card_id=None,position=None): return self.apply({'type':'observe','player':player,'zone':zone,'copy_id':copy_id,'card_id':card_id,'position':position})

    # Consultas.
    def snapshot(self): return copy.deepcopy(self.state)
    def discrepancies(self): return copy.deepcopy(self.state['pending'])
    def finished(self): return self.state['result'] is not None
    def to_json(self): return json.dumps({'format':FORMAT,'log':self.log,'state':self.state},ensure_ascii=False)

    @classmethod
    def replay(cls,log):
        duel=cls()
        for entry in log: duel.apply({'type':entry['type'],**entry['params']})
        return duel

    @classmethod
    def from_json(cls,text):
        data=json.loads(text);_need(isinstance(data,dict) and data.get('format')==FORMAT,'Formato de duelo desconocido')
        duel=cls.replay(data['log'])
        _need(duel.state==data['state'],'La reproducción del registro no coincide con el estado guardado')
        return duel

    def undo(self):
        """Deshace el último evento reproduciendo el registro sin él."""
        _need(self.log,'No hay eventos que deshacer')
        replay=Duel.replay(self.log[:-1]);self.state,self.log=replay.state,replay.log
        return len(self.log)
