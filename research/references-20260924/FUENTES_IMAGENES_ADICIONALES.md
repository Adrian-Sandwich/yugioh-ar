# Fuentes adicionales: CardsOricaBR y YCCLP

Revisión inicial: 2026-09-24. Actualización posterior: el usuario solicitó descargar toda la colección; ver estado al final. No se entrenó ni modificó el reconocedor.

## CardsOricaBR: candidato para galería visual

[Publicación de DeviantArt](https://www.deviantart.com/cardsoricabr/art/Yugioh-DataBase-Images-17-500-Cards-976699742), publicada el 12 de agosto de 2023, anuncia 17 500 cartas y enlaza una [carpeta pública de Drive](https://drive.google.com/drive/folders/1_AcddAI-MbuXIaaa5-VdzXLaw8ej7dmC). Esa cifra no fue contada ni validada como identidades únicas. No se encontró una licencia explícita de reutilización del conjunto en la descripción consultada.

Inspección directa: la subcarpeta Cards contiene 12 categorías, entre ellas Normal, Effect, Pendulum y Rush Duel. Normal se subdivide por atributos. En Light aparecen varios archivos Blue-Eyes con sufijos numerados. Son candidatos a variantes; el nombre del archivo por sí solo no determina identidad, idioma ni ilustración.

Se descargó y visualizó una muestra: `../../downloads/reference-assets/cardsoricabr-blue-eyes-2.jpg`, carta completa en inglés de Blue-Eyes, 206 × 300 píxeles, 64 811 bytes. Sirve para probar la ingesta; esa resolución no demuestra adecuación para OCR ni representa necesariamente todo el conjunto. ID Drive: `1hOVCw9zliLyHTZeS_lWg6h4HGj0tlmok`. SHA-256: `7f1e510f12a316fc94bc993b4b805efd5af21f7a75d3c9a21b9420574d0ca94b`.

Listados de la revisión inicial: `cardsoricabr-drive.html`, `cardsoricabr-cards.html`, `cardsoricabr-normal.html`, `cardsoricabr-light.html`. En esa revisión solo se descargó la muestra; posteriormente se descargó toda la colección. La cobertura de alemán, español, portugués y francés sigue sin verificar; los nombres ingleses de los archivos no prueban el idioma impreso.

## YCCLP: referencia histórica de metadatos

[SourceForge](https://sourceforge.net/projects/ycclp/) presenta una lista en formato OpenOffice Calc y señala última actualización el 15 de abril de 2013. Se descargó su archivo más reciente mediante `/files/latest/download`:

- `../../downloads/reference-assets/yugioh_boosters.rar`, 306 913 bytes. SHA-256 `bff753af53c489fef027bdcb5196ce2b0d9004607838f178bd70be7d55a6a375`, coincide con el publicado en SourceForge.
- Contiene únicamente `yugioh_boosters.ods`, extraído junto al RAR. SHA-256 `2059aa0f8c804f2065b5995201501deb17a3d477f5915504e09a1294e918b476`.

Verificación local del ODS: CRC correcto, 40 pestañas de expansiones; primera pestaña con nombres/textos en inglés, códigos de expansión, tipo, rareza y estadísticas. Inspección del XML, sin abrir una suite ni ejecutar macros. No aporta un conjunto de imágenes para embeddings. No se verificó una licencia específica de los datos.

Prioridad baja: posible contraste de códigos históricos. Mantener YGOJSON como catálogo principal; no sustituirlo ni adoptar estos textos antiguos como descripción actual de las cartas.

## Incorporación al plan en la otra computadora

1. Inventariar recursivamente la carpeta de imágenes y registrar cantidad real, tamaño, resolución, idioma verificado, procedencia y hash; distinguir archivos de identidades.
2. Separar TCG/OCG del alcance piloto de Rush Duel y cualquier material no oficial que aparezca tras la revisión. No concluir que una imagen es oficial solo por estar en esta carpeta.
3. Vincular cada muestra al catálogo y a una ilustración. Apartar coincidencias ambiguas; deduplicar por hash y revisar similitud visual antes de indexar.
4. Seleccionar referencias por calidad y cobertura de las 50 identidades piloto, manteniendo sus variantes útiles. Medir la aportación frente a las referencias existentes antes de descargar todo.
5. Construir la matriz de cobertura de los cinco idiomas. Obtener impresiones faltantes de otras fuentes; esta muestra inglesa no valida reconocimiento multilingüe.
6. Usar imágenes canónicas como galería/entrenamiento y fotos reales independientes para prueba. Evitar que duplicados o variantes del mismo escaneo contaminen las particiones.

Resultado: CardsOricaBR queda como fuente visual candidata pendiente de auditoría amplia; YCCLP queda como archivo histórico auxiliar. Ninguno proporciona por sí solo invariancia a giros/sombras ni validación con cámara.

## Descarga completa solicitada posteriormente

Inventario recursivo terminado: **89 carpetas, 17 818 archivos** (17 722 JPG y 96 PNG). Descargados todos sin errores: **1 267 825 708 bytes**. Originales en `../../downloads/cardsoricabr/files/`; `manifest.json` conserva IDs Drive, nombres, carpetas de origen, tamaños y SHA-256. `download_complete` y `discovery_complete` están en true. Se conservaron todos los originales.

Distribución de archivos por categoría: Effect 6 287; Spell 3 637; Trap 2 774; Rush Duel 1 104; Normal 755; Xyz 638; Fusion 586; Synchro 529; Link 489; Pendulum 459; especial 370; Ritual 190. Son archivos, no identidades únicas.

Descarga reproducible/reanudable: `research/download_cardsoricabr.py`. Se usaron los listados públicos embedded de Drive: se comprobó que incluyen archivos posteriores a los primeros 50 que muestra la vista normal. Las páginas de inventario se guardan en `downloads/cardsoricabr/listings/`.

Comprobación de imágenes y duplicados exactos: `research/audit_cardsoricabr.py`, salida `downloads/cardsoricabr/audit.json`. Esta auditoría no determina idioma, rareza, identidad ni oficialidad; esas etiquetas siguen pendientes. El plan de vectores incorpora múltiples artes y acabados por identidad.

Auditoría final completada: las **17 818 imágenes se decodifican**, tamaños y hashes coinciden, cero errores. Hay **17 754 contenidos SHA-256 únicos y 64 grupos de duplicados exactos**; no se borraron duplicados. La resolución más frecuente es 206 × 300 (5 805 archivos), seguida de 205 × 300 (2 775). La colección local de TDOANE aporta mayor resolución en muchas referencias y IDs enlazados con SQLite: priorizarla como base inicial y contrastar CardsOricaBR para variantes adicionales.
