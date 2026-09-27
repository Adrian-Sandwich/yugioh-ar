# Registro multilingüe y de impresiones

Fecha de trabajo: 25 de septiembre de 2026. Consulta los conteos actuales en `data/registry/summary.json`; el descargador puede seguir añadiendo observaciones después de este informe.

## Usarlo

Abre **http://127.0.0.1:8769** para buscar por nombre, passcode o código de set y ver impresiones filtradas por idioma. `start_lab.ps1` inicia este servicio junto a la galería cuando existe la base.

- `data/registry/registry.sqlite`: registro relacional consultable, separado del catálogo de imágenes y sus revisiones manuales.
- `data/registry/exports/cards.csv`: una fila por registro de carta, nombres EN/ES/DE/FR/PT y passcodes como texto.
- `names.csv`: nombres y textos por idioma con fuente; conserva variantes de nombre.
- `identifiers.csv`: passcodes, CID oficial, IDs del juego y de imágenes, distinguidos por tipo.
- `printings.csv`: códigos de set, idioma/región, rareza, edición, arte cuando se conoce, fecha, evidencia y fuente.
- `artworks.csv`: 16,121 registros de arte en la distribución inicial, con URLs originales.
- `sources.csv`: artefactos, URL, SHA-256 y metadatos de procedencia.
- `gaps.csv` e `issues.csv`: datos ausentes, colisiones y registros no resueltos.
- `card_facts.csv`: características originales de la carta como JSON, sin convertir valores desconocidos en cero.

Los CSV son UTF-8 con BOM. Al abrir `identifiers.csv` en Excel importa `value` como **texto**, para conservar ceros iniciales. Los nombres preferidos de `cards.csv` priorizan Neuron, luego YGOJSON, luego el juego. La tabla `names` mantiene los demás nombres; no se eliminan como si fueran erratas confirmadas.

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 registry.py lookup 89631139
.\.venv-eval\Scripts\python.exe -X utf8 registry.py lookup LOB-EN001
.\.venv-eval\Scripts\python.exe -X utf8 registry.py export
.\.venv-eval\Scripts\python.exe -X utf8 qa_registry.py
```

SQL de ejemplo:

```sql
SELECT p.set_code,p.language,p.rarity,p.edition,p.release_date,p.source
FROM printings p
WHERE p.card_id IN (
 SELECT card_id FROM identifiers WHERE kind='passcode' AND value='89631139'
) AND p.language IN ('es','en','de','fr','pt')
ORDER BY p.release_date DESC,p.set_code;
```

## Fuentes incorporadas

**27/09/2026: TCGplayer.** `research/import_tcgplayer_printings.py` añadió
42,062 observaciones de impresión con fuente `tcgplayer:reconstructed-20260927`:
código de set exacto de la búsqueda de TCGplayer, rareza del producto, URL del
escaneo en el CDN y, en `evidence_json`, el producto, la ruta local del
escaneo y cómo se emparejó la identidad (por nombre, `reconstructed.json`).
Se importaron sólo productos con una única identidad reconstruida y número
exacto (42,062 de 47,824; 3,448 con códigos fuera del formato `SET-LL000`,
2,103 con identidad ambigua). Aportó 42 códigos de set nuevos y rareza para
todas las filas; de las 1,138 lecturas OCR que el lote marcó "sin coincidencia
en el registro" sólo 4 se resuelven con ellos, confirmando que esas lecturas
eran errores de glifo y no huecos del registro. Su valor principal es enlazar
cada impresión con una foto real de esa rareza. Respaldo previo con la API de
backup en
`research/database-audit/registry-before-tcgplayer-20260927-091658.sqlite`
(fuera de Git). Reversión: borrar las filas de `printings` y `sources` con ese
identificador.

1. **[YGOJSON](https://github.com/iconmaster5326/YGOJSON)**: distribución individual completa, 14,616 registros de carta y 3,306 productos/conjuntos. El ZIP pasó validación CRC de todos sus archivos. Sus metadatos indican últimas lecturas de Yugipedia/YGOPRODeck del 7 de abril de 2026 y de YamlYugi de mayo de 2025; descargarlo hoy no vuelve actuales esos datos. Los sets virtuales se conservan como productos, pero no se inventan impresiones físicas para ellos.
2. **Juego local TDOANE**: nombres de cuatro idiomas enlazados por el catálogo existente y 8,350 observaciones de `pack.db`; 17 filas quedaron sin asociación segura. Su historial es parcial, no exhaustivo. Las fechas ambiguas y los códigos antiguos sin idioma conservan su valor original sin inferir datos.
3. **[Neuron](https://www.db.yugioh-card.com/yugiohdb/card_search.action)**: scraping directo de su índice público completo en cinco idiomas (678 páginas). Incluye nombres, textos e identificador CID. Descarga adicional de fichas individuales para código de set, rareza y fecha. Cada respuesta HTML se guarda junto al JSON interpretado, SHA-256, URL y fecha de descarga. El idioma y la paginación se verifican antes de aceptar una página.
4. **Fandom español e inglés**: se probaron las fichas públicas de Blue-Eyes; la herramienta web no pudo acceder (error de acceso y HTTP 402 en inglés). No se importaron datos de esas páginas ni se inventaron resultados. YGOJSON ya reúne información de Yugipedia, que es otra fuente, no la misma wiki.

Los dos ZIP agregados descargados fallaron CRC; no son entradas del constructor. `build_catalog.py` también fue corregido para leer la distribución individual válida. Los JSON extraídos de los agregados en `data/registry/source-ygojson` tampoco se usan.

## Qué significa cobertura completa

`data/registry/neuron/index-coverage.json` verifica páginas esperadas, páginas presentes, SHA-256, filas y CIDs únicos. La captura del índice contiene:

| Idioma | Páginas | Cartas listadas |
|---|---:|---:|
| Inglés | 140 | 13,919 |
| Español | 138 | 13,787 |
| Alemán | 139 | 13,844 |
| Francés | 139 | 13,825 |
| Portugués | 122 | 12,177 |

Estos son tamaños del índice público por idioma, no 67 mil identidades diferentes. No todas las cartas existen en todos los idiomas. El catálogo consolidado también contiene registros que no aparecen en esas búsquedas: por ejemplo, registros históricos, OCG o sin traducción oficial.

**El índice de nombres está completo respecto a esta captura; el contraste de todos los historiales oficiales es un trabajo separado y largo.** `neuron/progress.json` indica qué fase está activa y los errores; `detail-queue.json` guarda la cola inicial de la ejecución. El número `remaining` de esa cola es una instantánea inicial, no un contador en vivo.

La tabla `printings` guarda observaciones, no una deduplicación final de todas las impresiones físicas del mundo. Una misma impresión puede estar descrita por YGOJSON, el juego y Neuron. Un mismo set code puede tener varias rarezas: por ejemplo [RA05-EN085 en la ficha oficial](https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=4007&request_locale=en). Tampoco todas las fichas tienen código: Neuron deja vacío el código de una impresión de Blue-Eyes en 25TH ANNIVERSARY ULTIMATE KAIBA SET.

## Descarga y actualización

```powershell
# Completar/reanudar todos los historiales en segundo plano, sin ventana:
.\start_registry_crawl.ps1

