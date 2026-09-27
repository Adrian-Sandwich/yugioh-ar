# Calibración de la regla de aceptación (embeddings) — escaneos TCGplayer

Fecha: 2026-09-27 14:04. Semilla 20260926. Modelo sha256 `10dee721d80d4b4b…`. Índice piloto: 88 referencias, 50 identidades.

Escaneos: 47824 productos, 46058 con imagen, 41897 con una sola identidad, 28637 con ancho ≥ 400 px. Positivos disponibles 446, evaluados 446; negativos disponibles 28191, evaluados 1336 (muestra estratificada por rareza).

Tiempo: 0.02 s por escaneo (dos orientaciones, medido sobre 20 escaneos), positivos 0.1 min, negativos 0.2 min, fotos 1 s, total 0.4 min.

**Aviso:** los escaneos son fotos planas y uniformes, un dominio más cercano a las referencias del piloto que una foto de mesa. La tasa de falsas aceptaciones y el recall son optimistas para mesas reales.

## Reglas

| Regla | similitud ≥ | margen ≥ | Falsas aceptaciones (negativos) | Recall (positivos aceptados y correctos) | Positivos aceptados erróneos |
|---|---|---|---|---|---|
| current_0.80_0.07 | 0.80 | 0.07 | 4/1336 (0.30%) | 345/446 (77.4%) | 0 |
| best_fa_le_1pct | 0.78 | 0.06 | 11/1336 (0.82%) | 367/446 (82.3%) | 0 |
| best_fa_le_0_5pct | 0.80 | 0.06 | 5/1336 (0.37%) | 357/446 (80.0%) | 0 |
| best_fa_zero | 0.82 | 0.08 | 0/1336 (0.00%) | 317/446 (71.1%) | 0 |

Top-1 correcto en positivos sin regla: 435/446. Similitud de la identidad correcta: mediana 0.8852, mín. 0.3797. Negativos: similitud top-1 mediana 0.7016, p95 0.8395, máx. 0.8871; margen mediana 0.0161, p95 0.0713.

## Recall por rareza (positivos: aceptados correctos / n)

| Rareza | n | top-1 correcto | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|---|
| Collector's Rare | 4 | 4 | 3/4 | 3/4 | 3/4 | 3/4 |
| Common / Short Print | 48 | 48 | 47/48 | 47/48 | 47/48 | 47/48 |
| Duel Terminal Technology Common | 3 | 3 | 2/3 | 3/3 | 2/3 | 2/3 |
| Duel Terminal Technology Ultra Rare | 4 | 4 | 4/4 | 4/4 | 4/4 | 4/4 |
| Ghost Rare | 6 | 6 | 2/6 | 3/6 | 2/6 | 2/6 |
| Parallel Rare | 2 | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| Platinum Secret Rare | 14 | 13 | 7/14 | 8/14 | 7/14 | 5/14 |
| Prismatic Collector's Rare | 1 | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Prismatic Secret Rare | 9 | 7 | 1/9 | 1/9 | 1/9 | 1/9 |
| Prismatic Ultimate Rare | 1 | 1 | 1/1 | 1/1 | 1/1 | 1/1 |
| Quarter Century Secret Rare | 26 | 26 | 8/26 | 12/26 | 10/26 | 5/26 |
| Rare | 19 | 19 | 18/19 | 19/19 | 19/19 | 16/19 |
| Secret Rare | 32 | 30 | 16/32 | 19/32 | 18/32 | 11/32 |
| Starfoil Rare | 2 | 2 | 2/2 | 2/2 | 2/2 | 2/2 |
| Starlight Rare | 16 | 13 | 1/16 | 2/16 | 2/16 | 1/16 |
| Super Rare | 19 | 19 | 18/19 | 19/19 | 18/19 | 18/19 |
| Ultimate Rare | 7 | 6 | 6/7 | 6/7 | 6/7 | 4/7 |
| Ultra Rare | 57 | 56 | 54/57 | 55/57 | 55/57 | 48/57 |
| unknown | 176 | 175 | 152/176 | 160/176 | 157/176 | 144/176 |

## Falsas aceptaciones por rareza (negativos: aceptados / n)

