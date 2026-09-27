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

## 27/09/2026: GPU, bucle en el servidor y geometría en vivo

Computadora con GPU: i9-14900F (32 hilos), RTX 4070 12 GB, controlador 617.14
(CUDA 13.4), Python 3.14.7. Escena de prueba `qa/corner-refinement/current.jpg`
(9 cajas, 8 aceptadas) salvo donde dice "en vivo": teléfono real por stream,
1080p, 10–12 cartas. p50 de 15–30 repeticiones con dos de calentamiento.

| Pieza | Cambio | Medición | Prueba |
|---|---|---|---|
| Encoder en GPU | `research/dequantize_encoder.py` convierte el int8 dinámico (MatMulInteger/ConvInteger, que CUDA ejecuta en CPU) a fp32/fp16 con los **mismos pesos** descuantizados; no hay fp32 publicado de este modelo compacto (el `vit_fp32` de HuggingFace es el ViT principal de 13,820 etiquetas). `YUGIOH_ONNX_DEVICE=cuda` elige CUDA con CPU de respaldo; `YUGIOH_ENCODER` = int8/fp32/fp16 (por defecto int8 en CPU, fp16 en CUDA); un índice por variante (`embeddings-<variante>.npy`) | Análisis completo 1,361 → **145 ms**; encoder de 9 cartas 615 → 15 ms; detector 72 → 12 ms. Deriva lote/imagen 0.0117 → 0.0001 | `qa_vision_pipeline.py`, `qa_inference_host.py` con `.venv-gpu` |
| Misma calidad | Calibración pareada: los **mismos** 446 positivos y 1,336 negativos (`calibrate_acceptance.py --same-scans`) | Regla 0.50/0.25: int8 y fp16 dan 0/1,336 falsas y 431/446 (96.6 %); fotos reales 15/16 aceptadas en ambos; 23 ms por escaneo frente a 1,230 | `qa/calibration-fp16/`, `qa/calibration-fp32/` |
| Encoder genérico | DINOv2 ViT-S/14 y ViT-B/14 (`research/export_dinov2.py`) por el mismo arnés | Recall con 0 falsas 75.6 % y 71.1 % (DRAW2: 97.1 %); 3/16 fotos; 91–96 % de los negativos con similitud ≥ 0.5: ordena bien pero no separa cartas ajenas. **Se queda DRAW2** y el experimento 8 debe ajustar DRAW2 | `qa/calibration-dinov2_vit*/` |
| Evidencia de geometría | Contornos y segmentos en hilos y en paralelo con el detector (no dependen de las cajas) | CPU 4 hilos: 1,361 → 1,183 ms | `qa_card_geometry.py` |
| Refinado por caja | Se probó en paralelo por hilos y se **revirtió**: `snapped_segments` es Python con el GIL | En vivo con 12 cajas: 258–321 ms en hilos frente a 227–282 en serie | — |
| Esquinas del seguimiento | Una caja sobre una pista fresca y estable (IoU ≥ 0.75) toma las esquinas del seguidor (`geometry_status='tracked'`, sin recortes de OCR); la pista caduca a los `REUSE_MAX_AGE_S` y la carta vuelve a refinarse y codificarse. El `snapped_segments` que acaba de fallar en una caja no se reintenta durante 2 s | **En vivo: 430 → 196 ms p50 (p95 591 → 261), 2.4 → 3.8 análisis/s**; 11 de 12 cajas seguidas | `qa_vision_pipeline.py` (esquinas, doble rotación, reintento) |
| Evidencia por zonas | Contornos/LSD sólo alrededor de las cajas pendientes: **descartado** | 3× más rápido (33 vs 100 ms), pero 2–9 de 50 cajas cambiaron estado o movieron esquinas hasta 94 px: los contornos dependen del entorno y el umbral de LSD del tamaño de imagen | — |
| Bucle en el servidor | `AnalysisLoop` analiza el fotograma más nuevo del stream en cuanto termina el anterior; las pestañas hacen long poll a `/analysis?after=N` (204 a los 2 s). Sólo corre mientras alguna pestaña pidió resultados en los últimos 5 s. `--no-server-loop` vuelve a `POST /analyze` | Sin turnos entre pestañas ni envío de JPEG desde el navegador | `qa_server_loop.py` |
| Stream | `read(65536)` bloqueaba hasta juntar 64 KB: la cola de cada fotograma esperaba bytes del siguiente. Ahora `read1` | Parser verificado contra 597 fotogramas reales (10 s): todos coinciden con su `Content-Length` y decodifican. El teléfono entrega 60 fps a 1080p (11.5 MB/s); conviene configurarlo a 30 | `qa_camera_source.py` |
| Piloto en caliente | Guardar el piloto reescribía `catalog.json` y dejaba el índice viejo: los visores seguían con las cartas anteriores y al reiniciar fallaban. Ahora el reconocedor detecta el cambio, reconstruye su índice (escritura atómica) y lo recarga sin reiniciar | Reconstrucción: ~2 s en GPU, ~6 s int8 en este CPU | visor en vivo |

GPU en vivo al 7 %: detector y encoder ya no limitan. Lo que queda es la
geometría (~136 ms p50 en vivo aunque casi todo esté seguido, por la evidencia
de fotograma completo). La salida es YOLO11-pose en GPU (experimento 5), que
necesita las capturas anotadas del protocolo.

## 27/09/2026: reconocer todo el catálogo en lugar del piloto

`catalog.export_full()` escribe `data/full/` con todas las identidades que
tienen una imagen utilizable (mismo filtro y regla de un arte por ilustración
que el piloto): 14,278 identidades y 14,782 referencias, 7,219 con sprite. Con
`YUGIOH_SCOPE=full` (o `start_lab.ps1 -Full`) el reconocedor usa ese índice; las
fotos inscritas se suman en ambos alcances. Índice fp16 en GPU: 3.2 min (el
índice de artes en CPU tardaba 73 min). `rank` corta al reunir cinco
identidades en lugar de recorrer las 14,782 referencias en Python.

| Medida | Piloto (50) | Catálogo completo (14,278) |
|---|---|---|
| Análisis de la escena de 9 cartas, p50 | 124 ms | 137 ms |
| Top-1 en 4,000 escaneos TCGplayer estratificados por rareza | — | **99.3 %** |
| Regla 0.50/0.25: aceptadas correctas / aceptadas equivocadas | — | **96.2 % / 0** |
| Fotos reales de mesa (16 cartas anotadas) | 15 aceptadas, 0 mal | 16/16 top-1, 15 aceptadas, 0 mal |

Informe: `qa/calibration-full-fp16/`. Los "negativos" aceptados (51 de 196) no
son cartas ajenas: son identidades duplicadas del catálogo en sets recientes,
una con el nombre TCG y sin imagen y otra con la traducción previa del OCG y
con imagen ("Crackle Blitzclique" / "Crack Blitzclique", "Hideout in the Sky,
Coulomb" / "Kowloon, Citadel of the Sky"): el reconocedor acierta la carta
física. Queda pendiente unificarlas en el registro. Los 27 top-1 incorrectos
se concentran en Starlight y Ultimate Rare y todos quedan bajo la regla.
