# Calibración de la regla de aceptación (embeddings) — escaneos TCGplayer

Fecha: 2026-09-27 15:52. Semilla 20260926. Modelo sha256 `5a764445fdecb9ab…`. Índice piloto: 14782 referencias, 14274 identidades.

Escaneos: 47824 productos, 46058 con imagen, 44235 con una sola identidad, 29101 con ancho ≥ 400 px. Positivos disponibles 28905, evaluados 4000; negativos disponibles 196, evaluados 196 (muestra estratificada por rareza).

Tiempo: 0.07 s por escaneo (dos orientaciones, medido sobre 20 escaneos), positivos 2.1 min, negativos 0.1 min, fotos 1 s, total 5.2 min.

**Aviso:** los escaneos son fotos planas y uniformes, un dominio más cercano a las referencias del piloto que una foto de mesa. La tasa de falsas aceptaciones y el recall son optimistas para mesas reales.

## Reglas

| Regla | similitud ≥ | margen ≥ | Falsas aceptaciones (negativos) | Recall (positivos aceptados y correctos) | Positivos aceptados erróneos |
|---|---|---|---|---|---|
| current_0.80_0.07 | 0.80 | 0.07 | 28/196 (14.29%) | 3217/4000 (80.4%) | 1 |
| best_fa_le_1pct | — | — | ninguna regla de la rejilla cumple | — | — |
| best_fa_le_0_5pct | — | — | ninguna regla de la rejilla cumple | — | — |
| best_fa_zero | — | — | ninguna regla de la rejilla cumple | — | — |

Top-1 correcto en positivos sin regla: 3973/4000. Similitud de la identidad correcta: mediana 0.8919, mín. 0.0226. Negativos: similitud top-1 mediana 0.313, p95 0.8669, máx. 0.942; margen mediana 0.0418, p95 0.585.

## Recall por rareza (positivos: aceptados correctos / n)

| Rareza | n | top-1 correcto | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|---|
| 10000 Secret Rare | 1 | 1 | 1/1 | — | — | — |
| Collector's Rare | 226 | 225 | 200/226 | — | — | — |
| Common / Short Print | 263 | 261 | 255/263 | — | — | — |
| Duel Terminal Normal Parallel Rare | 1 | 1 | 1/1 | — | — | — |
| Duel Terminal Super Parallel Rare | 2 | 2 | 1/2 | — | — | — |
| Duel Terminal Technology Common | 131 | 131 | 122/131 | — | — | — |
| Duel Terminal Technology Ultra Rare | 31 | 31 | 28/31 | — | — | — |
| Duel Terminal Ultra Parallel Rare | 1 | 1 | 0/1 | — | — | — |
| Emblazoned Secret Rare | 1 | 1 | 1/1 | — | — | — |
| Emblazoned Ultra Rare | 1 | 1 | 1/1 | — | — | — |
| Ghost Rare | 31 | 31 | 4/31 | — | — | — |
| Gold Rare | 3 | 3 | 1/3 | — | — | — |
| Gold Secret Rare | 2 | 2 | 2/2 | — | — | — |
| Grand Master Rare | 18 | 17 | 0/18 | — | — | — |
| Parallel Rare | 39 | 39 | 37/39 | — | — | — |
| Platinum Secret Rare | 263 | 263 | 222/263 | — | — | — |
| Premium Gold Rare | 61 | 61 | 58/61 | — | — | — |
| Prismatic Collector's Rare | 263 | 263 | 255/263 | — | — | — |
| Prismatic Secret Rare | 263 | 262 | 205/263 | — | — | — |
| Prismatic Ultimate Rare | 263 | 263 | 245/263 | — | — | — |
| Promo | 4 | 3 | 1/4 | — | — | — |
| Quarter Century Secret Rare | 263 | 262 | 206/263 | — | — | — |
| Rare | 263 | 263 | 258/263 | — | — | — |
| Secret Pharaoh’s Rare | 21 | 20 | 18/21 | — | — | — |
| Secret Rare | 262 | 261 | 212/262 | — | — | — |
| Shatterfoil Rare | 7 | 7 | 6/7 | — | — | — |
| Starfoil Rare | 143 | 143 | 141/143 | — | — | — |
| Starlight Rare | 262 | 254 | 104/262 | — | — | — |
| Super Rare | 262 | 260 | 219/262 | — | — | — |
| Ultimate Rare | 262 | 258 | 73/262 | — | — | — |
| Ultra Pharaoh’s Rare | 21 | 20 | 16/21 | — | — | — |
| Ultra Rare | 262 | 262 | 228/262 | — | — | — |
| unknown | 104 | 101 | 96/104 | — | — | — |

## Falsas aceptaciones por rareza (negativos: aceptados / n)

