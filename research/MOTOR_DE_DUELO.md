# Motor de duelo

Fecha: 26/09/2026. Módulo `duel_engine.py`, prueba `qa_duel_engine.py`,
informe `qa/duel-engine.json`. Lógica pura: sin cámara, sin GPU, sin
dependencias fuera de la biblioteca estándar. No está conectado todavía al
reconocedor ni probado en duelos reales.

## Qué modela

Un duelo de dos jugadores como máquina de estados dirigida por eventos. Cada
evento válido se añade a un registro con número de secuencia creciente; el
estado se deriva sólo de ese registro, así que `undo` reproduce el registro sin
el último evento y `from_json` rechaza un estado guardado que no coincida con
su registro. Un evento inválido lanza `DuelError` con mensaje en español y no
cambia nada: el manejador trabaja sobre una copia y sólo se publica si termina.

| Concepto | Modelo |
|---|---|
| Zonas por jugador | `monster:0-4`, `spell:0-4`, `field`, cementerio, destierro; mano, mazo y mazo extra como conteos |
| Zonas compartidas | `extra_monster:0-1` |
| Zonas péndulo | banderas `spell_zone_pendulum` sobre la primera y la última zona de magia/trampa |
| Puntos de vida | 8000 por defecto, `change_lp` con motivo registrado |
| Turnos y fases | draw, standby, main1, battle (start, battle, damage, end), main2, end |
| Cartas | `copy_id` de la pista física del reconocedor; `card_id` de catálogo opcional; nombre, ATK, DEF, nivel y tipo cuando se conocen |
| Posiciones | attack, defense, facedown_defense; faceup, facedown para magia/trampa |
| Fin | LP ≤ 0, mazo agotado al robar, rendición |

`copy_id` y `card_id` se guardan separados, igual que `track_id` y `card_id`
en el visor: una carta boca abajo puede existir en el modelo sin identidad y
ninguna observación se la asigna.

## Eventos

`start_duel`, `draw`, `normal_summon`, `set_monster`, `special_summon`, `flip`,
`change_position`, `activate_spell_trap`, `set_spell_trap`,
`send_to_graveyard`, `banish`, `return_to_hand`, `declare_attack`,
`resolve_battle`, `change_lp`, `next_phase`, `end_turn`, `surrender` y
`observe`. Todos aceptan un dict serializable por `Duel.apply` y tienen un
método envoltorio con el mismo nombre.

Reglas estructurales que sí se validan: robo obligatorio salvo el primer turno
del que empieza; una sola Invocación Normal o colocación por turno; tributos
por nivel (5-6 uno, 7+ dos); sin Battle Phase en el primer turno; ataques sólo
en el Battle Step con monstruos boca arriba en ataque que no hayan atacado; un
cambio de posición por turno y nunca el turno de la invocación; trampas no se
activan el turno en que se colocan; cálculo de daño ATK/DEF con destrucción y
LP; ataque directo sólo sin monstruos rivales. Un defensor boca abajo se revela
al resolver la batalla con `reveal`, porque su identidad la aporta quien lo ve.

## Conciliación con la cámara

`observe(player, zone, copy_id, card_id, position)` compara lo que ve la
cámara con el modelo y **nunca invoca ni mueve cartas por sí solo**. Guarda
por zona la última discrepancia en `pending` (`unexplained`, `moved`,
`missing`, `different_copy`, `conflict`) y la borra cuando el jugador registra
el evento que la explica. Lo único que completa es el `card_id` de una carta
boca arriba que el modelo tenía sin identidad. Una identidad observada sobre
una carta que el modelo tiene boca abajo se ignora y se reporta como conflicto.

## Fuera de alcance

Efectos de cartas, cadenas, prioridad, condiciones de invocación especial,
contenido de la mano, Link, Xyz, Sincronía y Fusión como mecánicas propias
(se invocan con `special_summon` desde `extra_deck` sin comprobar materiales),
y cualquier regla de formato concreto. El motor no es un árbitro: es el estado
compartido sobre el que el reconocedor y los jugadores anotan.

