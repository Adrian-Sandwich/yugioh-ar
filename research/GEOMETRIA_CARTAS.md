# Geometría antes de recortes — 25/09/2026

## Problema observado

DRAW2 devuelve cajas rectangulares giradas (OBB), no cuatro esquinas reales
bajo perspectiva. En `qa/corner-refinement/current.jpg`, algunas cajas incluyen
mucha mesa; rectificarlas mueve el serial hacia la madera. Ampliar la región
del serial no resuelve ese error.

## Implementación actual

`card_geometry.py` extrae contornos cerrados y segmentos de borde a resolución
máxima de 1280 píxeles. Busca candidatos compatibles con cada OBB e intersecta
cuatro segmentos observados; no fuerza ángulos rectos en la fotografía. Filtra
tamaño relativo, posición, proporción aparente, convexidad y cobertura de los
lados. Prefiere el candidato exterior a marcos interiores de la ilustración.
Son heurísticas experimentales, no segmentación aprendida ni confianza calibrada.

`ResearchRecognizer.detect` aplica el ajuste antes del encoder. Conserva
`detector_corners` para auditoría y devuelve `geometry_status`, `geometry_iou`
y `geometry_ms`. El IoU mide solapamiento con la caja original, **no precisión**
del borde. El orden de esquinas se conserva y se rota junto con la orientación
seleccionada por el reconocedor.

Si falla, el reconocimiento visual conserva su caja aproximada. El visor la
dibuja en amarillo discontinuo; los ajustes aparecen en verde. El worker de
texto recibe la misma geometría, sin recalcularla. Para backends sin ese campo,
la refina sobre el JPEG original. Con geometría no resuelta omite tanto OCR
como recortes de nombre y serial.

Los recortes siguen siendo regiones anatómicas aproximadas, relativas al
cuadrilátero ajustado. El nombre se lee por OCR independiente: ver [OCR_NOMBRE.md](OCR_NOMBRE.md).
Con orientación dudosa se permite inspeccionar también el extremo opuesto.
No hay detección individual de caracteres o líneas de texto.

## Evidencia y límites

- `qa_card_geometry.py`: perspectiva sintética, conservación de orientación,
  imagen vacía sin OCR, carta cortada y comparación sobre la captura real.
- Ajusta **4 de 9 candidatos** en esa captura. Rechaza las dos cartas cortadas
  y Juicio Solemne parcialmente tapado. También se abstiene en dos cartas que
  una persona sí puede delimitar: no equivale a resolver las nueve.
- Con anotaciones manuales aproximadas, el error medio por esquina en cuatro
  cartas pasa de 37.4→7.5, 37.2→9.5, 17.7→5.9 y 31.9→8.8 píxeles. Una sola
  escena, **no un benchmark general**. Ver `qa/corner-refinement/validation.json`,
  `comparison.jpg` y `crop-comparison.jpg` (antes a izquierda, después a derecha).
- `qa_geometry_recognition.py`: mismas tres fotos y mismos modelos con/sin
  ajuste. Se mantienen las identidades principales de los candidatos ajustados;
  no aumenta el número de identidades aceptadas. Ajuste geométrico: 365–451 ms
  en ejecuciones únicas en esta PC. No se afirma mayor rapidez. Volver a medir
  distribución de latencias y carga en la próxima máquina.
- `qa_passcode.py`, `qa_pipeline_core.py` y `qa_passcode_browser.py` comprueban
  OCR, cola y visor. La fotografía cercana conserva lectura `89631139` tras
  ajustar bordes; el navegador muestra nombre y serial y sigue recibiendo imágenes.

Pendientes: brillos que borran bordes, fundas, cartas juntas, perspectiva fuerte
y confusión con marcos interiores. El filtro de proporción aparente (.55–.80)
puede rechazar cartas válidas con escorzo. Cerca del borde de imagen se exige
un contorno cerrado con corrección pequeña: evita extrapolar partes ausentes,
pero también causa abstenciones. No hay seguimiento óptico de esquinas.

## Ajuste por bordes de croma (25/09/2026, tarde)

Diagnóstico sobre la candidata 4 de `qa/corner-refinement/current.jpg` (Odd-Eyes
foil sobre madera clara, caja del detector un 45 % más alta que la carta): en
luminancia no hay escalón entre el borde plateado y la madera, pero en el canal
b* de Lab la diferencia es de unos 30 niveles. El detector de segmentos
fragmenta ese borde en trozos mucho menores que la mitad del lado y ningún
contorno cerrado lo rodea, así que `line_quads` nunca recibía un candidato.

