# Catálogo ampliado para generar vectores

El puntero `data/recognition-catalog/latest.json` identifica el paquete vigente.
Se construye con `prepare_recognition_catalog.py` sobre una versión curada
concreta, sin modificar el piloto, el visor ni los archivos de imagen.

## Contenido preparado

- **54,436 referencias conservadas**, una fila por ref_id en `assets.jsonl`.
- **13,094 imágenes de arte** de **12,947 identidades**, verificadas por SHA256,
  dimensiones y decodificación, en `embedding-inputs.jsonl`.
- **114 identidades con más de una referencia de arte** dentro de esa selección.
- **41,342 referencias retenidas fuera de la selección inicial**, con sus motivos.
- `identities.jsonl`: 14,722 identidades, alias de origen, nombres por idioma,
  passcodes efectivos y formatos declarados por la fuente.
- `summary.json`: conteos, procedencia, hashes de los manifiestos y del generador.
- `validation.json`: resultado de la validación de conservación y consistencia.

Los inputs están enlazados por la fuente a artes de identidades de tipo monstruo,
magia o trampa con metadatos TCG/OCG. Se comprueba que el ID del arte pertenezca
a la misma identidad canónica. No se consideran verdad de terreno independiente
de una impresión física. Los archivos duplicados se conservan sin fusionar filas.

## Etiquetas y límites

`origin_domain` distingue proveedor de artes, recurso del juego y colección de
terceros. `identity_family` distingue carta estándar, token, Skill y desconocido
cuando los metadatos de identidad permiten hacerlo. Esto no etiqueta la geometría
ni la autenticidad de todas las imágenes de esa carta.

`image_format` queda **unreviewed** salvo tres imágenes de la muestra visual con
evidencia y hash: Rush Duel, formato no estándar y diseño personalizado TDOANE.
No se declara que las otras 54,433 imágenes hayan sido revisadas. La procedencia
TDOANE no significa por sí sola que cada imagen tenga un marco personalizado.

Idioma impreso, rareza y edición permanecen sin asignar cuando no hay evidencia
de la imagen. Los nombres multilingües de una identidad no prueban el idioma de
una imagen concreta. Los motivos de retención pueden solaparse.

## Uso en la otra computadora

1. Copiar el paquete apuntado por `latest.json`, los scripts y las imágenes con
   sus rutas relativas originales. Para el índice inicial basta la carpeta de
   artes de YGOPRODeck; para revisar todas las referencias se requieren también
   los otros directorios de `downloads`. No borrar la colección original.
2. Leer **cada fila** de `embedding-inputs.jsonl`; conservar ref_id, card_id,
   artwork_id y SHA256 junto a cada vector. No reducir a una imagen por carta.
3. Comparar recorte de ilustración de la consulta con referencias de ilustración.
   No sustituir silenciosamente el índice de cartas completas por este índice.
   Registrar modelo, preprocesamiento y hashes de entrada en la caché nueva.
4. Agrupar resultados por identidad para calcular el margen entre cartas distintas;
   conservar los resultados por arte para detectar variantes y empates.
5. Comparar contra el piloto con las mismas capturas. Registrar desconocidos,
   falsos positivos, errores de esquinas y latencia p50/p95. Un arte desconocido
   no invalida automáticamente un serial/nombre correctamente identificado.

`split_group` agrupa por identidad canónica y evita repartir alias de la misma
carta como si fueran identidades distintas. No es una partición train/test:
para generalización por identidad se separan grupos; para reconocer identidades
ya conocidas se separan sesiones/capturas físicas y se auditan las fugas de imagen.

Los experimentos anteriores de `research/embedding_art_experiment.py` consumen
otro manifiesto; no usan automáticamente este paquete. Los vectores de esta
selección y su integración en el visor siguen pendientes para destino.

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 prepare_recognition_catalog.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_recognition_catalog.py
```

Investigación de nombres: [104 huecos con fuentes consultadas](database-audit/name-investigation-20260926-071914-072968/README.md).
