# Cola de experimentos para la otra PC — 25/09/2026

Diseñados y, cuando fue posible, ya ejecutados una vez en esta PC bajo carga.
En destino: recrear `.venv-eval`, copiar `data/`, `downloads/` (incluidos
`ygoprodeck-art` y `tcgplayer-sample`) y registrar CPU/GPU, versiones e hilos
antes de cada medición. Ninguna cifra de aquí es p50/p95.

| # | Experimento | Script | Estado en esta PC | Qué medir en destino | Decisión que habilita |
|---|---|---|---|---|---|
| 1 | Índice de embeddings con arte recortado (piloto y catálogo completo) | `research/embedding_art_experiment.py` | Hecho: 16/16 top-1 en las tres variantes, incluso entre 14,087 cartas; el arte baja la similitud en el piloto (no sustituir); 0 aceptaciones erróneas. `qa/embedding-art/comparison.json`, índice cacheado en `data/pilot/art_index-*.npy` | Repetir con negativos (cartas fuera del catálogo) y capturas nuevas; recalibrar la regla de aceptación para 14k distractores; tiempo de construcción con GPU | Propuesta a escala de catálogo + verificación SIFT como salida "fuera del deck" |
| 2 | Verificación SIFT de candidatas (`art_verify.py`) | `research/art_verification_experiment.py` | 10/10 correctas, 0 erróneas, 143–380 ms por carta | p50/p95 por carta, coste de referencias frías, comportamiento con reflejos y fundas, negativos con cartas fuera del catálogo | Mantener como evidencia o promover a aceptación visual |
| 3 | Geometría por bordes de croma | `qa_card_geometry.py`, `qa_geometry_recognition.py` | 5/9 resueltas; +45 ms por caja no resuelta | p50/p95 por fotograma con 1–9 cajas; falsas geometrías sobre más fondos y perspectivas | Umbrales de `snapped_segments` y `min_overlap` |
| 4 | OCR sobre escaneos de TCGplayer por rareza | `research/tcgplayer_sample_check.py` | 104/120 set code, 114/120 passcode en escaneos limpios | Repetir por rareza y edición; ajustar `SET_REGIONS` al borde blanco del escaneo; medir con fotos reales de las mismas impresiones | Calibrar regiones y umbrales de set/serial por acabado |
| 5 | YOLO11 de cuatro esquinas con datos reales | `research/yolo11_pose/` | Sólo pruebas de humo; sin datos reales | Ver `yolo11_pose/README.md` y `TRANSFERENCIA_GENERAL.md` (P0) | Sustituir el detector OBB |
| 6 | Frescura del registro frente a YGOPRODeck | `checkDBVer.php`, `cardinfo.php` | Versión 147.08 (25/09) vs lectura de YGOJSON 07/04 | Diseñar importación incremental con procedencia propia; sin español | Ruta de actualización del registro |
| 7 | Restauración de reflejos en GPU | `research/glare-benchmark/` | Sin mejora de identidad en CPU | Ver `glare-benchmark/TRANSFERENCIA.md` | Mantener fuera del vídeo o no |

Orden sugerido: 1 y 2 (cambian qué referencias usa el reconocedor), luego 3 y
4 (calibración), después 5 (necesita capturas anotadas). El experimento 1
debe repetirse con las mismas capturas de aquí y con capturas nuevas antes de
cambiar el índice en producción; comparar siempre contra `data/pilot/embeddings.npy`.
