# Calibración con escaneos de TCGplayer: regla de aceptación y regiones del set code

Fecha: 26 y 27 de septiembre de 2026. Scripts `research/calibrate_acceptance.py`
y `research/calibrate_set_regions.py`; resultados completos en
`qa/calibration/acceptance.{json,md}` y `qa/calibration/set-regions.{json,md}`.
Los escaneos de TCGplayer (fotos planas y uniformes de una impresión concreta)
son el primer conjunto grande con negativos que ha tenido el proyecto. Son un
dominio más fácil que una foto de mesa: **todas las cifras de aquí son
optimistas para la cámara real**, tanto las falsas aceptaciones como el recall.

## Regla de aceptación del embedding

Método: cada escaneo entero se trata como el recorte rectificado de
producción (224 × 224, orientaciones 0 y 180, mejor puntuación), contra el
índice del piloto (88 referencias, 50 identidades). Positivos: los 446
escaneos (≥ 400 px de ancho, una sola identidad reconstruida) de cartas del
piloto. Negativos: 1,336 escaneos de cartas fuera del piloto, estratificados
por rareza para que los acabados foil estén representados. Rejilla de reglas:
similitud 0.40 a 0.90 y margen 0.00 a 0.40, paso 0.02. 27 minutos de CPU.

| Regla | Falsas aceptaciones (1,336 negativos) | Recall (446 positivos) | Fotos reales aceptadas (16 recortes) |
|---|---|---|---|
| anterior: similitud ≥ 0.80, margen ≥ 0.07 | 0 | 406 (91.0 %) | 11 |
| frontera sin falsas: ≥ 0.48, ≥ 0.24 | 0 | 433 (97.1 %) | 15 |
| ≥ 0.40, ≥ 0.24 | 1 (0.07 %) | 436 (97.8 %) | 16 |
| **adoptada: ≥ 0.50, ≥ 0.25** | 0 | 431 (96.6 %) | 15 |

Lo que la regla anterior perdía era foil: Ghost Rare 2/6, Prismatic Secret
Rare 3/9, Starlight Rare 8/16, Secret Rare 26/32. Con la adoptada todas
suben (6/6, 9/9, 10/16, 29/32); Starlight sigue baja porque su top-1 ya falla
en 1 de 16 y su similitud cae más que el resto. En los negativos la similitud
top-1 tiene mediana 0.14, p95 0.22 y máximo 0.45: el margen de 0.25 es lo que
separa, no la similitud absoluta.

Se adopta 0.50 / 0.25 y no la frontera exacta 0.48 / 0.24 por el cambio de
dominio: un negativo fotografiado en la mesa podría acercarse más al máximo de
0.45 observado en escaneos. En las 16 fotos reales anotadas la única carta que
queda fuera es Juicio Solemne en la caja ocluida por un Blue-Eyes (0.457 /
0.283), que la verificación por arte ya acepta por su cuenta
([TIEMPO_REAL.md](TIEMPO_REAL.md)). Ojos Anómalos (0.58 a 0.78 con los tres
artes en el piloto) y Mago Oscuro (0.92 a 0.95 con sus nueve artes) entran
con margen.

Límites: 50 identidades en el índice; con un índice mayor los márgenes se
estrechan y hay que repetir la calibración. Los positivos se emparejan por
identidad, no por arte. La rareza es desconocida para 176 de los 446
positivos. No hay negativos fotografiados en mesa: es el hueco que cubre el
[protocolo de capturas](PROTOCOLO_CAPTURAS.md).

Repetir sin volver a codificar (los registros quedan en
`qa/calibration/acceptance-records.json`):

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 research/calibrate_acceptance.py --from-records
```

## Regiones y umbral del OCR de set code

Parte A: las 16,340 lecturas del lote (`scan-numbers.jsonl`) contra el número
exacto de TCGplayer, disponible para 3,286. Cobertura 48.4 % (1,590 correctas),
precisión de lo leído 81.3 %. Por ancho: 200 px casi nada (1.8 %), 400 px 70 %,
500 px 50 %, 600 px 58 %. Por rareza: Rare y Secret Rare por encima de 75 %,
Shatterfoil 13 %, Ultimate 4 %, Platinum Secret 8 %, Starlight 12 %. Las
confusiones dominantes son F→E (429), S→5 (228), O→0 (126), I→1 (63) y P→E
(57): el lector confunde glifos, no posiciones.

Parte B: 400 escaneos ≥ 400 px con verdad exacta, estratificados por rareza,
releídos con siete variantes de `SET_REGIONS` y tres umbrales (35 minutos):

| Variante | 0.80 | 0.85 (actual) | 0.90 |
|---|---|---|---|
| actual | 52.7 % | **52.7 %** | 50.7 % |
| desplazar −3 % | 51.7 % | 51.5 % | 48.7 % |
| desplazar −1.5 % | 38.8 % | 39.8 % | 38.5 % |
| desplazar +1.5 % | 15.2 % | 14.2 % | 12.8 % |
| desplazar +3 % | 0.7 % | 0.7 % | 0.5 % |
| 5 % más ancha | 49.0 % | 48.0 % | 47.0 % |
| 1 % más alta | 35.5 % | 34.5 % | 31.2 % |

**Conclusión: no se cambia `SET_REGIONS` ni el umbral.** La región actual es
la mejor de las probadas y la sensibilidad es fuerte hacia abajo (+1.5 % ya
pierde dos tercios), así que cualquier ajuste futuro debe medirse sobre fotos
reales, no sobre escaneos. La ganancia real está en otro sitio: la mitad de
los fallos son F/E, S/5, O/0 e I/1. La regla de la casa es no corregir
caracteres a ciegas; la opción compatible con ella sería buscar en el registro
el código leído admitiendo esas equivalencias y guardarlo como evidencia
separada (`number_read_unverified` ya existe para eso), nunca como número.
No está implementado.
