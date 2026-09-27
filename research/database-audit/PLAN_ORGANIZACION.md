# Inventario y organización de la base

Corte del registro: 2026-09-26 05:26 UTC. La descarga sigue activa: los totales
son una fotografía temporal. Auditoría de sólo lectura; no se fusionaron ni
borraron identidades y no se modificaron las bases del visor.

**Política indicada por el usuario:** conservar todos los archivos de imagen,
incluidos duplicados exactos, tomas parecidas y distintas rarezas/iluminaciones.
Los hashes sólo describen coincidencias. No borrar, reemplazar ni colapsar
referencias por hash, nombre, carta o arte. El estado posterior de sincronización
se documenta en `SINCRONIZACION.md`; este inventario conserva su corte original.

## Qué existe realmente

| Archivo / conjunto | Función y contenido observado |
|---|---|
| `data/registry/registry.sqlite` | Registro de identidades, nombres, identificadores, artes, productos y observaciones de impresiones; aproximadamente 565.5 MB más WAL |
| `data/catalog/catalog.sqlite` | Catálogo de referencias visuales y localizaciones; aproximadamente 119.2 MB |
| `data/catalog/reviews.sqlite` | Decisiones humanas; actualmente cero decisiones guardadas |
| `data/registry/neuron` | Caché de fichas JSON/HTML e índices oficiales; una ficha es una combinación carta/idioma |
| `downloads/reference-assets/ygojson-individual-20260925.zip` | Fuente estructurada de YGOJSON usada por los importadores; conservar ZIP y procedencia |
| `downloads/tdoane-reference` | Recursos del juego: 15,122 JPG, 7,247 PNG, 7 CDB y otros archivos; no todos son cartas completas |
| `downloads/cardsoricabr` | 17,818 imágenes y páginas/manifiestos de procedencia |
| `downloads/ygoprodeck-art` | 14,248 JPG de ilustraciones; manifiesto de 15,014 asociaciones a artes (14,249 ok, 765 missing); asociación y archivo no son la misma unidad |
| `downloads/tcgplayer-sample` | 120 JPG de muestra; tampoco están en `catalog.refs` |
| `data/pilot/catalog.json` | 63 referencias para 50 identidades; el índice de embeddings actual tiene este alcance. El clasificador es otra ruta distinta |

El registro contiene 14,734 filas de identidad: 14,616 de YGOJSON y 118 añadidas
por Neuron. No equivalen necesariamente a 14,734 identidades ya reconciliadas.
Tiene 16,121 registros de arte para 14,616 cartas; 1,173 cartas tienen varios
artes registrados. Un registro de arte no garantiza una imagen local descargada.

Hay 502,313 **observaciones** de impresión: 339,985 de YGOJSON, 153,978 de
Neuron y 8,350 del juego. No son 502,313 impresiones físicas únicas. Incluso
agrupar por carta/código/idioma (266,901 grupos con código) todavía mezcla
rarezas, ediciones y otras variantes. Igualar todos los campos observados deja
502,195 tuplas: el desacuerdo y los campos vacíos impiden deduplicar sólo con DISTINCT.

Cobertura de nombres, contando identidades con al menos un nombre:

| Idioma | Con nombre | Sin nombre respecto a 14,734 |
|---|---:|---:|
| Inglés | 14,734 | 0 |
| Español | 14,314 | 420 |
| Alemán | 14,332 | 402 |
| Francés | 14,351 | 383 |
| Portugués | 12,463 | 2,271 |

12,462 identidades tienen nombres en los cinco idiomas. Una traducción ausente
no prueba que falte una descarga ni que exista una edición física en ese idioma.
Hay otros idiomas en el registro: conservarlos sin mezclarlos con la evaluación
del objetivo EN/ES/DE/FR/PT. Las 298,935 observaciones de nombres se reducen a
121,997 combinaciones distintas carta/idioma/texto en todos los idiomas.

## Hallazgos que requieren trabajo

1. **Colisiones de identidad:** 13 passcodes apuntan cada uno a dos UUID y hay
   9 CID de Neuron compartidos. Ejemplos: Ryzeal Cross y Azamina aparecen en dos
   registros. Son candidatos a reconciliación, no autorización para fusionar
   automáticamente por nombre. Ver `passcode-conflicts.csv`.
2. **Passcodes opcionales y múltiples:** 635 identidades no tienen serial y 78
   tienen varios. Los 14,166 valores distintos no son una clave primaria segura.
   No hay seriales mal formados aceptados; tres valores con comentarios HTML
   están apartados como incidencias de importación.
3. **Impresión → arte sin resolver:** las 502,313 filas tienen `artwork_id` vacío.
   No sabemos todavía qué arte corresponde a cada impresión. Tener el arte y el
   set por separado no resuelve ese vínculo. Investigar primero si la fuente
   aporta la relación antes de atribuirlo a un fallo del importador.
4. **Impresiones incompletas:** 4,773 sin código, 1,508 sin idioma, 335,401 sin
   edición, 335,401 sin URL de imagen, 162,328 sin producto y 54,673 sin fecha.
   No rellenar estos huecos copiando valores de otra variante sin evidencia.
5. **Colisiones de código:** 50 set codes apuntan a más de una identidad; algunos
   son placeholders (`BLLR-EN0??`). Distinguir códigos literales, incompletos y
   códigos internos; un set code tampoco será clave global única.
6. **Catálogo visual desfasado:** tiene 14,616 identidades, le faltan las 118 de
   Neuron. De 40,187 referencias: 20,988 linked, 14,810 proposed, 4,389 unresolved.
   Linked indica ID/nombre concordantes, no revisión humana. Sólo linked cubre
   13,479 cartas; contar cualquier vínculo propuesto da un total mayor engañoso.
