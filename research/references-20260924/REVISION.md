# Referencias de reconocimiento de Yu-Gi-Oh!

## Resultado de la revisión

**Priorizar DRAW2 para el siguiente experimento.** Aporta detección con cajas orientadas y clasificación de miles de ilustraciones, frente a nuestra referencia SIFT de una sola carta. Mantener nuestro visor Android y SIFT como comparación. Los modelos nuevos se descargaron pero no se ejecutaron ni integraron: aún no conocemos su precisión o velocidad en esta PC.

## Fuentes solicitadas y estado

| Fuente | Revisión y descarga |
|---|---|
| [Medium: DRAW, Hicham Tala](https://medium.com/@hich.tala.phd/how-i-trained-a-model-to-detect-and-recognise-a-wide-range-of-yu-gi-oh-cards-6ea71da007fd) | Leído mediante navegador de investigación. La descarga directa devuelve HTTP 403; se conserva esta ficha y el enlace, no una copia completa. |
| [Towards Data Science: Anthony Lowhur](https://towardsdatascience.com/i-made-an-ai-to-recognize-over-10-000-yugioh-cards-26fc6aed1588/) | El navegador de investigación no pudo abrirlo, pero la descarga HTTP normal sí funcionó. HTML local: `towardsdatascience.html`, con título y contenido del artículo. |
| [Reddit: anuncio de DRAW](https://www.reddit.com/r/yugioh/comments/1avcvae/i_trained_a_deep_learning_model_to_detect_yugioh/) | Leído mediante navegador de investigación; enlaza al mismo DRAW, no a otro detector. El HTML descargado directamente es una página genérica, no un archivo completo del hilo. |
| [Roboflow UniKL AI](https://universe.roboflow.com/unikl-ai/yu-gi-oh-card-detection) | Ficha y versión 1 revisadas por navegador. Descarga directa de página/exportación: HTTP 403. Dataset y pesos NO descargados. |
| [HichTala/draw](https://github.com/HichTala/draw) | Clone completo del último commit. La URL duplicada se descargó una sola vez. |
| [HichTala/draw2](https://github.com/HichTala/draw2) | Clone completo de la segunda versión enlazada en el README de DRAW. |
| [vanstorm9/yugioh-one-shot-learning](https://github.com/vanstorm9/yugioh-one-shot-learning) | Clone completo del proyecto asociado al artículo de Lowhur. |

Los manifiestos `downloads.json`, `assets.json` y `repos.json` registran fuentes y revisiones. Un HTTP 200 por sí solo no demuestra que se haya archivado el artículo: por eso se distingue expresamente el caso de Reddit.

## DRAW original: qué tomar

Código en `../../repos/draw`. Licencia principal AGPL-3.0. GitHub lo marca archivado; el README dirige a DRAW2.

- `draw.py`: separa localización YOLO, extracción de región, clasificación y representación. Restringe candidatos mediante deck `.ydk`.
- `src/tools.py`: extracción de contornos/arte, estimación de orientación y categorías por color.
- `src/build_models.py`: carga varios BEiT por tipo de carta. Los pesos publicados de los seis clasificadores suman más de 6 GB; no se descargaron para esta primera evaluación. Sí se descargó `yolo_ygo.pt`.
- `config.json`: seis tipos y umbrales de área absolutos. Estos umbrales necesitan calibración para nuestra resolución y distancia.

Problema concreto: aunque el constructor elige CPU si falta CUDA, la inferencia usa `.to('cuda')` en `draw.py:120`. No funcionaría intacta en una PC sin CUDA. También depende de funciones antiguas como `scipy.interpolate.interp2d`. Mantener como referencia histórica, sin convertirlo en la base del visor.

El artículo explica la separación detección/clasificación y el uso de listas de deck. En Reddit el autor aclara que la demostración original usa vídeo pregrabado y estima alrededor de dos fotogramas por segundo con una buena GPU. Esto no es una medida de nuestra PC ni de DRAW2.

## DRAW2: candidato principal

Código en `../../repos/draw2`, licencia principal AGPL-3.0.

| Componente | Utilidad para nuestro proyecto |
|---|---|
| `src/draw/draw.py` | Detector con cajas orientadas, rectificación de perspectiva a 224×224 y clasificador ViT. Las cuatro esquinas son útiles para anclar AR. |
| `src/draw/utils.py` | Herramientas de orientación y representación; requieren casos de prueba con fundas, giros y reflejos. |
| `docs/scripts/pipeline.js` | Implementación para ONNX Runtime Web, supresión de detecciones, clasificación con alternativas de rotación y asociación visual entre fotogramas. Es una referencia especialmente útil para ejecución local. |
| `docs/export_models.py` | Exportación y cuantización; orienta una futura versión CPU/ONNX. No se ejecutó el exportador. |

Hallazgos del código Python que corregir antes de integrar:

1. En la rama con deck, encuentra una candidata de la lista pero añade y muestra `output[0]`, en lugar de la candidata seleccionada. Puede devolver una carta fuera del deck.
2. Ante una rotación indeterminada usa `break`, que interrumpe el recorrido de las demás cajas de ese fotograma. Evaluar reemplazo por `continue`.
3. El umbral por defecto de clasificación equivale al 5%; necesita calibración con negativos, no adoptarlo como confianza de identificación.
4. La salida Python se centra en etiquetas e imagen dibujada. Nuestro adaptador debe conservar esquinas, puntuación, ID e instante para alimentar seguimiento y AR.
5. La inicialización descarga dataset completo y clasificador principal. Para el ensayo local, cargar directamente los ONNX seleccionados evita heredar toda esa inicialización.

La ruta web ofrece varias alternativas. Descargamos **el modelo compacto `vit_yugiscan_int8.onnx`**, no el ViT principal FP32/FP16. Su mapa `card_labels_yugiscan.json` tiene **13 659** entradas; el `config.json` del modelo principal tiene **13 820**. No mezclar estos índices. `cardnames_onnx.json` corresponde a la variante principal; para el compacto resolver su etiqueta/ID y usar los nombres por ID.

## One-shot learning de Lowhur

Código en `../../repos/yugioh-one-shot-learning`. No se encontró archivo de licencia principal; tratar como referencia antes de copiar código.

- `predict.py` y `detector/support/predictScript.py`: comparación de representaciones aprendidas y ajuste de ranking con ORB.
- `dictScripts/dictCreate.py`, `dictTest.py`, `dictUnify.py`: precomputar un índice de referencias en vez de procesar de nuevo el catálogo en cada fotograma.
- `detector/detector.py`: extracción y alineación para clasificación.
- Dependencias antiguas fijadas (`torch==1.7.0`, `torchvision==0.5.0`, OpenCV 4.2) y llamadas explícitas `.cuda()`; no instalar sobre nuestro entorno Python 3.14.

El autor diferencia la evaluación sobre imágenes de catálogo alteradas de las pruebas limitadas con fotos reales. El aproximadamente 99% publicado no demuestra ese rendimiento sobre nuestra mesa. El repositorio incluye fotos de ejemplo útiles para ampliar las pruebas; sus pesos/dataset externos de Google Drive no se descargaron.

## Roboflow UniKL AI

[Versión revisada](https://universe.roboflow.com/unikl-ai/yu-gi-oh-card-detection/dataset/1): 347 imágenes, tres clases (`Monster`, `Spell`, `Trap`), licencia declarada CC BY 4.0. Distribución 243 entrenamiento / 69 validación / 35 prueba; redimensionamiento a 640×640 y sin aumentos aplicados según la ficha.

Sirve para localizar cartas y distinguir categorías generales, **no para identificar Blue-Eyes por nombre**. Las métricas de la ficha pertenecen a ese conjunto y esa tarea, no son comparables con precisión de identidad de miles de cartas. La exportación no fue accesible aquí. Para usarlo se necesitará una exportación autorizada en YOLO/COCO desde Roboflow; no se enviaron nuestras fotos a su API.

## Recursos almacenados

Directorio: `../../downloads/reference-assets/`. Total: **197 719 922 bytes**, en 12 archivos, aproximadamente 198 MB decimales.

- `draw/yolo_ygo.pt` y ficha del modelo.
- `draw2/onnx/ygo_yolo.onnx` (~39 MB).
- `draw2/onnx/vit_yugiscan_int8.onnx` (~98 MB).
- Los dos mapas ONNX, nombres por ID, configuración ViT, configuración de DRAW y ficha del modelo.
- `retro-dataset/club_yugioh_dataset.zip` (~47 MB) y ficha: conjunto retro, no catálogo moderno completo. El antiguo enlace `HichTala/yugioh_dataset` redirige a `HichTala/tw-2008-ygo-dataset`.

Descargas fijadas a la revisión de Hugging Face indicada en `assets.json`. Todos los tamaños coinciden con metadatos; SHA-256 calculado para cada archivo y comparado con el hash LFS publicado en los cuatro binarios grandes. ZIP verificado por CRC, 6815 entradas. No se extrajo: contiene nombres con comillas incompatibles con Windows; habrá que normalizarlos conservando un mapa si decidimos usarlo.

## Plan actualizado

### YGOJSON, añadido por el usuario

[Repositorio](https://github.com/iconmaster5326/YGOJSON) descargado en `../../repos/ygojson`; código con licencia MIT. Catálogo agregado oficial descargado en `../../downloads/reference-assets/ygojson-aggregate.zip` (35 569 075 bytes). CRC del ZIP correcto; SHA-256 y commit registrados en `ygojson-inspection.json`.

El repo contiene generador y esquemas; los datos se publican aparte. Se usó el ZIP de release, porque el README advierte que el JSON agregado en la rama raw está desactualizado por límites de tamaño. El ZIP recibido contiene **14 616 cartas**. Sus metadatos registran últimas lecturas de YGOPRODeck/Yugipedia el **7 de abril de 2026** y de Yaml Yugi el 13 de mayo de 2025: no asumir que contiene novedades posteriores por haberse descargado hoy.

Sirve para nombres, estadísticas y vínculos entre cartas/ilustraciones. No es un modelo de visión ni incluye modelos 3D. El código de exportación de DRAW2 ya usa YGOJSON para nombres japoneses.

Cruce reproducible: `python research/check_ygojson.py`. Usa passwords, identificadores de imágenes y `externalIDs.ygoprodeck.id`, normaliza ceros iniciales y conserva ambigüedades. Nunca equipara el UUID de YGOJSON con el índice de salida del modelo.

| Resultado para las etiquetas de DRAW2 Small | Cantidad |
|---|---:|
| Etiquetas totales | 13 659 |
| Enlace único con una carta YGOJSON | 13 631 |
| Enlaces únicos con nombre español | 13 470 |
| Sin correspondencia | 16 |
| Correspondencias ambiguas | 12 |

Mapa derivado en `draw2-small-ygojson-map.json`; pendientes detallados en `ygojson-inspection.json`. Son medidas de **cobertura del catálogo**, no de precisión visual. No se cambió el visor. Blue-Eyes se resuelve a `89631139`, UUID `e0404755-1ade-4c7c-9a2a-b29b7755d860` y nombre español `Dragón Blanco de Ojos Azules`.

Nuevo componente propuesto: `índice del clasificador -> etiqueta/ID de arte -> UUID YGOJSON -> ficha en español -> asset AR`. Mantener también el ID de ilustración para no confundir una variante de arte con otra carta.

### Experimentos siguientes

1. Crear un entorno de evaluación separado para ONNX; conservar nuestro visor actual.
2. Ejecutar solo el detector DRAW2 sobre las tres capturas y fotos negativas. Medir cajas, falsos positivos y tiempo en CPU.
3. Rectificar los recortes y añadir el clasificador compacto con SU mapa de etiquetas; comprobar ID y arte alternativo.
4. Comparar con SIFT en las mismas imágenes y en nuevos vídeos del teléfono: tamaño pequeño, giros, reflejos, varias cartas y cartas fuera del deck.
5. Integrar el método elegido detrás de `/analyze` y conservar esquinas/timestamp. Añadir seguimiento por copia física antes de animaciones 3D.

Este turno descarga y revisa referencias. No modifica el reconocedor ni afirma que DRAW2 ya funcione en vivo.