| Rareza | n | current_0.80_0.07 | best_fa_le_1pct | best_fa_le_0_5pct | best_fa_zero |
|---|---|---|---|---|---|
| Common / Short Print | 101 | 11/101 | — | — | — |
| Parallel Rare | 1 | 0/1 | — | — | — |
| Secret Rare | 12 | 4/12 | — | — | — |
| Starlight Rare | 24 | 2/24 | — | — | — |
| Super Rare | 34 | 7/34 | — | — | — |
| Ultra Rare | 24 | 4/24 | — | — | — |

## Fotos reales anotadas (embedding_art_experiment.py)

16 candidatas con verdad y rectificables de 19 anotadas en 5 fotos (3 omitidas por geometría; fotos ausentes: ninguna). Top-1 correcto 16/16.

| Regla | Aceptadas correctas | Aceptadas erróneas |
|---|---|---|
| current_0.80_0.07 (0.80/0.07) | 12/16 | 0 |

| Foto | cand. | verdad | top-1 | similitud | margen |
|---|---|---|---|---|---|
| current.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.944 | 0.586 |
| current.jpg | 3 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.960 | 0.605 |
| current.jpg | 4 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.655 | 0.289 |
| current.jpg | 5 | Mago Oscuro | Mago Oscuro | 0.956 | 0.595 |
| current.jpg | 6 | Número 39: Utopía | Número 39: Utopía | 0.947 | 0.533 |
| current.jpg | 7 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.743 | 0.468 |
| current.jpg | 8 | Juicio Solemne | Juicio Solemne | 0.456 | 0.165 |
| carta-2026-09-25T04-13-54-278Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.925 | 0.541 |
| carta-2026-09-25T04-15-11-032Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.930 | 0.557 |
| carta-2026-09-25T04-15-19-512Z.jpg | 0 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.919 | 0.544 |
| table-original.jpg | 1 | Dragón Blanco de Ojos Azules | Dragón Blanco de Ojos Azules | 0.943 | 0.576 |
| table-original.jpg | 2 | Juicio Solemne | Juicio Solemne | 0.898 | 0.607 |
| table-original.jpg | 3 | Mago Oscuro | Mago Oscuro | 0.941 | 0.570 |
| table-original.jpg | 4 | Número 39: Utopía | Número 39: Utopía | 0.910 | 0.482 |
| table-original.jpg | 5 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.617 | 0.258 |
| table-original.jpg | 6 | Dragón de Péndulo de Ojos Anómalos | Dragón de Péndulo de Ojos Anómalos | 0.800 | 0.551 |

## Rejilla (falsas aceptaciones % / recall %) — filas similitud, columnas margen

| sim \ margen | 0.00 | 0.10 | 0.20 | 0.30 | 0.40 |
|---|---|---|---|---|---|
| 0.40 | 38.78 / 98.1 | 32.65 / 97.8 | 28.57 / 97.2 | 23.98 / 95.0 | 20.41 / 91.1 |
| 0.44 | 37.24 / 97.8 | 31.63 / 97.5 | 28.57 / 97.2 | 23.98 / 95.0 | 20.41 / 91.1 |
| 0.48 | 33.67 / 97.4 | 29.59 / 97.1 | 27.55 / 97.0 | 23.98 / 95.0 | 20.41 / 91.1 |
| 0.52 | 30.61 / 96.7 | 26.53 / 96.4 | 26.02 / 96.4 | 23.47 / 95.0 | 20.41 / 91.1 |
| 0.56 | 27.55 / 96.0 | 25.00 / 95.6 | 24.49 / 95.6 | 22.45 / 94.8 | 20.41 / 91.1 |
| 0.60 | 25.51 / 94.8 | 23.98 / 94.5 | 23.47 / 94.5 | 21.94 / 94.0 | 20.41 / 91.1 |
| 0.64 | 23.47 / 93.5 | 22.45 / 93.2 | 22.45 / 93.2 | 20.92 / 92.9 | 20.41 / 90.8 |
| 0.68 | 20.41 / 91.9 | 19.90 / 91.6 | 19.90 / 91.6 | 19.39 / 91.3 | 19.39 / 90.0 |
| 0.72 | 18.37 / 89.5 | 17.86 / 89.2 | 17.86 / 89.2 | 17.86 / 89.1 | 17.86 / 88.3 |
| 0.76 | 16.33 / 86.3 | 16.33 / 86.0 | 16.33 / 86.0 | 16.33 / 86.0 | 16.33 / 85.5 |
| 0.80 | 14.29 / 80.7 | 14.29 / 80.4 | 14.29 / 80.4 | 14.29 / 80.4 | 14.29 / 80.0 |
| 0.84 | 8.67 / 71.0 | 8.67 / 70.8 | 8.67 / 70.8 | 8.67 / 70.7 | 8.67 / 70.6 |
| 0.88 | 3.06 / 55.4 | 3.06 / 55.2 | 3.06 / 55.2 | 3.06 / 55.2 | 3.06 / 55.0 |

Rejilla completa en `acceptance.json` (`grid`).