7. **Mezcla de tipos de imagen:** las 40,187 referencias incluyen 32,753 cartas
   completas, 7,245 sprites, 188 campos y un recurso de otro tipo. Hay 40,058
   hashes distintos y 116 grupos duplicados; conservar las rutas y procedencias
   sin deduplicar ni eliminar contenido binario.
8. **Assets fuera del catálogo:** YGOPRODeck ya tiene asociaciones por arte en su
   manifiesto, pero no filas centrales en `refs`. Integrarlas es prioritario para
   ampliar reconocimiento; no hay que inferirlas desde el nombre del archivo.
9. **Ruta rota recuperable:** una referencia de Fanfan contiene `Phmenix` en lugar
   de `Phoenix`. El archivo existe y su SHA-256 coincide con el registrado.
   Reparación identificada, todavía no aplicada.

`PRAGMA quick_check` del registro devuelve `ok`; no hay violaciones de claves
foráneas detectadas. Eso verifica estructura, no exactitud semántica. Las
revisiones manuales no tienen decisiones: no presentar todo el corpus como
visualmente validado. No se releyeron todos los HTML ni recalcularon todos los
hashes de imágenes durante esta auditoría.

## Modelo recomendado

Mantener SQLite: el problema encontrado es de relaciones, cobertura y calidad,
no una necesidad demostrada de cambiar de motor o usar Go/Julia.

Separar tres capas lógicas, aunque compartan servidor local:

1. **Fuentes originales:** HTML, JSON, ZIP, imágenes y manifiestos con URL,
   fecha y hash. Conservar sin sobrescribir para poder reproducir importaciones.
2. **Observaciones y reconciliación:** valores tal como los afirma cada fuente,
   conflictos y decisiones versionadas. La descarga continúa escribiendo aquí.
3. **Catálogo publicado para consultas:** identidades reconciliadas, nombres
   preferidos, aliases, impresiones, imágenes y un índice de reconocimiento
   explícitamente versionado; regenerable desde las dos capas anteriores.

Entidades que debe exponer la tercera capa:

| Entidad | Relación y reglas |
|---|---|
| `card_identity` | UUID estable, tipo y ámbito del juego; jamás usar nombre traducido como ID |
| `identity_alias` | UUID de origen → UUID canónico, decisión/evidencia y versión; reversible |
| `card_name` | Identidad + idioma; nombre preferido separado de aliases y observaciones |
| `identifier` | Identidad + tipo + valor de texto; ceros iniciales intactos; conflictos explícitos |
| `artwork` | Identidad + arte; distinguir ilustración del escaneo de una impresión |
| `product` | Pack/mazo con nombres, región y fechas respaldadas por fuentes |
| `printing` | Identidad + producto + código + idioma + región + edición + rareza/acabado; ID propio, campos desconocidos permitidos |
| `printing_artwork` | Asociación con evidencia y estado; aceptar múltiples candidatos mientras falte certeza |
| `image_asset` | Hash, dimensiones, ruta, tipo (carta/arte/sprite/campo), origen y estado de disponibilidad |
| `asset_link` | Imagen → identidad/arte/impresión, método, confianza y revisión; no equivaler proposed a approved |
| `recognition_release` | Versión de catálogo, modelos, referencias incluidas, hashes, cobertura y métricas |

Normalizar rarezas con una tabla de equivalencias específica por fuente:
`common` y `Common` pueden coincidir, pero acabados diferentes no se deben
colapsar por parecido textual. Conservar el valor original. Separar idioma de
región/locale; revisar `ae` sin tratarlo automáticamente como un idioma nuevo.

## Orden de implementación y aceptación

1. **Ahora:** conservar este inventario, CSV de identidades y cola de conflictos.
   Preparar una copia SQLite consistente para ensayar cambios; no copiar un
   archivo vivo ignorando WAL. La descarga no necesita detenerse.
2. **Sanear enlaces:** corregir la ruta verificada, integrar el manifiesto de
   YGOPRODeck y actualizar las 118 identidades ausentes mediante staging.
   Aceptación: rutas resolubles, hashes y tipos válidos; cero referencias a UUID
   inexistentes; estados de revisión preservados.
3. **Reconciliar:** revisar primero los 13 seriales/9 CID compartidos, crear mapa
   de aliases reversible y decidir nombres preferidos sin borrar alternativas.
   Aceptación: conflictos resueltos o marcados, nunca selección arbitraria.
4. **Impresiones:** normalizar vocabularios, vincular productos y estudiar
   impresión→arte por fuente. Aceptación: cada asociación tiene evidencia;
   rareza/edición desconocida no se transforma en valor inventado.
5. **Publicar una versión:** generar tablas de consulta e índice visual ampliado
   en paralelo al actual. Comparar búsquedas y OCR, medir cobertura real y falsos
   positivos. Cambiar el visor sólo después de validar y conservar rollback.
6. **Cerrar descarga:** reintentar los dos errores DNS, reconciliar cola/caché/
   fuentes importadas y volver a auditar. Durante este corte la diferencia de
   82 fichas entre caché y fuentes corresponde a instantes de lectura distintos;
   no demuestra una pérdida. Comprobar tras estabilizar el importador.

## Entregables

- `inventory.json`: conteos y hallazgos detallados del corte.
- `identities.csv`: una fila por UUID con CID, tipo, seriales y nombres por idioma;
  las celdas de listas son JSON, sin elegir silenciosamente un alias.
- `passcode-conflicts.csv`: 26 filas correspondientes a 13 seriales conflictivos,
  con nombres, UUID y CID para revisión.
- `../audit_database_inventory.py`: auditoría base reproducible, de sólo lectura.
  El inventario de este corte incluye comprobaciones complementarias del
  manifiesto YGOPRODeck, piloto y recuperación de ruta.
