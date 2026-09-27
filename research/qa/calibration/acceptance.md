# Calibración de la regla de aceptación (embeddings) — escaneos TCGplayer

Fecha: 2026-09-26 23:58. Semilla 20260926. Modelo sha256 `5b847a2bb23b99ac…`. Índice piloto: 88 referencias, 50 identidades.

Escaneos: 47824 productos, 46058 con imagen, 41897 con una sola identidad, 28637 con ancho ≥ 400 px. Positivos disponibles 446, evaluados 446; negativos disponibles 28191, evaluados 1336 (muestra estratificada por rareza).

Tiempo: 1.23 s por escaneo (dos orientaciones, medido sobre 20 escaneos), positivos 7.6 min, negativos 19.0 min, fotos 19 s, total 27.3 min.

**Aviso:** los escaneos son fotos planas y uniformes, un dominio más cercano a las referencias del piloto que una foto de mesa. La tasa de falsas aceptaciones y el recall son optimistas para mesas reales.

## Reglas

| Regla | similitud ≥ | margen ≥ | Falsas aceptaciones (negativos) | Recall (positivos aceptados y correctos) | Positivos aceptados erróneos |
|---|---|---|---|---|---|
| current_0.80_0.07 | 0.80 | 0.07 | 0/1336 (0.00%) | 406/446 (91.0%) | 0 |
| best_fa_le_1pct | 0.40 | 0.24 | 1/1336 (0.07%) | 436/446 (97.8%) | 0 |
| best_fa_le_0_5pct | 0.40 | 0.24 | 1/1336 (0.07%) | 436/446 (97.8%) | 0 |
| best_fa_zero | 0.48 | 0.24 | 0/1336 (0.00%) | 433/446 (97.1%) | 0 |

Top-1 correcto en positivos sin regla: 445/446. Similitud de la identidad correcta: mediana 0.9555, mín. 0.1406. Negativos: similitud top-1 mediana 0.1445, p95 0.2186, máx. 0.4455; margen mediana 0.0248, p95 0.0872.

## Recall por rareza (positivos: aceptados correctos / n)

| Rareza | n | top-1 correcto | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|---|
| Collector's Rare | 4 | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| Common / Short Print | 48 | 48 | 48/48 | 48/48 | 48/48 | 48/48 |
| Duel Terminal Technology Common | 3 | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Duel Terminal Technology Ultra Rare | 4 | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| Ghost Rare | 6 | 6 | 2/6 | 6/6 | 6/6 | 6/6 |
| Parallel Rare | 2 | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| Platinum Secret Rare | 14 | 14 | 13/14 | 14/14 | 14/14 | 14/14 |
| Prismatic Collector's Rare | 1 | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Prismatic Secret Rare | 9 | 9 | 3/9 | 9/9 | 9/9 | 9/9 |
| Prismatic Ultimate Rare | 1 | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Quarter Century Secret Rare | 26 | 26 | 26/26 | 26/26 | 26/26 | 26/26 |
| Rare | 19 | 19 | 19/19 | 19/19 | 19/19 | 19/19 |
| Secret Rare | 32 | 32 | 26/32 | 29/32 | 29/32 | 29/32 |
| Starfoil Rare | 2 | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| Starlight Rare | 16 | 15 | 8/16 | 10/16 | 10/16 | 10/16 |
| Super Rare | 19 | 19 | 18/19 | 19/19 | 19/19 | 19/19 |
| Ultimate Rare | 7 | 7 | 5/7 | 7/7 | 7/7 | 6/7 |
| Ultra Rare | 57 | 57 | 56/57 | 57/57 | 57/57 | 56/57 |
| unknown | 176 | 176 | 165/176 | 175/176 | 175/176 | 174/176 |

## Falsas aceptaciones por rareza (negativos: aceptados / n)

| Rareza | n | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|
| 10000 Secret Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Collector's Rare | 78 | 0/78 | 0/78 | 0/78 | 0/78 |
| Common | 16 | 0/16 | 0/16 | 0/16 | 0/16 |
| Common / Short Print | 78 | 0/78 | 0/78 | 0/78 | 0/78 |
| Duel Terminal Normal Parallel Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Duel Terminal Super Parallel Rare | 2 | 0/2 | 0/2 | 0/2 | 0/2 |
| Duel Terminal Technology Common | 78 | 0/78 | 0/78 | 0/78 | 0/78 |
| Duel Terminal Technology Ultra Rare | 26 | 0/26 | 0/26 | 0/26 | 0/26 |
| Duel Terminal Ultra Parallel Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Ghost Rare | 24 | 0/24 | 0/24 | 0/24 | 0/24 |
| Gold Secret Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Parallel Rare | 27 | 0/27 | 0/27 | 0/27 | 0/27 |
| Platinum Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Collector's Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Ultimate Rare | 77 | 0/77 | 1/77 | 1/77 | 0/77 |
| Quarter Century Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Shatterfoil Rare | 2 | 0/2 | 0/2 | 0/2 | 0/2 |
| Starfoil Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Starlight Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Super Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Ultimate Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Ultra Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| unknown | 77 | 0/77 | 0/77 | 0/77 | 0/77 |

