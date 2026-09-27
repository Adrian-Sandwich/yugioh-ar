# Protocolo de capturas con cartas reales

Fecha: 26/09/2026. Es el procedimiento para fotografiar cartas físicas de
modo que el detector, el identificador y el OCR se puedan evaluar, y más
adelante entrenar, con datos separados por sesión. Se ejecuta en una tarde con
un teléfono y las siete cartas que ya existen. Garantiza datos reproducibles y
sin fuga entre particiones; **no** garantiza precisión: las muestras serán
pequeñas y hay que reportarlas con sus denominadores.

## Las siete cartas disponibles

| Carta | Impresión | Acabado | Por qué interesa |
|---|---|---|---|
| Dragón Blanco de Ojos Azules (2 o 3 copias) | LOB-EN001 / otras | común y otras | Copias iguales en la mesa; referencia bien resuelta (0.92 a 0.95) |
| Dragón Negro de Ojos Rojos | SDJ-001 | común | Marco de monstruo clásico, se acepta hoy |
| Mago Oscuro | DUPO-EN101 | Ultra Rare foil | Foil; el piloto tiene ahora sus 9 artes; similitud 0.66 a 0.76 |
| Dragón de Péndulo de Ojos Anómalos | DUPO-EN105 | Ultra Rare foil | Marco Péndulo (escalas), foil; similitud 0.42 a 0.63 |
| Dragón de Péndulo de Ojos Anómalos | CT12-EN001 | Platinum Secret Rare | Marco plateado; la copia más difícil |
| Número 39: Utopía | (Xyz) | | Marco Xyz negro, texto claro sobre oscuro |
| Juicio Solemne | | | Carta de trampa: sin ATK/DEF, layout distinto |

## Montaje

- **Teléfono** con IP Webcam (`http://IP:8080`) para vídeo, o la cámara del
  teléfono para fotos sueltas. Bloquear exposición y enfoque cuando la app lo
  permita; desactivar HDR y estabilización digital (cambian la geometría).
