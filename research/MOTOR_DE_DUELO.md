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

## Vista de duelo separada (27/09/2026)

El duelo tiene su propia página, `http://127.0.0.1:8765/duelo` (`web/duel.html`,
`web/duel.js`): el vídeo en vivo con el tablero, las cartas (nombre en español
e inglés) y los monstruos AR, y a un lado el tablero, el duelo y las preguntas.
Sin el último fotograma analizado, OCR, reflejos ni textos de diagnóstico: eso
queda en el visor de siempre (`/`), que ya no incluye el duelo y enlaza a la
vista nueva. El dibujo de sprites (WebGL) se comparte en `web/ar.js`. La vista
de duelo pide resultados a `/analysis` para que el servidor siga analizando
aunque el visor de diagnóstico esté cerrado. Las Zonas de Monstruo Extra sólo
ofrecen Invocación Especial.

## Vista de duelo minimalista (27/09/2026)

Cartas y zonas se marcan sólo con sus cuatro esquinas (como la plantilla
impresa); las zonas de pila (Cementerio, Mazo, Mazo Extra, Desterradas) más
tenues. Con un tablero puesto, sólo se muestran las cartas cuyo centro cae en
una zona del campo (Monstruo, Magia/Trampa, Campo, Monstruo Extra): una carta
en la mano, fuera del tablero o boca arriba en una pila no lleva marca, nombre
ni monstruo, y el contador de arriba cuenta sólo las del campo. Además el
reconocedor recibe los polígonos de esas zonas (`TableDuel.field_regions`,
`regions` en `analyze_jpeg`): las cajas cuyo centro queda fuera no pasan por
geometría ni encoder (`outside_regions` las cuenta). Sin tablero se analiza
todo, como en el visor de diagnóstico.

## Carta en juego, pilas e historial (27/09/2026)

Decisiones con el usuario: los efectos no se resuelven solos todavía; primero
que los jugadores entiendan qué pasa. "Carta en juego" (arriba del panel)
muestra la carta de la última jugada, la que se toque en el vídeo o la que se
elija en una pila: imagen (`/card-image`, la mejor imagen enlazada a 360 px),
nombre en español e inglés, tipo, ATK/DEF y efecto. Bajo cada carta del campo,
dos líneas cortas: nombre y ATK/DEF (o el tipo de Magia/Trampa).
"Cementerio y Desterradas" lista las cartas de cada pila con su nombre
(`graveyard_cards`, `banished_cards` en la vista del duelo). "Terminar y
reiniciar" archiva el duelo en `data/playmat/history/` con su registro
completo, reproducible con `Duel.replay`; "Historial de duelos" los lista.

## Batalla (27/09/2026)

Acordado con el usuario: ataques con clic en el vídeo o con el gesto de
llevar y regresar, y el daño propuesto pero nunca aplicado solo (los efectos
pueden cambiarlo). En la Battle Phase, clic en un monstruo propio en ataque y
luego en uno rival (o "Ataque directo"): `TableDuel.attack` avanza al Battle
Step si hace falta y declara. El gesto (`_gesture`): un monstruo propio en
ataque que se aleja más de 0.6 anchos de zona de la suya, llega a menos de 0.6
de un monstruo rival y regresa a menos de 0.35 de su zona en 8 s declara ese
ataque; mientras dura, su zona vacía no cuenta como "salió del campo".
`battle_preview` resuelve el ataque sobre una copia del duelo
(`Duel.replay(log)`), así lo propuesto es exactamente lo que se aplicaría:
"Dragón Blanco de Ojos Azules (ATK 3000) ataca a Mago Oscuro (ATK 2500) ·
Mago Oscuro es destruido; Jugador 1 pierde 500 LP". "Aplicar resultado"
resuelve; "Cancelar ataque" regresa el registro al punto anterior a la
declaración. En el vídeo, el atacante elegido brilla y el ataque declarado
lleva una flecha al objetivo. Pruebas: `qa_table_duel.py` (gesto, propuesta
sin aplicar, aplicar, segundo ataque rechazado) y en Edge (clic, propuesta,
LP intactos hasta aplicar, Cementerio).

