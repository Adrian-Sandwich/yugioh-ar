# Calibración de la regla de aceptación (embeddings) — escaneos TCGplayer

Fecha: 2026-09-27 14:03. Semilla 20260926. Modelo sha256 `fc76920af7aed675…`. Índice piloto: 88 referencias, 50 identidades.

Escaneos: 47824 productos, 46058 con imagen, 41897 con una sola identidad, 28637 con ancho ≥ 400 px. Positivos disponibles 446, evaluados 446; negativos disponibles 28191, evaluados 1336 (muestra estratificada por rareza).

Tiempo: 0.02 s por escaneo (dos orientaciones, medido sobre 20 escaneos), positivos 0.1 min, negativos 0.2 min, fotos 1 s, total 0.3 min.

**Aviso:** los escaneos son fotos planas y uniformes, un dominio más cercano a las referencias del piloto que una foto de mesa. La tasa de falsas aceptaciones y el recall son optimistas para mesas reales.

## Reglas

| Regla | similitud ≥ | margen ≥ | Falsas aceptaciones (negativos) | Recall (positivos aceptados y correctos) | Positivos aceptados erróneos |
|---|---|---|---|---|---|
| current_0.80_0.07 | 0.80 | 0.07 | 1/1336 (0.07%) | 360/446 (80.7%) | 0 |
| best_fa_le_1pct | 0.70 | 0.08 | 12/1336 (0.90%) | 386/446 (86.5%) | 0 |
| best_fa_le_0_5pct | 0.74 | 0.08 | 6/1336 (0.45%) | 380/446 (85.2%) | 0 |
| best_fa_zero | 0.80 | 0.10 | 0/1336 (0.00%) | 337/446 (75.6%) | 0 |

Top-1 correcto en positivos sin regla: 427/446. Similitud de la identidad correcta: mediana 0.8827, mín. 0.3135. Negativos: similitud top-1 mediana 0.6716, p95 0.7722, máx. 0.8324; margen mediana 0.0207, p95 0.0683.

## Recall por rareza (positivos: aceptados correctos / n)

| Rareza | n | top-1 correcto | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|---|
| Collector's Rare | 4 | 4 | 3/4 | 3/4 | 3/4 | 3/4 |
| Common / Short Print | 48 | 48 | 47/48 | 48/48 | 48/48 | 47/48 |
| Duel Terminal Technology Common | 3 | 3 | 3/3 | 3/3 | 3/3 | 3/3 |
| Duel Terminal Technology Ultra Rare | 4 | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| Ghost Rare | 6 | 6 | 1/6 | 2/6 | 1/6 | 1/6 |
| Parallel Rare | 2 | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| Platinum Secret Rare | 14 | 13 | 7/14 | 9/14 | 8/14 | 7/14 |
| Prismatic Collector's Rare | 1 | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Prismatic Secret Rare | 9 | 6 | 1/9 | 2/9 | 2/9 | 1/9 |
| Prismatic Ultimate Rare | 1 | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Quarter Century Secret Rare | 26 | 25 | 12/26 | 16/26 | 15/26 | 8/26 |
| Rare | 19 | 18 | 16/19 | 17/19 | 17/19 | 15/19 |
| Secret Rare | 32 | 28 | 20/32 | 24/32 | 23/32 | 17/32 |
| Starfoil Rare | 2 | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| Starlight Rare | 16 | 10 | 3/16 | 6/16 | 5/16 | 3/16 |
| Super Rare | 19 | 19 | 18/19 | 19/19 | 19/19 | 17/19 |
| Ultimate Rare | 7 | 6 | 5/7 | 6/7 | 6/7 | 5/7 |
| Ultra Rare | 57 | 56 | 56/57 | 54/57 | 54/57 | 49/57 |
| unknown | 176 | 175 | 158/176 | 167/176 | 166/176 | 151/176 |

## Falsas aceptaciones por rareza (negativos: aceptados / n)

| Rareza | n | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|
| 10000 Secret Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Collector's Rare | 78 | 0/78 | 0/78 | 0/78 | 0/78 |
| Common | 16 | 0/16 | 0/16 | 0/16 | 0/16 |
| Common / Short Print | 78 | 0/78 | 0/78 | 0/78 | 0/78 |
| Duel Terminal Normal Parallel Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Duel Terminal Super Parallel Rare | 2 | 1/2 | 1/2 | 1/2 | 0/2 |
| Duel Terminal Technology Common | 78 | 0/78 | 1/78 | 1/78 | 0/78 |
| Duel Terminal Technology Ultra Rare | 26 | 0/26 | 0/26 | 0/26 | 0/26 |
| Duel Terminal Ultra Parallel Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Ghost Rare | 24 | 0/24 | 0/24 | 0/24 | 0/24 |
| Gold Secret Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Parallel Rare | 27 | 0/27 | 0/27 | 0/27 | 0/27 |
| Platinum Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Collector's Rare | 77 | 0/77 | 1/77 | 1/77 | 0/77 |
| Prismatic Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Ultimate Rare | 77 | 0/77 | 2/77 | 0/77 | 0/77 |
| Quarter Century Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Rare | 77 | 0/77 | 1/77 | 1/77 | 0/77 |
| Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Shatterfoil Rare | 2 | 0/2 | 0/2 | 0/2 | 0/2 |
| Starfoil Rare | 77 | 0/77 | 2/77 | 0/77 | 0/77 |
| Starlight Rare | 77 | 0/77 | 1/77 | 1/77 | 0/77 |
| Super Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Ultimate Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Ultra Rare | 77 | 0/77 | 1/77 | 0/77 | 0/77 |
| unknown | 77 | 0/77 | 2/77 | 1/77 | 0/77 |