## Cómo probarlo

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 qa_duel_engine.py
```

La prueba guioniza un duelo de cuatro turnos (43 eventos): invocaciones,
trampa colocada y activada en el turno rival, ataque contra un monstruo en
ataque más fuerte, ataque contra un defensor boca abajo revelado al resolver,
ataque directo, resurrección desde el cementerio, LP a cero. Comprueba además
que cada acción inválida deja estado y registro idénticos, `undo`, ida y
vuelta JSON con reproducción determinista y rechazo de un estado manipulado,
mazo agotado, rendición, ATK iguales, tributos con la zona extra compartida,
banderas de zona péndulo y la conciliación de observaciones.

## Siguiente paso para conectarlo

El reconocedor emite por análisis detecciones con `track_id`, `card_id`,
`corners` y `stable`. Falta un paso de mapa de tapete: una homografía de la
mesa que convierta las esquinas en una zona (`player`, `monster:n`, ...) y
llame a `observe` por cada carta estable. Con el registro de `pending` el
visor puede pedir al jugador que explique una carta nueva ("¿Invocación
Normal o Especial?") en lugar de adivinarlo.

## Mapa del tapete (27/09/2026)

`playmat.py`, prueba `qa_playmat.py`. Cuatro esquinas por tapete (vistas desde
su jugador) dan una homografía al cuadrado unitario; la plantilla es el tapete
oficial de TCG de un jugador (fila superior campo, cinco monstruos y
cementerio; inferior mazo extra, cinco magias/trampas y mazo) y las dos zonas
de monstruo extra quedan fuera del tapete, entre los jugadores. La orientación
se mide en milímetros del tapete (60 × 35 cm): vertical = ataque, horizontal =
defensa; boca abajo lo decide quien vio el reverso. `ZoneTracker` sólo reporta
una zona tras tres lecturas coincidentes y nunca emite eventos: sus
observaciones van a `observe`. Configuración elegida: dos tapetes frente a
frente, y también un modo de un solo tapete.

## Duelo en el visor (27/09/2026)

`table_duel.py` (prueba `qa_table_duel.py`) une el visor en vivo, el tapete y
el motor. En la cámara (sección "Duelo en la mesa"): se elige el modo, se
pulsa "Calibrar tapetes" y se hace clic en las cuatro esquinas de cada tapete
tal como las ve su jugador; la calibración queda en `data/playmat/` y la
cuadrícula de zonas se dibuja sobre el vídeo. Tras cada análisis sólo las
pistas confirmadas pasan por `ZoneTracker`, y al motor sólo llegan los
cambios (a 3.8 análisis/s repetir observaciones idénticas llenaría el registro).
Cada discrepancia se muestra como pregunta con sus respuestas: carta nueva en
zona de monstruo (Invocación Normal/Especial, colocada; tributos a elegir si el
nivel es 5+), en magia/trampa (activada, colocada), carta que desaparece
(cementerio, destierro, mano) y posición distinta (cambio de posición,
volteo). Al responder, la carta entra con nombre, ATK, DEF y nivel de
`card_info`. Un monstruo que no es Péndulo en una zona de magia/trampa, o una
magia/trampa en zona de monstruo, no ofrece respuestas: casi siempre es una
calibración desfasada o una carta mal puesta. Controles: empezar, siguiente
fase, terminar turno, robar, LP, ataque y resolución de batalla, deshacer y
reiniciar. El registro del duelo se guarda tras cada evento y se recupera al
reiniciar el visor. La cara boca abajo todavía no se detecta (falta el reverso
como identidad), así que "colocada boca abajo" la declara el jugador.

Probado en Edge con un visor real y la escena de 9 cartas (calibración de un
tapete, inicio, fases, LP, deshacer, 5 preguntas y una respuesta aplicada).

## Plantilla impresa con marcadores (27/09/2026)

Propuesta del usuario (como los demos de duelo en AR): en lugar de marcar
esquinas, una plantilla predefinida que se imprime, con las zonas dibujadas
para que el jugador sepa dónde va cada carta, e invariante al movimiento.
`playmat_print.py` genera una por jugador (678 × 318 mm; PDF en una pieza o en
6 hojas carta con solape, y PNG): esquinas en "L" y etiquetas por zona (CAMPO,
M1-M5, CEMENTERIO, MAZO EXTRA, MT1-MT5, MAZO) y un marcador ArUco
(DICT_4X4_50) en cada esquina, fuera de las zonas: ids 0-3 el jugador 1, 4-7
el jugador 2. `detect_mats` encuentra los marcadores en cada análisis (7 ms a
1080p) y ajusta la homografía con las cuatro esquinas de cada marcador en
milímetros conocidos. Hacen falta al menos dos marcadores: con uno solo la
extrapolación desplazó una carta una zona entera en la prueba. Mientras una
mano tapa los marcadores se conserva la última posición buena 5 s.

En el visor es el modo "Plantilla impresa (automática)" (sin clics; los
enlaces a los PDF están en la sección del duelo). Los modos con clics quedan
para tapetes propios sin marcadores. Pruebas: `qa_playmat_print.py` (56 casos
de zona y orientación en perspectiva, dos marcadores bastan, uno no, cámara
movida) y en Edge con un visor real: los dos tapetes impresos se ven sin
clics y las tres cartas puestas generan exactamente sus tres preguntas.