## Tipos de invocación con materiales (27/09/2026)

Acordado: el sistema propone la invocación y sus materiales ("Invocación
Sincronía: X con A + B"); los jugadores confirman o corrigen desde "Últimas
jugadas". Motor: `special_summon` acepta `materials` (monstruos propios en el
campo; salen primero, así el nuevo puede ocupar la zona de uno), `attach`
(Xyz: quedan debajo en `materials` y van al Cementerio cuando el monstruo deja
el campo) y `from_copy` (la carta del Cementerio o destierro que vuelve, cuando
la cámara la sigue con otro `copy_id`).

`TableDuel` deduce los materiales de lo que acaba de salir del campo: monstruos
propios que la cámara ya no ve (aún en el modelo) y los que la jugada
automática mandó al Cementerio hace menos de 20 s (`MATERIAL_WINDOW_S`), si
después sólo hubo observaciones; esas jugadas se deshacen y se repiten las
observaciones. Con los datos de la carta (`card_sheet`): Sincronía exige un
Cantante y la suma de Niveles; Xyz, dos o más del Nivel igual al Rango; Link,
tantos como su LINK; Fusión, dos o más (sin leer aún qué materiales pide);
Tributo, 1 o 2 según el Nivel en una Zona de Monstruo principal. Una carta
puesta encima de otra propia (`different_copy`) sólo se explica usándola de
material. Un monstruo del Mazo Extra o de Nivel 5+ sin materiales disponibles
espera `MISSING_GRACE_S` antes de decidir, por si los materiales salen justo
después. Si la misma carta está en el Cementerio del jugador, se ofrece
revivirla (primero si no cabe una Invocación Normal). Al cambiar a una
Invocación Especial simple, los materiales que ya no se usan van al Cementerio
(la cámara los vio salir); al deshacer, vuelven a esperar como salidas del
campo. Corregido de paso: tras una jugada automática la zona se marca para
reenviarse en vez de olvidarse, así una carta que sale antes de volver a verse
cuenta como salida. Pruebas: `qa_duel_engine.py` (materiales, Xyz, revivir con
otra copia) y `qa_table_duel.py` (Sincronía, Xyz desde el Cementerio, cambio a
Especial simple, Tributo encima de una zona, revivir).

## Boca abajo y Volteo (27/09/2026)

El detector de cartas (`ygo_yolo.onnx`) se entrenó con caras: pegados en una
captura en vivo, dos reversos no recibieron caja y cartas boca arriba en los
mismos lugares sí (0.96 y 0.72). Acordado con el usuario: revisar zonas ahora
e incluir reversos cuando se entrene YOLO11; reverso oficial más reversos
enseñados (fundas).

`card_backs.py`: cada zona de Monstruo principal, Magia/Trampa y Campo del
tablero sin una carta reconocida se rectifica a 224x224 y se codifica con el
mismo codificador del reconocedor; se compara con los reversos (umbral 0.45).
Una caja del detector sin identidad aceptada no cuenta como ocupada (a veces
enmarca un reverso). Referencias en `data/card-backs` (fuera del repositorio;
`YUGIOH_CARD_BACKS` la cambia para pruebas): el reverso oficial, descargado
la primera vez (YGOPRODeck y Yugipedia), y los enseñados con "Enseñar
reverso" en /duelo (clic en la zona con la carta boca abajo; guarda ese
recorte). Medido en GPU: 11 ms por 6 zonas, 17-19 ms por análisis con un
tapete; reversos 0.75-0.94, zonas vacías, cartas boca arriba y una funda sin
enseñar 0.07-0.13, la funda enseñada 0.999 (`qa_card_backs.py`, escena
sintética; el umbral falta calibrarlo con capturas reales).