`card_geometry.snapped_segments` se ejecuta **sólo cuando contornos y segmentos
no resuelven la caja**. Para cada lado muestrea una banda (13 % hacia fuera,
38 % hacia dentro, los mismos límites que los filtros de segmentos) en los tres
canales Lab, calcula una derivada de gaussiana a través de la banda, toma los
máximos locales por canal frente a su propio ruido, y vota líneas por
(canal y signo, pendiente ≤ 15°, desplazamiento). Las celdas más votadas se
verifican: reajuste por mínimos cuadrados, un solo canal y signo, y el tramo
continuo más largo sin huecos mayores de 12 px. Cada línea verificada entra como
un segmento delimitado por sus columnas con apoyo real; `line_quads` conserva su
regla de cobertura ≥ 72 % del lado inferido y `refine_corners` sus filtros de
proporción, IoU, desplazamiento y preferencia por el cuadrilátero exterior. La
única regla relajada en esta ruta es la posición extrema del segmento sobre el
lado de la caja, sustituida por un solapamiento mínimo del 35 %, porque la caja
puede ser mucho mayor que la carta.

El resultado mantiene `geometry_status='contour_refined'` (mismo contrato para OCR
y visor) y añade `geometry_source='snapped_edges'` o `'contours_lines'`.

Evidencia (`qa_card_geometry.py`, `qa/corner-refinement/validation.json`):

- Escena real: **5 de 9** candidatas resueltas (antes 4). La candidata 4 pasa de
  122.6 a 2.3 px de error medio frente a esquinas leídas en recortes ampliados.
  Las cuatro anteriores no cambian (mismo origen y mismos errores). Cartas
  cortadas y Juicio Solemne ocluido siguen sin resolverse.
- Sintético con carta de igual luminancia que la mesa y caja inflada: contornos
  fallan, el ajuste devuelve el borde exterior con error < 4 px y no produce
  nada sobre una mesa vacía.
- Otras siete fotos reales con el detector: dos nuevas resoluciones inspeccionadas
  visualmente y correctas (Juicio Solemne sin ocluir en
  `glare-benchmark/table-original.jpg` y la carta del diagrama de anatomía);
  ninguna geometría existente cambia; ninguna falsa geometría observada.
- `qa_geometry_recognition.py`: mismas identidades principales; la candidata 4
  sube de 0.12 a 0.63 de similitud pero sigue por debajo del umbral de aceptación.
- Coste: en esta PC cargada (descarga de Neuron y cuatro servicios activos), la
  escena de nueve cajas pasa de ~241 a ~332 ms mínimos en seis repeticiones; unos
  45 ms por caja no resuelta. Ejecuciones únicas bajo carga llegaron a 600–900 ms,
  así que la cifra a reportar es la de la próxima PC con p50/p95.

Límites: una sola escena real con anotación manual aproximada; cartas de borde
oscuro sobre madera ya se resolvían por contornos, así que la mejora sólo se ha
observado en bordes de bajo contraste luminoso. Vetas de madera colineales
pueden votar como segmentos largos; hoy las rechazan los filtros de proporción y
cobertura, pero no hay medición de falsas geometrías sobre más fondos. No cambia
el detector ni los umbrales del reconocedor.

## PCA / vector principal propuesto por el usuario

PCA estima el eje largo sobre puntos de una instancia ya separada.
[OpenCV muestra su uso para orientación](https://docs.opencv.org/4.13.0/da/d94/samples_2cpp_2tutorial_code_2ml_2introduction_to_pca_2introduction_to_pca_8cpp-example.html).
No separa por sí mismo carta–mesa o carta–carta, no devuelve cuatro esquinas
y deja ambigüedad de 180 grados. Aplicarlo a todos los bordes de una ROI mezcla
mesa, ilustración y cartas vecinas.

**PCA no está implementado ni medido todavía.** Evaluarlo como apoyo al eje
después de aislar cada carta y compararlo con el eje de la OBB. No imponer sus
ejes ortogonales como los cuatro lados bajo perspectiva. Para oclusiones,
evaluar segmentación por instancia o un modelo de esquinas con indicadores
de visibilidad; distinguir esquinas inferidas de observadas.

Próxima evaluación: anotar esquinas y visibilidad en sesiones con distintas
alturas/inclinaciones, fondos, fundas, reflejos y superposiciones. Medir error
de esquina, recortes que contienen texto, falsas aceptaciones de geometría,
abstenciones y latencias p50/p95. Separar sesiones de ajuste y validación.