- **Distancia.** El OCR del serial exige unos 7 px por dígito
  (`passcode_ocr.py`: `estimated_digit_height = altura_nativa_de_carta * 0.015`,
  y el lector se omite por debajo de 7 px; ver PIPELINE_ESTADO.md, "OCR por
  tamaño"). Eso obliga a que la carta mida **al menos 467 px de alto en la
  imagen**. Con una carta de 86 mm y un campo vertical de unos 50°, orientativo:

  | Resolución del fotograma | Altura mínima de carta | Distancia aproximada |
  |---|---|---|
  | 1920 × 1080 (vídeo) | 467 px = 43 % del alto | unos 20 cm |
  | 4000 × 3000 (foto) | 467 px = 16 % del alto | unos 55 a 60 cm |

  El campo de visión varía por teléfono; la cifra fiable es la que muestra el
  panel de lectura del visor ("Carta original: W × H px · dígitos ≈ N px").
  Ajustar la altura hasta ver dígitos ≥ 7 px. Para el detector y el
  identificador basta con menos: 200 px de alto ya se rectifican.
- **Encuadre.** Carta completa y separada de las demás. Una carta cortada por
  el borde del cuadro no se rectifica ni se verifica por arte (ARTE_YGOPRODECK.md:
  "las dos cajas cortadas por el borde no se rectifican"). Dejar un margen de al
  menos un 5 % del cuadro alrededor de cada carta. El visor marca en rojo las
  cortadas.
- **Luz.** Una fuente lateral difusa; nunca la lámpara detrás del teléfono
  (reflejo especular en foil). Anotar `condición = reflejo` cuando el brillo
  tape parte del arte o del texto; no restaurar la foto.
- **Fondos.** Madera clara (como la escena existente), tela oscura y un tapete
  con dibujo. El ajuste de bordes por croma se diseñó sobre madera clara; los
  otros fondos son los que faltan.

## Diseño de sesiones

Doce situaciones (PLAN_MEJORA_INTEGRAL.md, sección 5) × tres sesiones. Una
sesión es un bloque de fotos tomadas seguidas con el mismo montaje. Nombrarla
`<dispositivo>_<fondo>_<fecha>_<n>` (letras, números, guiones y guiones bajos:
`capture_dataset.py` rechaza otros caracteres), por ejemplo
`pixel_madera_20260927_1`.

| # | Situación | Qué variar |
|---|---|---|
| 1 | Vista superior | cámara perpendicular, 4 a 7 cartas |
| 2 | Inclinación oblicua 1 | unos 30° |
| 3 | Inclinación oblicua 2 | unos 50°, escorzo fuerte |
| 4 | Lejos | cartas de 200 a 300 px de alto (sin OCR posible) |
| 5 | Cerca | una o dos cartas, dígitos ≥ 7 px |
| 6 | Giro de cámara | 90° y 180° respecto a la situación 1 |
| 7 | Giro de cartas | cartas en ángulos distintos, alguna boca abajo |
| 8 | Movimiento de cámara | vídeo de 15 s barriendo la mesa |
| 9 | Movimiento de cartas | vídeo: una mano mueve una carta, la coloca, la retira |
| 10 | Oclusión | mano o carta tapando parte de otra |
| 11 | Brillo y funda | las foil con reflejo visible; una carta con funda |
| 12 | Cruce y sustitución | dos Ojos Anómalos que se cruzan; una carta sustituida en el mismo sitio |

Negativos obligatorios en cada sesión: dos o tres cartas que **no** sean de
Yu-Gi-Oh!, un reverso de carta, un rectángulo que no es carta (caja, teléfono).
Se anotan con identidad "Desconocida / fuera del catálogo".

Particiones: sesiones 1 y 2 en `train`, la sesión 3 en `test`. Una sesión no
puede repartirse entre particiones; `capture_dataset.py` lo impide. La copia
física se registra en `physical_copy` (`odd_eyes_dupo`, `odd_eyes_ct12`,
`blue_eyes_1`, `blue_eyes_2`, ...) para poder medir el seguimiento de copias
iguales. Vídeos: guardar el archivo y extraer fotogramas cada 0.5 s como fotos
de la misma sesión; no contar fotogramas vecinos como ejemplos independientes.

## Anotación

Página de capturas: http://127.0.0.1:8768/capture (la sirve
`catalog_server.py`; arranca con `start_lab.ps1`). **Marcar todas las cartas
completas de cada foto**, no sólo las interesantes: el detector se entrena con
estas mismas fotos y una carta sin marcar cuenta como falso negativo. Las
sesiones en que se cumplió eso se declaran al convertir para YOLO11
(`research/yolo11_pose/from_captures.py --exhaustive-sessions ...`). Los
negativos (fotos sin cartas) se anotan con el anotador de pose
(http://127.0.0.1:8767/pose-annotator), no aquí. Por cada carta de la foto:

1. Marcar las cuatro esquinas **empezando por la superior izquierda de la
   carta** (no de la imagen) y siguiendo el borde. Ese orden es el que el
   rectificador espera; una carta girada 180° empieza por la esquina que sería
   la superior izquierda si la carta estuviera derecha.
2. Identidad: elegir la carta del piloto o "Desconocida / fuera del catálogo".
   Cartas boca abajo: desconocida, con `condición` = "oclusión parcial" si sólo
   se ve el reverso parcialmente.
3. Idioma impreso sólo si se ha leído físicamente; "Sin verificar" si no.
4. Arte o variante y acabado / rareza: texto libre (`artwork`, `finish`), por
   ejemplo `DUPO-EN105 Ultra Rare`. No inventar rarezas.
5. Sesión, partición, copia física y condición (normal, sombra, reflejo,
   funda, distante, oclusión parcial).

No etiquetar un serial como legible en una toma lejana aunque se conozca por
una foto cercana: la verdad del serial va en la anotación de la foto donde se
lee. Los campos que guarda `capture_dataset.py` son `id`, `image`,
`image_sha256`, `width`, `height`, `session`, `split`, `card_id`,
`printed_language`, `corners`, `physical_copy`, `artwork`, `finish`,
`condition` y `label_source`.

## Entregable

- `data/pilot/captures/<sha256>.jpg` (originales sin tocar) y
  `data/pilot/captures/annotations.jsonl` (una línea por carta anotada).
- Un archivo `SESIONES.md` en la misma carpeta con fecha, teléfono, app,
  resolución, altura aproximada, luz y fondo de cada sesión.
- Copia de seguridad de la carpeta completa antes de cualquier reconstrucción
  del catálogo (las anotaciones son decisiones humanas, no se regeneran).
- Para compartirlas: ver CONTRIBUTING.es.md ("Fotos de cartas reales").

Después de anotar las sesiones `train`, las fotos de tus cartas pueden pasar a
ser referencias del reconocedor con `enroll_reference.py`, y el índice se
reconstruye con `vision_onnx.py`. Las sesiones `test` nunca se inscriben.

## Qué medir con este material

Con `evaluate_pilot.py` y los scripts de `research/`: acierto top-1 y
aceptaciones por situación, falsas aceptaciones en los negativos, error de
esquinas frente a la anotación, lectura exacta del serial sólo en las fotos
donde los dígitos superan 7 px, y cambios de identidad entre copias en los
vídeos de cruce. Reportar siempre n por estrato; los estratos sin ejemplos se
declaran vacíos, no se extrapolan.