`TableDuel` convierte cada zona con reverso en una pista `back-<sesión>-<n>`:
el mismo id mientras el reverso siga ahí, aunque una mano lo tape hasta 20
análisis; uno nuevo cuando vuelve después. Un reverso en Zona de Monstruo es
"Colocado boca abajo"; en Magia/Trampa, "Colocada boca abajo". Cuando la cara
de la carta aparece donde el modelo tenía un reverso (`different_copy`): en
ataque, Invocación por Volteo; en defensa, volteado por un efecto; en
Magia/Trampa, activada. El motor revela la carta (`reveal`) y la sigue con la
pista de la cara (`as_copy`, en `flip` y `activate_spell_trap`); `flip` con
`position='defense'` no tiene los límites de la Invocación por Volteo. En el
vídeo, las cartas boca abajo del duelo se marcan en su zona con "Boca abajo".
Pruebas: `qa_duel_engine.py` (Volteo con otra pista, por efecto, activar
colocada), `qa_table_duel.py` (colocar por zona, mano encima, Volteo,
activar) y en Edge (reverso de lado y de pie, carta boca arriba intacta,
funda enseñada con clic).

Siguiente, ya acordado: datos de mecánicas desde BabelCDB, descargados fuera
del repositorio; al entrenar YOLO11, reversos (y fundas) como clase. Para más
adelante (pedido el 27/09/2026): seguir a dónde va una carta que sale de una
zona (Cementerio, de vuelta al Mazo o a la mano) en vez de suponer siempre el
Cementerio.

## ygopro-core (revisado el 27/09/2026)

`Fluorohydride/ygopro-core`: licencia MIT, C++ con Lua, activo (último push
26/09/2026). Es el motor completo de YGOPro: el anfitrión carga los mazos
enteros con `new_card`, llama a `process()` en bucle y responde a los mensajes
que piden decisiones (`get_message`, `set_responsei/b`); cadenas, ventanas de
activación, Damage Step y costos los resuelve él. Los efectos viven en
`ygopro-scripts` (unos 13 mil scripts Lua, GPL-2.0) y los datos en `cards.cdb`.

No encaja hoy con cartas físicas: el motor es dueño de la información oculta
y del azar (orden del mazo, robos), y una mesa real roba otras cartas. Las
opciones realistas, para más adelante: (1) consultor de reglas "en espejo",
reconstruyendo el tablero visible y la mano declarada con la API de puzzles
(`Debug.AddCard`, `Debug.ReloadFieldBegin/End` en `libdebug.cpp`) para
preguntar qué acciones son legales o qué puede responder el rival; exige
compilar el núcleo con Lua para Windows, un envoltorio (ctypes) y leer su
protocolo binario de mensajes; (2) sólo sus datos (`cards.cdb` de
ygopro-database) para arquetipos, categorías y tipos. Los scripts GPL se
descargarían aparte, fuera del repositorio MIT. El panel muestra
"Últimas jugadas" (tres) y "Preguntas" sólo cuando hay; LP, robar, deshacer y
la lista del campo quedan plegados, y los ajustes del tablero se pliegan solos
al fijarlo.

## Jugadas automáticas y barra de fases (27/09/2026)

Con una pregunta por cada carta el duelo se volvía lento. Como en Master Duel
y YGOPro, poner una carta cuenta como la jugada obvia (`TableDuel._plays`, en
orden de probabilidad) y las preguntas quedan sólo para lo que el motor
rechaza: monstruo vertical, Invocación Normal si es nivel 4 o menos y queda la
del turno, si no Especial (desde el Mazo Extra si es Sincronía, Xyz, Fusión o
Link); horizontal, Especial en defensa; sin identidad, colocado; magia/trampa
reconocida, activada, si no colocada; monstruo que desaparece 3 s
(`MISSING_GRACE_S`, para que una mano encima no lo mande al Cementerio), al
Cementerio; cambio de orientación, cambio de posición o volteo. Si la jugada
llega en la Draw o Standby Phase del jugador del turno, se avanza a la Main
Phase 1 robando si faltaba (la carta física ya se robó).

Cada jugada automática queda en "Últimas jugadas" con "Era: …" (otra jugada) y
"Deshacer": se regresa el registro exactamente al punto anterior a ella
(`revise`) y una jugada deshecha no se vuelve a aplicar sola, queda como
pregunta. "Registrar jugadas solas" lo desactiva.