# Si Windows bloquea los .ps1, excepción sólo para esta ejecución:
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_registry_crawl.ps1

# Ver el avance y posibles errores:
Get-Content data/registry/neuron/progress.json
Get-Content .runtime/registry-crawl.error.log -Tail 20

# Solicitar parada ordenada después del lote en curso:
New-Item -ItemType File -Path data/registry/neuron/STOP
```

Para reanudar, elimina exclusivamente el archivo `STOP` y vuelve a ejecutar el lanzador. Las páginas ya descargadas se reutilizan. No ejecutes dos descargadores ni reconstruyas `registry.py build` mientras el actualizador esté escribiendo. El servicio de consulta es de sólo lectura.

El proceso usa hasta cuatro solicitudes concurrentes, espaciadas globalmente, caché persistente y reintentos limitados para errores transitorios. No evade bloqueos de acceso. La fase de todos los historiales implica decenas de miles de páginas y puede durar horas. Se incorporan resultados a SQLite cada 20 páginas; los CSV y conteos resumidos se actualizan cada 1,000 resultados y al terminar. La base consultable puede estar más avanzada que los CSV entre esos puntos.

## Reglas y pendientes de calidad

- El passcode proviene exclusivamente de `passwords` de YGOJSON en esta versión. Sus IDs de imagen **no** se convierten en passcodes. Para Blue-Eyes, `89631139` es passcode; `89631140` sólo se guarda como ID de imagen.
- Hay nueve colisiones de CID entre registros de YGOJSON. Se registran como incidencias y no se reparten automáticamente las observaciones oficiales entre identidades ambiguas. Deben reconciliarse con evidencia adicional.
- Tres valores de passcode incluyen comentarios HTML en el origen. Se mantienen como incidencias, fuera de la tabla de passcodes válidos. No se corrigen silenciosamente: algunos comentarios mencionan números impresos compartidos.
- Las ediciones se asignan sólo donde `cardInfo` del producto documenta esa impresión/edición; las ediciones generales del set no se multiplican como si hubiera prueba de cada combinación.
- La ausencia de passcode puede ser legítima (tokens, promociones, etc.) o un hueco de fuente. La ausencia de traducción no se rellena con traducción automática presentada como nombre impreso.
- Rush Duel necesita un catálogo y plantillas propios; no queda cubierto por esta base TCG/OCG de YGOJSON y búsquedas TCG de Neuron.
- Los artes y rarezas de los archivos de imágenes todavía necesitan revisión visual. La asociación de identidad no demuestra qué edición o acabado aparece en una fotografía.

La referencia de estructura está en [card-anatomy/ESTRUCTURA.md](card-anatomy/ESTRUCTURA.md) y [anatomy.json](card-anatomy/anatomy.json). Las pruebas cubren integridad SQLite, claves, ceros iniciales, separación de IDs, cinco idiomas, múltiples rarezas por código, campos ausentes y búsqueda real en navegador.
