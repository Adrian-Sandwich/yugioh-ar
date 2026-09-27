# Calibración de regiones y umbral del OCR de set code — escaneos TCGplayer

Fecha: 2026-09-27 00:03. Semilla 20260926. Lecturas evaluadas: 16340 (scan-numbers.jsonl).

## A. Lecturas existentes contra el número exacto de TCGplayer

| Grupo | n | leídas | correctas | erróneas | ilegibles | precisión de las leídas | cobertura |
|---|---|---|---|---|---|---|---|
| all | 3286 | 1957 | 1590 | 367 | 1329 | 0.8125 | 0.4839 |
| rarity:Common / Short Print | 1028 | 692 | 581 | 111 | 336 | 0.8396 | 0.5652 |
| rarity:Mosaic Rare | 4 | 0 | 0 | 0 | 4 | None | 0.0 |
| rarity:Platinum Secret Rare | 12 | 2 | 1 | 1 | 10 | 0.5 | 0.0833 |
| rarity:Prismatic Collector's Rare | 161 | 35 | 30 | 5 | 126 | 0.8571 | 0.1863 |
| rarity:Prismatic Secret Rare | 144 | 101 | 83 | 18 | 43 | 0.8218 | 0.5764 |
| rarity:Prismatic Ultimate Rare | 162 | 66 | 48 | 18 | 96 | 0.7273 | 0.2963 |
| rarity:Promo | 2 | 0 | 0 | 0 | 2 | None | 0.0 |
| rarity:Quarter Century Secret Rare | 43 | 9 | 8 | 1 | 34 | 0.8889 | 0.186 |
| rarity:Rare | 172 | 154 | 133 | 21 | 18 | 0.8636 | 0.7733 |
| rarity:Secret Rare | 148 | 123 | 111 | 12 | 25 | 0.9024 | 0.75 |
| rarity:Shatterfoil Rare | 225 | 59 | 29 | 30 | 166 | 0.4915 | 0.1289 |
| rarity:Starfoil Rare | 161 | 114 | 76 | 38 | 47 | 0.6667 | 0.472 |
| rarity:Starlight Rare | 57 | 8 | 7 | 1 | 49 | 0.875 | 0.1228 |
| rarity:Super Rare | 382 | 212 | 184 | 28 | 170 | 0.8679 | 0.4817 |
| rarity:Ultimate Rare | 24 | 1 | 1 | 0 | 23 | 1.0 | 0.0417 |
| rarity:Ultra Rare | 561 | 381 | 298 | 83 | 180 | 0.7822 | 0.5312 |
| width:200px | 326 | 12 | 6 | 6 | 314 | 0.5 | 0.0184 |
| width:300px | 402 | 149 | 85 | 64 | 253 | 0.5705 | 0.2114 |
| width:400px | 900 | 725 | 630 | 95 | 175 | 0.869 | 0.7 |
| width:500px | 1085 | 685 | 538 | 147 | 400 | 0.7854 | 0.4959 |
| width:600px | 571 | 384 | 330 | 54 | 187 | 0.8594 | 0.5779 |
| width:700px | 2 | 2 | 1 | 1 | 0 | 0.5 | 0.5 |

Confusiones más frecuentes (leído → verdad):

| leído | verdad | veces |
|---|---|---|
| F | E | 429 |
| S | 5 | 228 |
| O | 0 | 126 |
| I | 1 | 63 |
| P | E | 57 |
| 1 | P | 36 |
| 0 | 6 | 15 |
| I | P | 12 |
| R | B | 12 |
| 1 | 4 | 12 |
| 1 | L | 12 |
| T | P | 12 |
| B | E | 12 |
| Q | 0 | 9 |
| L | 1 | 9 |

Con verdad inferida por el registro (más débil): {'n': 36, 'status:unreadable': 36, 'accuracy_of_reads': None, 'coverage': 0.0}

## B. Variantes de región y umbral (muestra estratificada por rareza)

Muestra: 400 escaneos ≥ 400 px con número exacto; 35.4 min.

| Variante | regiones | umbral 0.8 | umbral 0.85 | umbral 0.9 |
|---|---|---|---|---|
| baseline | [[0.52, 0.714, 0.96, 0.752], [0.52, 0.742, 0.96, 0.785], [0.52, 0.91, 0.96, 0.949]] | 0.527 (211/400) | 0.527 (211/400) | 0.507 (203/400) |
| shift_-0.030 | [[0.52, 0.6839999999999999, 0.96, 0.722], [0.52, 0.712, 0.96, 0.755], [0.52, 0.88, 0.96, 0.9189999999999999]] | 0.517 (207/400) | 0.515 (206/400) | 0.487 (195/400) |
| shift_-0.015 | [[0.52, 0.699, 0.96, 0.737], [0.52, 0.727, 0.96, 0.77], [0.52, 0.895, 0.96, 0.9339999999999999]] | 0.388 (155/400) | 0.398 (159/400) | 0.385 (154/400) |
| shift_+0.015 | [[0.52, 0.729, 0.96, 0.767], [0.52, 0.757, 0.96, 0.8], [0.52, 0.925, 0.96, 0.964]] | 0.152 (61/400) | 0.142 (57/400) | 0.128 (51/400) |
| shift_+0.030 | [[0.52, 0.744, 0.96, 0.782], [0.52, 0.772, 0.96, 0.8150000000000001], [0.52, 0.9400000000000001, 0.96, 0.979]] | 0.007 (3/400) | 0.007 (3/400) | 0.005 (2/400) |
| wider_5pct | [[0.47000000000000003, 0.714, 1.0, 0.752], [0.47000000000000003, 0.742, 1.0, 0.785], [0.47000000000000003, 0.91, 1.0, 0.949]] | 0.490 (196/400) | 0.480 (192/400) | 0.470 (188/400) |
| taller_1pct | [[0.52, 0.704, 0.96, 0.762], [0.52, 0.732, 0.96, 0.795], [0.52, 0.9, 0.96, 0.959]] | 0.355 (142/400) | 0.345 (138/400) | 0.312 (125/400) |

Conclusión automática: la mejor variante es baseline con umbral 0.85 (0.527 frente a 0.527 de la configuración actual); la ganancia es menor de 2 puntos: no se justifica cambiar SET_REGIONS

Los escaneos son fotos planas con borde blanco; una foto de mesa tiene perspectiva y menos píxeles. Esta calibración dice qué región lee mejor el escaneo, no la foto real.