Sobre el vídeo, una barra de fases DP · SP · M1 · BP · M2 · EP con la fase
actual resaltada; clic en una fase posterior salta a ella (`goto_phase`, que
roba si hace falta y se detiene en el primer turno, sin Battle Phase ni Main
Phase 2), "Terminar turno" funciona desde cualquier fase (`end_turn`) y la
barra espaciadora avanza de fase. Los marcadores de LP pasan a esquinas
opuestas y los efectos se acortaron, con interruptor.

Pruebas: `qa_table_duel.py` (16 comprobaciones: la carta en Draw Phase queda
Invocada Normal en M1, Especial cuando la Normal ya se usó, deshacer la deja
como pregunta, una mano un momento no la manda al Cementerio y 3 s sí, saltos
de fase y fin de turno) y en Edge con los tapetes impresos (las tres cartas se
registran solas, sin preguntas, barra en M1, deshacer, EP, espacio termina el
turno).

## Monstruos AR de pie y efectos (27/09/2026)

En `/duelo` los monstruos ya no se pegan planos sobre la carta: se paran sobre
ella. Los 7,245 recortes de YGOPro (close-ups con transparencia) se sirven
ajustados a su contenido en `/cutout/<ref>` (`SpriteOverlay.cutout_png`), así
la fila inferior son los pies. La homografía de cada carta da su centro, su
tamaño en perspectiva y la elipse de su sombra sobre el plano de la carta;
"arriba" es el arriba de la imagen (la cámara mira la mesa desde arriba). Cada
monstruo respira, flota y se balancea con una fase propia, se dibujan de lejos
a cerca para que los cercanos tapen a los lejanos y llevan un anillo en la base
(cian el jugador 1, ámbar el 2). En defensa, agachado con escudo azul; boca
abajo, nada.

Efectos, siempre por cambios del duelo y nunca por la cámara sola: columna de
luz, anillo y partículas al invocar (el monstruo sube desde ella), embestida
hacia el objetivo con destello al resolver un ataque, pedazos que caen al
salir un monstruo del campo, y números de daño o ganancia bajo un marcador de
LP que cuenta animado. Con AR activo el lienzo se repinta en cada fotograma
(60 fps en Edge). Probado en Edge con los tapetes impresos: invocación,
monstruos de pie, LP, ataque y destrucción sin errores.

## Tablero virtual sobre el vídeo (27/09/2026)

Propuesta del usuario: un tablero siempre dibujado sobre el vídeo, sin tapete
ni clics; se elige 1 o 2 jugadores, se ajusta y se fija. `playmat.tcg_layout`
sigue ahora la distribución del tapete oficial vigente (referencia de
2000 × 1167: Zona de Campo, cinco Zonas de Monstruo Principal, Cementerio;
Mazo Extra, cinco de Magia/Trampa con Péndulo en los extremos, Mazo;
Desterradas arriba a la derecha y las dos Zonas de Monstruo Extra encima de M2
y M4). Sólo se usa la geometría, nunca la imagen. Cada ranura mide
exactamente una carta (59 × 86 mm en un tapete de 60 × 35 cm).

`table_duel.virtual_corners` convierte los controles (horizontal, vertical,
tamaño, inclinación = lado lejano / lado cercano, profundidad, giro y, con dos
jugadores, separación) en las esquinas de cada tablero. Con dos jugadores un
solo cuadrilátero abarca la mesa y una sola homografía coloca ambos tableros,
así el del rival sale más pequeño con la perspectiva correcta y girado 180°.
El visor muestra la vista previa al moverlos (`POST /playmat` con `preview`,
que no guarda) y "Fijar tablero" la guarda con los valores de los controles,
que se recuperan al recargar. Pruebas: `qa_table_duel.py` (vista previa sin
cambios, tablero lejano más pequeño, cartas en sus zonas, controles guardados)
y en Edge (vista previa al cargar, el control mueve el tablero, fijar,
recargar, reajustar y 1 jugador).

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
