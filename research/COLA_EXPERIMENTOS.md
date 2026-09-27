# Cola de experimentos para la otra PC — 25/09/2026, revisada el 27/09/2026

Diseñados y, cuando fue posible, ya ejecutados una vez en esta PC bajo carga.
En destino: recrear `.venv-eval`, copiar `data/`, `downloads/` (incluidos
`ygoprodeck-art` y `tcgplayer-sample`) y registrar CPU/GPU, versiones e hilos
antes de cada medición. Ninguna cifra de aquí es p50/p95.

Revisión del 27/09/2026: la columna "Estado en esta PC" incorpora lo hecho el
26/09 ([TIEMPO_REAL.md](TIEMPO_REAL.md), [CALIBRACION_ESCANEOS.md](CALIBRACION_ESCANEOS.md)).

| # | Experimento | Script | Estado en esta PC | Qué medir en destino | Decisión que habilita |
|---|---|---|---|---|---|
| 1 | Índice de embeddings con arte recortado (piloto y catálogo completo) | `research/embedding_art_experiment.py` | Hecho: 16/16 top-1 en las tres variantes, incluso entre 14,087 cartas; el arte baja la similitud en el piloto (no sustituir); 0 aceptaciones erróneas. La regla de aceptación ya se calibró contra 1,336 negativos **con el índice del piloto (88 referencias)**, no con el de 14k: `research/calibrate_acceptance.py` es el arnés para repetirlo | Repetir la calibración con el índice completo y con capturas nuevas; tiempo de construcción con GPU | Propuesta a escala de catálogo + verificación SIFT como salida "fuera del deck" |
| 2 | Verificación SIFT de candidatas (`art_verify.py`) | `research/art_verification_experiment.py` | 10/10 correctas, 0 erróneas, 143–380 ms por carta. **Promovida a aceptación** en el visor el 26/09 (`promote_by_art`): un candidato rechazado por score con arte verificado se acepta | p50/p95 por carta, coste de referencias frías, comportamiento con reflejos y fundas, **negativos con cartas fuera del catálogo y artes parecidos** (hoy no hay) | Mantener la promoción o restringirla |
| 3 | Geometría por bordes de croma | `qa_card_geometry.py`, `qa_geometry_recognition.py` | 5/9 resueltas; +45 ms por caja no resuelta. El seguimiento entre análisis (`live_tracking.py`) ahora reutiliza esquinas: la geometría sólo se recalcula en cada análisis | p50/p95 por fotograma con 1–9 cajas; falsas geometrías sobre más fondos y perspectivas; seguimiento con cámara en movimiento | Umbrales de `snapped_segments` y `min_overlap` |
| 4 | OCR sobre escaneos de TCGplayer por rareza | `research/calibrate_set_regions.py` | Hecho con 3,286 verdades exactas y 400 relecturas: la región actual es la mejor de siete variantes (52.7 %); el fallo dominante son confusiones F/E, S/5, O/0, I/1, no la posición | Repetir sobre fotos reales de las mismas impresiones; decidir si se admite búsqueda con equivalencias de glifos **como evidencia separada**, nunca como corrección | Región y umbral por acabado |
| 5 | YOLO11 de cuatro esquinas con datos reales | `research/yolo11_pose/` | Sólo pruebas de humo; sin datos reales. Protocolo de captura listo y puente `from_captures.py` desde la página de capturas | Ver `yolo11_pose/README.md` y `TRANSFERENCIA_GENERAL.md` (P0). Comparar contra OBB + refinamiento + seguimiento, no sólo contra la OBB | Sustituir el detector OBB |
| 6 | Frescura del registro frente a YGOPRODeck | `checkDBVer.php`, `cardinfo.php` | Versión 147.08 (25/09) vs lectura de YGOJSON 07/04. El registro incorpora además Neuron (67,552 fichas) y, desde el 27/09, 42,062 impresiones de TCGplayer con rareza y escaneo | Diseñar importación incremental con procedencia propia; sin español | Ruta de actualización del registro |
| 7 | Restauración de reflejos en GPU | `research/glare-benchmark/` | Sin mejora de identidad en CPU. El problema del foil se resolvió por otra vía (todos los artes en el piloto, aceptación por arte, regla 0.50/0.25): prioridad baja | Ver `glare-benchmark/TRANSFERENCIA.md` | Mantener fuera del vídeo o no |
| 8 | Ajuste contrastivo del encoder con foil y fotos inscritas | pendiente de escribir | Positivos disponibles: escaneos por rareza (46k), fotos inscritas (`enroll_reference.py`); negativos: escaneos fuera del piloto | Recall por rareza con `calibrate_acceptance.py` antes y después; deriva int8 del encoder exportado | Sustituir el encoder DRAW2 |

**27/09/2026 en la PC con GPU:** la calibración de los experimentos 1 y 8 ya
corre en GPU (23 ms por escaneo; `calibrate_acceptance.py --same-scans` repite
exactamente los mismos escaneos para comparar encoders). El encoder fp16
descuantizado da los mismos números que el int8 con la regla 0.50/0.25.
DINOv2 sin ajustar queda muy por debajo (recall 71–76 % con 0 falsas frente a
97 %): el experimento 8 debe partir de DRAW2. Detalle en
[TIEMPO_REAL.md](TIEMPO_REAL.md#27092026-gpu-bucle-en-el-servidor-y-geometría-en-vivo).

Orden sugerido: 1 y 2 (cambian qué referencias usa el reconocedor), luego 3 y
4 (calibración), después 5 (necesita capturas anotadas) y 8 (necesita GPU y
las capturas). El experimento 1 debe repetirse con las mismas capturas de aquí
y con capturas nuevas antes de cambiar el índice en producción; comparar
siempre contra `data/pilot/embeddings.npy`.
