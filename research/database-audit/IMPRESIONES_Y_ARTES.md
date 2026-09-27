# Asociaciones entre impresiones, artes e imágenes — 26/09/2026

Versión publicada: `20260926-071914-072968`; ruta vigente en
`data/curated/latest.json`. Las versiones anteriores se conservan.

## Evidencia incorporada

`printing_art_links` contiene **204 asociaciones de observaciones de impresión
con artes, correspondientes a 184 identidades**. Son coincidencias literales,
no vacías, de `printings.image_url` y `artworks.card_url`, dentro de la misma
identidad canónica. En esta versión proceden de YGOJSON.

Cada fila guarda `printing_id`, `artwork_id`, `canonical_card_id`, `status`,
`method`, `image_url`, `printing_source` y `artwork_source`. Las fuentes permiten
consultar el artefacto y hash originales en `sources`; la impresión conserva
su `record_key` y `evidence_json`. El método es `exact_card_url`.

- `source_declared`: URL coincidente con un único ID de arte de esa identidad.
- `ambiguous_url`: varios IDs de arte para la misma URL; se conservan todos.
- `source_declared_printing_art`: vista que incluye solamente el primer estado.

No se rellenó `printings.artwork_id` ni se modificaron observaciones originales.
Una coincidencia de URL en una fuente **no constituye verificación independiente
del arte físico, rareza, idioma o edición**. No se normalizan URLs ni se comparan
sólo sus nombres de archivo. Tener un único arte conocido tampoco prueba que
corresponda a todas las impresiones. Quedan **540,852 observaciones de impresión
sin este vínculo**; no son necesariamente impresiones físicas distintas.

## Revisión de imágenes

La versión incluye `visual-review-queue.jsonl`, con una fila por referencia
pendiente y los candidatos originales intactos:

| Resultado de clasificación | Referencias |
|---|---:|
| Un candidato canónico; falta verificación | 14,739 |
| Varios candidatos | 71 |
| Sin candidato | 4,389 |
| Total | 19,199 |

Son 17,818 referencias de CardsOrica y 1,381 de TDOANE. La cola es diagnóstica;
no aprueba propuestas ni modifica decisiones humanas. No se fusionan imágenes,
ni siquiera cuando comparten archivo, hash, carta o arte. Las 54,436 referencias
del catálogo se conservan. Un candidato único por nombre todavía puede ser falso.

Los archivos `printing-art-links.csv`, `visual-review-summary.json` y
`evidence-validation.json` quedan junto al SQLite de la versión. La consulta
`query_curated.py` muestra el número de asociaciones declaradas por identidad.
El visor de cámara no consume esta nueva tabla ni cambia sus umbrales.

## Continuación en esta u otra computadora

1. Seleccionar una muestra estratificada de la cola por fuente, idioma,
   resolución y cantidad de candidatos. Anotar positivos y negativos reales.
2. Comparar cada imagen con todos los artes candidatos, manteniendo empates
   entre artes de la misma carta. `ArtVerifier.verify` actual selecciona el
   mejor arte por identidad: no basta para confirmar una variante de arte.
3. Medir falsos positivos antes de promover asociaciones. Mantener métricas,
   hashes, referencias y versión del algoritmo como evidencia de cada decisión.
4. Enlazar escaneos TCGplayer por set code, nombre y metadatos concordantes;
   no inferir edición o rareza exclusivamente de la ilustración o de ofertas.

## Reproducción y validación

```powershell
.\.venv-eval\Scripts\python.exe qa_printing_art_links.py
.\.venv-eval\Scripts\python.exe -X utf8 curated_registry.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_printing_art_release.py
.\.venv-eval\Scripts\python.exe -X utf8 query_curated.py 89631139
```

La prueba sintética cubre alias, URL ambigua, identidad equivocada, URLs vacías
o diferentes, referencias duplicadas y candidatos mal formados. La validación
de la versión compara filas crudas y referencias con las bases originales,
revisa integridad SQLite y claves foráneas. No vuelve a hashear todas las imágenes.

Neuron: 67,552/67,552 fichas en caché y descarga completada sin errores en la
última ejecución. Esto sigue separado de una auditoría semántica de cada ficha.