## Fotos reales anotadas (embedding_art_experiment.py)

16 candidatas con verdad y rectificables de 19 anotadas en 5 fotos (3 omitidas por geometría; fotos ausentes: ninguna). Top-1 correcto 15/16.

| Regla | Aceptadas correctas | Aceptadas erróneas |
|---|---|---|
| current_0.80_0.07 (0.80/0.07) | 3/16 | 0 |
| best_fa_le_1pct (0.70/0.08) | 6/16 | 0 |
| best_fa_le_0_5pct (0.74/0.08) | 5/16 | 0 |
| best_fa_zero (0.80/0.10) | 3/16 | 0 |

| Foto | cand. | verdad | top-1 | similitud | margen |
|---|---|---|---|---|---|
| current.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.675 | 0.104 |
| current.jpg | 3 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.759 | 0.111 |
| current.jpg | 4 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.731 | 0.069 |
| current.jpg | 5 | Mago Oscuro | Mago Oscuro | 0.865 | 0.172 |
| current.jpg | 6 | Número 39: Utopía | Número 39: Utopía | 0.558 | 0.089 |
| current.jpg | 7 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.714 | 0.032 |
| current.jpg | 8 | Juicio Solemne | Juicio Solemne | 0.555 | 0.035 |
| carta-2026-09-25T04-13-54-278Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.771 | 0.087 |
| carta-2026-09-25T04-15-11-032Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.707 | 0.070 |
| carta-2026-09-25T04-15-19-512Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.857 | 0.133 |
| table-original.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.660 | 0.080 |
| table-original.jpg | 2 | Juicio Solemne | Juicio Solemne | 0.701 | 0.187 |
| table-original.jpg | 3 | Mago Oscuro | Mago Oscuro | 0.824 | 0.155 |
| table-original.jpg | 4 | Número 39: Utopía | Número 39: Utopía | 0.595 | 0.066 |
| table-original.jpg | 5 | Dragón de Péndulo de Ojos Anómalos | Sabia Ciberso (ERROR) | 0.482 | 0.001 |
| table-original.jpg | 6 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.787 | 0.057 |

## Rejilla (falsas aceptaciones % / recall %) — filas similitud, columnas margen

| sim \ margen | 0.00 | 0.10 | 0.20 | 0.30 | 0.40 |
|---|---|---|---|---|---|
| 0.40 | 99.70 / 95.7 | 1.80 / 83.0 | 0.00 / 41.5 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.44 | 99.03 / 95.7 | 1.80 / 83.0 | 0.00 / 41.5 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.48 | 97.08 / 95.7 | 1.80 / 83.0 | 0.00 / 41.5 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.52 | 94.54 / 95.5 | 1.80 / 83.0 | 0.00 / 41.5 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.56 | 87.35 / 95.5 | 1.65 / 83.0 | 0.00 / 41.5 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.60 | 79.49 / 95.5 | 1.20 / 83.0 | 0.00 / 41.5 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.64 | 64.67 / 94.6 | 1.20 / 82.3 | 0.00 / 41.5 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.68 | 46.48 / 93.9 | 0.82 / 82.1 | 0.00 / 41.3 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.72 | 26.05 / 92.4 | 0.30 / 81.4 | 0.00 / 41.3 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.76 | 8.23 / 87.4 | 0.07 / 79.1 | 0.00 / 40.8 | 0.00 / 15.5 | 0.00 / 1.6 |
| 0.80 | 1.20 / 81.6 | 0.00 / 75.6 | 0.00 / 39.9 | 0.00 / 15.2 | 0.00 / 1.6 |
| 0.84 | 0.00 / 69.5 | 0.00 / 67.0 | 0.00 / 37.0 | 0.00 / 15.0 | 0.00 / 1.6 |
| 0.88 | 0.00 / 52.2 | 0.00 / 51.3 | 0.00 / 32.7 | 0.00 / 14.1 | 0.00 / 1.3 |

Rejilla completa en `acceptance.json` (`grid`).