## Fotos reales anotadas (embedding_art_experiment.py)

16 candidatas con verdad y rectificables de 19 anotadas en 5 fotos (3 omitidas por geometría; fotos ausentes: ninguna). Top-1 correcto 16/16.

| Regla | Aceptadas correctas | Aceptadas erróneas |
|---|---|---|
| current_0.80_0.07 (0.80/0.07) | 11/16 | 0 |
| best_fa_le_1pct (0.40/0.24) | 16/16 | 0 |
| best_fa_le_0_5pct (0.40/0.24) | 16/16 | 0 |
| best_fa_zero (0.48/0.24) | 15/16 | 0 |

| Foto | cand. | verdad | top-1 | similitud | margen |
|---|---|---|---|---|---|
| current.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.938 | 0.671 |
| current.jpg | 3 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.957 | 0.590 |
| current.jpg | 4 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.620 | 0.487 |
| current.jpg | 5 | Mago Oscuro | Mago Oscuro | 0.945 | 0.649 |
| current.jpg | 6 | Número 39: Utopía | Número 39: Utopía | 0.944 | 0.824 |
| current.jpg | 7 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.728 | 0.576 |
| current.jpg | 8 | Juicio Solemne | Juicio Solemne | 0.457 | 0.283 |
| carta-2026-09-25T04-13-54-278Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.918 | 0.532 |
| carta-2026-09-25T04-15-11-032Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.928 | 0.554 |
| carta-2026-09-25T04-15-19-512Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.914 | 0.537 |
| table-original.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.940 | 0.567 |
| table-original.jpg | 2 | Juicio Solemne | Juicio Solemne | 0.892 | 0.742 |
| table-original.jpg | 3 | Mago Oscuro | Mago Oscuro | 0.920 | 0.628 |
| table-original.jpg | 4 | Número 39: Utopía | Número 39: Utopía | 0.903 | 0.791 |
| table-original.jpg | 5 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.583 | 0.428 |
| table-original.jpg | 6 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.781 | 0.627 |

## Rejilla (falsas aceptaciones % / recall %) — filas similitud, columnas margen

| sim \ margen | 0.00 | 0.10 | 0.20 | 0.30 | 0.40 |
|---|---|---|---|---|---|
| 0.40 | 0.30 / 97.8 | 0.22 / 97.8 | 0.07 / 97.8 | 0.07 / 96.6 | 0.00 / 95.5 |
| 0.44 | 0.15 / 97.5 | 0.15 / 97.5 | 0.07 / 97.5 | 0.07 / 96.6 | 0.00 / 95.5 |
| 0.48 | 0.00 / 97.1 | 0.00 / 97.1 | 0.00 / 97.1 | 0.00 / 96.4 | 0.00 / 95.5 |
| 0.52 | 0.00 / 96.6 | 0.00 / 96.6 | 0.00 / 96.6 | 0.00 / 96.2 | 0.00 / 95.5 |
| 0.56 | 0.00 / 96.6 | 0.00 / 96.6 | 0.00 / 96.6 | 0.00 / 96.2 | 0.00 / 95.5 |
| 0.60 | 0.00 / 96.4 | 0.00 / 96.4 | 0.00 / 96.4 | 0.00 / 96.0 | 0.00 / 95.3 |
| 0.64 | 0.00 / 96.2 | 0.00 / 96.2 | 0.00 / 96.2 | 0.00 / 96.0 | 0.00 / 95.3 |
| 0.68 | 0.00 / 95.1 | 0.00 / 95.1 | 0.00 / 95.1 | 0.00 / 95.1 | 0.00 / 94.6 |
| 0.72 | 0.00 / 93.9 | 0.00 / 93.9 | 0.00 / 93.9 | 0.00 / 93.9 | 0.00 / 93.7 |
| 0.76 | 0.00 / 92.8 | 0.00 / 92.8 | 0.00 / 92.8 | 0.00 / 92.8 | 0.00 / 92.6 |
| 0.80 | 0.00 / 91.0 | 0.00 / 91.0 | 0.00 / 91.0 | 0.00 / 91.0 | 0.00 / 91.0 |
| 0.84 | 0.00 / 88.3 | 0.00 / 88.3 | 0.00 / 88.3 | 0.00 / 88.3 | 0.00 / 88.3 |
| 0.88 | 0.00 / 83.6 | 0.00 / 83.6 | 0.00 / 83.6 | 0.00 / 83.6 | 0.00 / 83.6 |

Rejilla completa en `acceptance.json` (`grid`).