| Rareza | n | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|
| 10000 Secret Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Collector's Rare | 78 | 0/78 | 0/78 | 0/78 | 0/78 |
| Common | 16 | 0/16 | 0/16 | 0/16 | 0/16 |
| Common / Short Print | 78 | 1/78 | 1/78 | 1/78 | 0/78 |
| Duel Terminal Normal Parallel Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Duel Terminal Super Parallel Rare | 2 | 0/2 | 0/2 | 0/2 | 0/2 |
| Duel Terminal Technology Common | 78 | 0/78 | 0/78 | 0/78 | 0/78 |
| Duel Terminal Technology Ultra Rare | 26 | 0/26 | 1/26 | 1/26 | 0/26 |
| Duel Terminal Ultra Parallel Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Ghost Rare | 24 | 0/24 | 0/24 | 0/24 | 0/24 |
| Gold Secret Rare | 1 | 0/1 | 0/1 | 0/1 | 0/1 |
| Parallel Rare | 27 | 0/27 | 0/27 | 0/27 | 0/27 |
| Platinum Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Collector's Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Secret Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Prismatic Ultimate Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Quarter Century Secret Rare | 77 | 1/77 | 1/77 | 1/77 | 0/77 |
| Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Secret Rare | 77 | 0/77 | 1/77 | 0/77 | 0/77 |
| Shatterfoil Rare | 2 | 0/2 | 0/2 | 0/2 | 0/2 |
| Starfoil Rare | 77 | 1/77 | 4/77 | 1/77 | 0/77 |
| Starlight Rare | 77 | 0/77 | 1/77 | 0/77 | 0/77 |
| Super Rare | 77 | 1/77 | 2/77 | 1/77 | 0/77 |
| Ultimate Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| Ultra Rare | 77 | 0/77 | 0/77 | 0/77 | 0/77 |
| unknown | 77 | 0/77 | 0/77 | 0/77 | 0/77 |

## Fotos reales anotadas (embedding_art_experiment.py)

16 candidatas con verdad y rectificables de 19 anotadas en 5 fotos (3 omitidas por geometría; fotos ausentes: ninguna). Top-1 correcto 14/16.

| Regla | Aceptadas correctas | Aceptadas erróneas |
|---|---|---|
| current_0.80_0.07 (0.80/0.07) | 5/16 | 0 |
| best_fa_le_1pct (0.78/0.06) | 6/16 | 0 |
| best_fa_le_0_5pct (0.80/0.06) | 6/16 | 0 |
| best_fa_zero (0.82/0.08) | 3/16 | 0 |

| Foto | cand. | verdad | top-1 | similitud | margen |
|---|---|---|---|---|---|
| current.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.679 | 0.083 |
| current.jpg | 3 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.764 | 0.047 |
| current.jpg | 4 | Dragón de Péndulo de Ojos Anómalos | Decodificador Hablador (ERROR) | 0.656 | 0.009 |
| current.jpg | 5 | Mago Oscuro | Mago Oscuro | 0.878 | 0.141 |
| current.jpg | 6 | Número 39: Utopía | Número 39: Utopía | 0.679 | 0.035 |
| current.jpg | 7 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.854 | 0.067 |
| current.jpg | 8 | Juicio Solemne | Dragón Blanco de Ojos Azules (ERROR) | 0.667 | 0.062 |
| carta-2026-09-25T04-13-54-278Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.851 | 0.038 |
| carta-2026-09-25T04-15-11-032Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.849 | 0.045 |
| carta-2026-09-25T04-15-19-512Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.884 | 0.078 |
| table-original.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.720 | 0.037 |
| table-original.jpg | 2 | Juicio Solemne | Juicio Solemne | 0.807 | 0.372 |
| table-original.jpg | 3 | Mago Oscuro | Mago Oscuro | 0.838 | 0.149 |
| table-original.jpg | 4 | Número 39: Utopía | Número 39: Utopía | 0.650 | 0.046 |
| table-original.jpg | 5 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.505 | 0.027 |
| table-original.jpg | 6 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.855 | 0.101 |

## Rejilla (falsas aceptaciones % / recall %) — filas similitud, columnas margen

| sim \ margen | 0.00 | 0.10 | 0.20 | 0.30 | 0.40 |
|---|---|---|---|---|---|
| 0.40 | 98.13 / 97.5 | 2.17 / 74.0 | 0.07 / 37.4 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.44 | 96.48 / 97.5 | 2.10 / 74.0 | 0.07 / 37.4 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.48 | 93.34 / 97.5 | 2.10 / 74.0 | 0.07 / 37.4 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.52 | 88.62 / 97.5 | 2.10 / 74.0 | 0.07 / 37.4 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.56 | 83.16 / 97.3 | 1.80 / 74.0 | 0.07 / 37.4 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.60 | 75.08 / 96.9 | 1.65 / 74.0 | 0.07 / 37.4 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.64 | 66.92 / 96.2 | 1.35 / 73.5 | 0.07 / 37.4 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.68 | 56.89 / 95.1 | 0.90 / 72.9 | 0.07 / 37.2 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.72 | 43.41 / 92.6 | 0.37 / 71.7 | 0.07 / 36.8 | 0.00 / 11.7 | 0.00 / 3.4 |
| 0.76 | 29.87 / 88.8 | 0.22 / 70.0 | 0.00 / 35.6 | 0.00 / 11.2 | 0.00 / 3.4 |
| 0.80 | 16.09 / 83.2 | 0.07 / 66.6 | 0.00 / 34.3 | 0.00 / 11.0 | 0.00 / 3.4 |
| 0.84 | 5.01 / 72.0 | 0.00 / 59.9 | 0.00 / 31.6 | 0.00 / 10.3 | 0.00 / 3.1 |
| 0.88 | 0.22 / 53.4 | 0.00 / 46.0 | 0.00 / 24.0 | 0.00 / 9.0 | 0.00 / 2.9 |

Rejilla completa en `acceptance.json` (`grid`).
