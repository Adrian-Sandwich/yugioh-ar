# Tiempo real sin GPU: bucle del visor, aceptación por arte y reutilización de identidad

Fecha: 26/09/2026. Cambios al reconocedor y al visor que no dependen de GPU ni
de datos nuevos, con sus mediciones y sus pruebas. Todo se probó en esta PC
(8 núcleos lógicos, gráficos Intel) con otros procesos activos; los tiempos
son observaciones, no benchmarks.

## Diagnóstico de partida

En la escena real de siete cartas (`qa/corner-refinement/current.jpg`) el
embedding acertaba el top-1 en todos los recortes, pero Ojos Anómalos (0.42 a
0.63) y Mago Oscuro (0.66 a 0.76) quedaban bajo el umbral 0.80 por ser foil
frente a referencias planas. La verificación SIFT del arte las confirmaba
(65, 120, 57 y 295, 219 inliers) y el visor no lo usaba para aceptar. Cada
análisis costaba 2 pasadas del encoder por carta a 624 ms cada una, y el AR
sólo se movía al terminar un análisis.

## Qué cambió

| Pieza | Cambio | Medición | Prueba |
|---|---|---|---|
| Encoder (`vision_onnx.py`) | 4 hilos ONNX en lugar de 2 (`YUGIOH_ONNX_THREADS`); una pasada por lotes por orientación | 1 imagen: 624 → 474 ms; lote de 4: 395 ms/imagen. 8 hilos empeora (873 ms) | `qa_vision_pipeline.py` |
| Orientación | La segunda orientación sólo se calcula si la primera no llega a 0.90 | En 19 recortes reales la orientación incorrecta llegó como mucho a 0.815 y la correcta ganó por ≥ 0.122 | ídem |
| Lotes int8 | Los scores del grafo cuantizado difieren entre lote y una imagen | deriva máxima 0.012 en la escena; identidades y rotaciones iguales | ídem |
| Índice vacío | Sin candidatos se reporta la caja sin identidad en vez de fallar (`IndexError` latente) | | ídem |
| Piloto | Todas las ilustraciones por identidad (`catalog.export_pilot(max_artworks=None)`): 63 → 88 referencias; Ojos Anómalos 3 artes, Mago Oscuro 9 | | índice reconstruido |
| Aceptación por arte | `promote_by_art`: un candidato rechazado con el mismo `card_id` que la ilustración verificada (SIFT ≥ 30 inliers, margen 2×) en una caja solapada (IoU ≥ 0.5) y reciente (≤ 4 s) se acepta como `art_verified`; el score no cambia | Con los datos de la escena habría aceptado las 5 cajas rechazadas | ídem (`promote_by_art`) |
| Reutilización | Una pista estable y verificada hace ≤ 8 s que solapa ≥ 0.75 con la caja nueva conserva su identidad sin codificar; pasado ese plazo se reidentifica para detectar sustituciones | 9 cartas: 1 reutilizada = 1 codificación menos | ídem |
| Seguimiento (`live_tracking.py`) | Lucas-Kanade piramidal sobre 35 puntos interiores por carta + homografía RANSAC; historial de fotogramas para colocar un análisis tardío y reproducir el flujo hasta el presente. Una sola llamada de flujo para todas las cartas; salto adaptativo de fotogramas si el seguidor va atrasado (`max_load` 0.5) | Sintético 720p, una carta: 6 ms y ≤ 2 px. Sonda de diez cartas a 1080p: 45 ms por fotograma (14 ms son decodificar el JPEG, 7 el flujo, 6 las homografías), error medio 3 px y máximo 5 px en 40 fotogramas. En vivo con el teléfono a ~20 fps el seguidor procesa uno de cada dos fotogramas cuando hay muchas cartas | `qa_live_tracking.py` |
| Fuente MJPEG (`camera_source.py`) | Hilo lector de `/video` de IP Webcam; `/snapshot` sirve el último fotograma y cae a `shot.jpg` si el stream lleva 2 s sin fotogramas | 54 fotogramas, reconexión automática | `qa_camera_source.py` |
| Cabecera `X-Tracks` | `/snapshot` lleva las pistas del fotograma exacto; el navegador dibuja nombres y sprites por fotograma | sondeo del navegador a 66 ms en lugar de 200 | ídem, `qa_live_camera.py` |
| Sprites en el navegador | `/sprite/<ref>` sirve el lienzo PNG; WebGL con coordenadas proyectivas (pesos por intersección de diagonales) lo deforma sobre las esquinas. `/analyze` ya no codifica la capa PNG de fotograma completo | | `qa_live_camera.py`, `qa_sprite_cache.py` |
| Inferencia aislada (`inference_host.py`) | Reconocedor en proceso hijo (`spawn`) con tubería; una llamada que supere el límite mata y reinicia el hijo y devuelve 502 sin bloquear el vídeo | arranque 4 s; reinicio tras cuelgue forzado con el mismo resultado | `qa_inference_host.py` |
| Cartas cortadas | Los candidatos con `geometry_status = frame_edge` se marcan en rojo con el aviso de moverlas dentro del cuadro | | visor |
| Inscripción (`enroll_reference.py`) | Fotos anotadas de la partición `train` rectificadas al lienzo 421 × 614 como referencias adicionales (`data/pilot/enrolled.json`); `test` nunca se inscribe; el índice detecta el cambio y exige reconstrucción | | `qa_enroll_reference.py` |

Comando de arranque: `camera_viewer.py --backend embedding --ar` usa por
defecto stream, seguimiento y proceso aislado; `--no-stream`, `--no-tracking`,
`--no-isolate` los desactivan. `start_lab.ps1` no cambia.

## Lo que sigue sin medir

- Latencia de extremo a extremo con el teléfono real y el stream MJPEG: los
  66 ms de sondeo son el ritmo del navegador, no la edad del fotograma. En la
  primera prueba en vivo (27/09) el stream entregó ~20 fps con 44 ms de edad
  del último fotograma; el seguidor con diez cartas iba a 100 ms por fotograma
  antes de agrupar las llamadas de flujo, y el parser MJPEG cortaba fotogramas
  en la miniatura EXIF. Ambas cosas se corrigieron ese día con sus pruebas.
- Seguimiento con cartas reales, manos, reflejos y cámara en movimiento: la
  prueba es sintética.
- El efecto de la promoción por arte sobre falsas aceptaciones: hoy no hay
  negativos con arte parecido en las pruebas.
- La deriva int8 entre lote y una imagen (0.012) se acepta porque no cambia
  identidades en la escena; con umbrales calibrados hay que volver a mirarla.

Regla de aceptación: ver [CALIBRACION_ESCANEOS.md](CALIBRACION_ESCANEOS.md).
