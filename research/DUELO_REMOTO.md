# Duelo remoto con AR (plan, 28/09/2026)

Cambio de alcance acordado con el usuario: además del duelo en una sola mesa,
apuntar a un duelo **remoto** con AR, donde los jugadores toman y resuelven la
mayoría de las decisiones y el sistema se integra lo mejor posible. Nada de
esto está construido todavía: antes de avanzar hay más cosas que resolver
(sección "Pendiente de resolver").

## Decisiones tomadas

| Tema | Decisión |
|---|---|
| Dónde se procesa | Cada jugador reconoce **su propia mesa en local**, con su cámara a resolución completa y su GPU, y manda todo ya procesado. |
| Qué ve el rival | **Los dos tableros en AR**: su mesa y la tuya, cada una con sus monstruos y efectos. |
| Videollamada | Integrarse con Meet o Zoom como etapa temprana: nuestra vista procesada entra a la llamada como cámara virtual. Procesar el video que llega por la llamada queda como plan B (rival sin GPU), a medir antes de comprometerse. |
| Servidor | Etapa temprana: sin servidor propio o con un relevo mínimo. Después, un servidor en Go. |
| Reglas | Modo **notario**: registra todo, avisa cuando algo normalmente no se puede, bloquea sólo lo imposible (zona ocupada, carta que no existe). Conteos de mano y mazo son estimados. |
| Objeción | Un **diálogo de alerta discreto**, sólo por si acaso; nada disruptivo. |
| Modo local | Se queda: local (una cámara, uno o dos tapetes) y remoto comparten motor, vista y AR. |
| Conexión | Primero construirlo bien en nuestra vista; después se ve cómo se conecta. |

## Por qué encaja con lo que ya existe

- `duel_engine` es un registro de eventos: el estado se deriva de repetirlo
  (`Duel.replay`). En red, los jugadores se mandan **eventos**, no estados.
- Con el modo notario el motor ya no arbitra reglas, así que el servidor en Go
  no tiene que reimplementar Yu-Gi-Oh!: le basta con **ordenar y repartir
  eventos** (recibir, numerar, reenviar). Eso lo vuelve un proyecto pequeño.
- El modo "un tapete" ya es exactamente el lado de un jugador remoto.

## Procesar en origen frente a procesar la llamada

- **En origen (elegido):** video nítido; hoy el catálogo completo reconoce
  cartas reales a 0.82-0.87 de similitud, ~135 ms por análisis en GPU. Por el
  canal de eventos viajan unos cuantos bytes por jugada.
- **Sobre la llamada (plan B):** Meet y Zoom comprimen, suelen bajar a 720p o
  menos, la calidad cambia con la conexión y el diseño de la ventana se mueve.
  Se espera bastante menos precisión; hay que medirlo con una grabación real
  de una llamada antes de usarlo.

## Temas de fondo que cambian en remoto

1. **Autoría.** Cada evento lleva quién lo propuso; el rival lo ve y puede
   marcarlo con el diálogo de alerta.
2. **Información oculta.** Tu reconocedor puede ver la cara de una carta justo
   antes de que la pongas boca abajo. El estado compartido no debe filtrar su
   identidad; de la mano sólo se comparte el conteo, estimado.
3. **Confianza.** Remoto depende de la buena fe; la cámara y el registro sirven
   para revisar, no para impedir trampas. No prometer un árbitro.
4. **Dos fuentes de verdad.** Cada mesa física es la verdad de su lado; ningún
   lado mueve las cartas del otro.

## Etapas propuestas

1. **Notario + autoría** en el motor y el panel: avisos en lugar de rechazos,
   autor en cada evento, diálogo de alerta discreto.
2. **Dos asientos en una PC**: dos visores en modo un tapete (celular y webcam,
   o una captura fija) con un registro compartido; en nuestra vista, el lado
   rival dibujado en AR en la mitad lejana del tablero.
3. **Videollamada**: nuestra vista como cámara virtual (OBS Virtual Camera o
   similar) y un relevo mínimo de eventos desde la PC de un jugador, con un
   túnel (Tailscale o Cloudflare). Aparte, la prueba de calidad del plan B.
4. **Servidor en Go**: relevo de eventos con salas.

## Pendiente de resolver (antes de construir)

El usuario indicó que hay más cosas por resolver; se irán anotando aquí.

- Diseño del lado rival en AR dentro de nuestra vista (cómo se dibuja su tablero
  sin cámara: imágenes de sus cartas en sus zonas, sus monstruos, sus efectos).
- Qué validaciones del motor pasan a aviso y cuáles siguen bloqueando en modo
  notario (lista de `_need` de `duel_engine.py`: reglas de juego frente a
  imposibles físicos).
- Qué hace el diálogo de alerta al aceptarse (¿deshacer, marcar como dudosa,
  pedir al autor corregir?).
- Seguimiento de a dónde va una carta que sale de una zona (Cementerio, Mazo o
  mano), anotado como futuro el 27/09/2026.
- Datos de mecánicas desde BabelCDB (acordado antes, sin empezar).

## Datos de referencia

- Magias de Campo en el registro local (`card_facts`, 28/09/2026): **334** de
  2,838 Magias (Normales 1,070; de Juego Rápido 560; Continuas 509; de Equipo
  282; de Ritual 83). Con legalidad TCG registrada: 293 (286 ilimitadas, 4
  limitadas, 2 semilimitadas, 1 prohibida) y 3 sin publicar en TCG; 36 sin
  datos TCG (en su mayoría de OCG o del anime). Reconocibles con el catálogo
  completo del recognizer: 329.
