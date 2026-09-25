# Plan: reconocimiento robusto por vectores, geometría e iluminación

La planificación general actual está en [PLAN_MEJORA_INTEGRAL.md](PLAN_MEJORA_INTEGRAL.md):
prioriza geometría, seguimiento y medición antes de reactivar entrenamiento.

**Pospuesto por decisión del usuario (25/09/2026).** El trabajo adicional de
vectores, invariancia y entrenamiento queda para una etapa futura, junto con
el [lector especializado de dígitos](digit-references/README.md). Retomar cuando
el usuario lo indique; conservar el piloto de embeddings existente.

Actualización del 25/09/2026: se implementaron catálogo unificado, revisión de artes, piloto de 50 identidades, extracción de embeddings de 768 dimensiones sin entrenar pesos, comparación inicial y sprites AR. Estado, límites y reproducción en [ENTREGA_PILOTO.md](ENTREGA_PILOTO.md). El entrenamiento y validación amplia en la otra computadora siguen pendientes; el texto siguiente conserva el plan de investigación.

Estado: plan para ejecutar en otra computadora. No se entrenaron ni exportaron modelos nuevos en este paso. Hardware destino aún desconocido; registrar GPU, VRAM, RAM, sistema y cámara antes de fijar batch size o tiempos. El procesamiento final puede volver a la PC actual tras medir su rendimiento.

## 1. Qué significa vectorizar aquí

Convertir cada recorte de carta en un **embedding visual** que conserve identidad y reduzca sensibilidad a condiciones de captura. Aplanar píxeles en un vector no proporciona esa robustez. DRAW2 ya contiene una red que produce representaciones internas, pero sus ONNX descargados son clasificadores: no asumir que sus salidas son embeddings apropiados para búsqueda.

Compararemos dos caminos: (A) clasificación DRAW2 tal como fue entrenada, con su mapa correcto; (B) encoder de embeddings y recuperación de referencias por similitud. El camino B permite indexar nuevas referencias sin ampliar necesariamente una cabeza de clasificación, pero su generalización a cartas nuevas debe medirse.

Las transformaciones geométricas tampoco garantizan invariancia por sí solas:

- Rotación y escala se describen mediante matrices; traslación entra en transformaciones afines.
- La perspectiva requiere una **homografía proyectiva**, no solo una transformación lineal de coordenadas 2D.
- Sombras, exposición y reflejos requieren tratamiento fotométrico y/o entrenamiento. CLAHE y gamma no son transformaciones lineales.
- Buscamos identidad estable frente al giro, pero **conservamos la orientación y la posición física** para representar AR y distinguir posiciones de juego. No eliminar esa información del estado.

## 2. Arquitectura propuesta

```text
Vídeo Android + timestamp
  -> detección de cartas y geometría
  -> control de calidad de cada recorte
  -> rectificación y orientación
  -> preprocesamiento validado
  -> encoder visual + normalización L2
  -> búsqueda top-k en catálogo de referencias
  -> verificación / rechazo / resolución de identidad
  -> seguimiento por copia física
  -> ID + esquinas + orientación + timestamp -> visualizador AR
```

Dos tareas separadas: **detectar dónde hay cartas** y **reconocer qué cartas son**. Aumentos del detector transforman también cajas/esquinas; los del identificador trabajan sobre recortes rectificados. No aplicar la misma receta ciegamente a ambos.

## 3. Preparar y trasladar los materiales

Copiar a la computadora de trabajo:

- `repos/draw2`, `repos/draw`, `repos/yugioh-one-shot-learning`, `repos/ygojson` como referencias, conservando sus licencias/commits.
- `downloads/reference-assets/`, especialmente detector ONNX, clasificador Small, su mapa de etiquetas y ZIP YGOJSON.
- `research/references-20260924/`: evaluación, manifiestos SHA-256, metadatos y mapa de etiquetas a YGOJSON.
- `data/captures`, `data/references`, `recognition.py`, `check_recognition.py`, `camera_viewer.py`, `web/` y este plan.

Recrear el entorno de investigación en destino; no copiar `.venv`. Elegir versiones compatibles con el runtime/hardware comprobados y congelarlas. Mantener los experimentos fuera del entorno del visor. Verificar hashes tras la transferencia.

No contamos todavía con todas las imágenes de referencia del catálogo moderno: YGOJSON contiene metadatos/URLs y el ZIP de imágenes descargado es retro. Preparar primero las imágenes del deck piloto y luego ampliar usando una fuente autorizada, caché y procedencia por imagen. No confundir catálogo de nombres, mapa de clases, pesos e imágenes de referencia: son artefactos distintos.

## 4. Datos reales y separación de pruebas

Piloto propuesto: 50 identidades de cartas, incluyendo pares de apariencia similar, distintos tipos, algunas ilustraciones alternativas, varias fundas y dos copias físicas simultáneas. Recoger 3–5 sesiones con cambios de luz, fondo, cámara/distancia y día. Anotar identidad, ilustración si es conocida, cuatro esquinas, visibilidad y condición de captura.

Usar imágenes canónicas como galería de búsqueda. Separar fotos/vídeos reales en entrenamiento, validación y prueba por sesión/dispositivo; no repartir fotogramas contiguos de un mismo vídeo entre particiones. Cuando sea posible, reservar copias físicas/fundas para evitar aprender arañazos o marcas. Los aumentos sintéticos se generan solo después de fijar los grupos.

Reservar además:

- Cartas no presentes en la galería, reversos y objetos rectangulares para rechazo.
- Un conjunto de identidades no usado al ajustar el encoder, pero con referencias incorporadas al evaluar: mide si agregar cartas funciona sin reentrenar.
- Variantes de ilustración conocidas y no conocidas, con métricas separadas.

Para un mismo card_id, diferentes ilustraciones son positivas al medir identidad. No tratarlas como negativos difíciles por accidente. Mantener artwork_id separado si también queremos determinar la ilustración.

## 5. Línea base antes de entrenar

1. Medir nuestro SIFT en las capturas disponibles y luego en el piloto.
2. Ejecutar el detector ONNX de DRAW2 sin clasificación; evaluar cartas omitidas, falsas cajas y error de esquinas.
3. Ejecutar DRAW2 Small con sus **13 659** etiquetas. El mapa del ViT principal tiene **13 820** y no es intercambiable.
4. Guardar aciertos, fallos y tiempos por etapa, modelo y condición. Comparar con un encoder congelado si se dispone de un checkpoint adecuado.

Estos resultados deciden si falla el detector, el recorte, la orientación o la representación visual. No entrenar el clasificador para compensar cajas mal recortadas.

## 6. Geometría y rotaciones

Calibrar intrínsecos/distorsión del teléfono para la cámara, resolución y zoom usados. Mantener calibración versionada. Conservar fotogramas originales y parámetros de transformación.

El detector DRAW2 devuelve rectángulos orientados. Sus vértices **no son necesariamente las cuatro esquinas reales de una carta con perspectiva**. Evaluar refinamiento por bordes, segmentación o un modelo de puntos clave cuando la inclinación lo exija. Rectificar solo con cuadriláteros válidos; rechazar geometría degenerada o recortes excesivamente truncados.

Orden de procesamiento: corregir distorsión si procede -> localizar/refinar cuadrilátero -> rectificar -> resolver orientación -> preparar entrada del encoder. Guardar homografía/inversa y geometría original. Para un modelo preentrenado, respetar inicialmente su tamaño, proporción y normalización; cambios de recorte requieren evaluación o ajuste.

Resolver 0/90/180/270 grados mediante orientación estimada. Si es ambigua, evaluar varias rotaciones y elegir por evidencia; medir el coste. En entrenamiento, añadir giros arbitrarios y error residual de rectificación. No usar reflejo horizontal como equivalente de rotación: altera letras y arte; corregir vídeo espejado en la entrada si existe.

## 7. Iluminación, sombras y calidad

Probar cada opción por separado y conservar solo lo que mejore validación:

| Perturbación | Tratamiento propuesto | Límite |
|---|---|---|
| Exposición/contraste | Aumentos de brillo, contraste y gamma; normalización requerida por el encoder | Evitar saturar artificialmente todas las muestras. |
| Luz cálida/fría | Variaciones moderadas de balance de blancos y color | No borrar colores que discriminan cartas. |
| Sombras locales | Máscaras suaves de atenuación y gradientes; comparar CLAHE moderado en luminancia | CLAHE puede amplificar ruido y modificar la distribución de entrada. |
| Reflejos de fundas/foil | Casos reales, pequeñas regiones especulares sintéticas y criterio de calidad | Un reflejo saturado puede ocultar información irrecuperable. Esperar otro fotograma. |
| Movimiento/desenfoque | Blur moderado y movimiento sintético; casos reales del teléfono | Un recorte ilegible debe rechazarse, no forzarse. |
| Cámara distante/comprimida | Reducción de resolución, ruido y compresión JPEG realistas | Registrar tamaño mínimo de carta que permite reconocimiento. |
| Mano/solapamiento | Oclusión parcial y entrenamiento con ejemplos reales | No asignar identidad nueva cuando la evidencia es insuficiente. |

Rangos iniciales orientativos, a ajustar mirando muestras: gamma 0.7–1.4, brillo/contraste ±20–30%, sombra suave con atenuación 0.4–0.9 y oclusión limitada al 10–20% del recorte en una fracción de muestras. No aplicar todos los extremos juntos. Antes de entrenar, exportar una cuadrícula de aumentos y comprobar que sigue siendo razonable identificar la carta.

La normalización de entrada y L2 de vectores son operaciones distintas: ninguna garantiza por sí sola invariancia a sombras.

## 8. Embeddings e índice

Probar extracción de la capa anterior al clasificador de un checkpoint accesible; definir por escrito pooling, dimensión y preprocesamiento. Los pesos entrenables del clasificador principal no se descargaron en la revisión inicial. Si el ONNX Small no expone una representación útil, obtener su checkpoint compatible o elegir un encoder disponible y documentar el cambio. No usar automáticamente logits de 13 mil clases como embedding.

Para cada referencia x, calcular `z = f(preprocesar(x))`, normalizar `z / ||z||` y buscar por producto interno/coseno entre vectores normalizados. Versionar encoder e índice juntos. La galería y las consultas deben usar el mismo modelo y procesamiento.

Comenzar con un vector por ilustración. Comparar, después, con pocas referencias reales/variantes por ilustración o prototipos normalizados. No vectorizar todas las combinaciones posibles de sombras/giros: la robustez debe provenir principalmente del encoder y la normalización geométrica. Más prototipos también elevan oportunidades de falsos positivos; recalibrar umbrales.

Para ~14 000 referencias, comenzar con búsqueda exacta matricial o `IndexFlatIP`; medir antes de introducir un índice aproximado. Ejemplo de memoria solo para vectores: 14 000 × 512 × 4 bytes ≈28.7 MB; con dimensión 768 ≈43 MB. No incluye pesos, índices auxiliares ni múltiples ilustraciones.

Guardar por fila: índice vectorial, UUID YGOJSON, card_id, artwork_id, hash de imagen y procedencia. El índice neuronal no es un ID universal. Resolver explícitamente las 16 etiquetas sin correspondencia y 12 ambiguas del cruce actual; no adjudicarlas por semejanza de nombres sin verificación.

## 9. Ajuste del encoder, solo si la línea base lo justifica

Entrenar primero una pequeña cabeza/proyección y después descongelar parte del encoder si mejora. Comparar pérdida contrastiva supervisada o triplet con negativos difíciles, manteniendo un objetivo coherente con la identidad buscada. Mezclar imagen canónica y foto real como positivos para reducir la diferencia entre catálogo y cámara.

Organizar batches con varias vistas por identidad; incluir cartas parecidas como negativos y distribuir tipos. Registrar semillas, datos, aumentos y checkpoint. Ajustar batch/precisión a VRAM medida; no prometer tiempos ni exigir una GPU concreta sin conocer la computadora.

Reentrenar detector y encoder como experimentos separados. Una mejora en recuperación no implica mejor localización.

## 10. Decisión y estabilidad temporal

Recuperar top-5/top-10 y reagrupar por identidad antes de comparar candidatos: dos ilustraciones de la misma carta no deben reducir falsamente el margen. Aceptar solo con similitud y separación suficientes respecto de la siguiente identidad, calibradas en validación con desconocidos.

Comparar verificación SIFT/ORB de candidatos cuando hay detalle suficiente. Usar el deck como prior opcional; conservar rechazo de cartas ajenas y no convertir toda observación en una carta del deck. No presentar similitud coseno como porcentaje de certeza.

Asociar objetos por geometría y movimiento; acumular evidencia en varias observaciones consistentes. Mantener track_id distinto de card_id para dos copias iguales. Evitar que una identificación errónea se perpetúe mediante historial. Después de ocultamientos ambiguos, volver a confirmar identidad.

## 11. Matriz de experimentos y aceptación

| Ensayo | Cambio frente al anterior |
|---|---|
| E0 | SIFT actual y DRAW2 Small intacto como baselines independientes. |
| E1 | Geometría/refinamiento y orientación corregidos. |
| E2 | Encoder congelado + galería vectorial + rechazo. |
| E3 | Ajuste con aumentos geométricos. |
| E4 | Añadir aumentos fotométricos/sombras. |
| E5 | Probar CLAHE/normalización opcional; aceptar solo si ayuda sin degradar casos normales. |
| E6 | Verificación de candidatos y seguimiento temporal. |
| E7 | Exportación/optimización para la PC de ejecución. |

Medir recall/precisión de detección y error de esquinas; top-1/top-5 de identidad; precisión entre resultados aceptados y fracción rechazada; falsos positivos en desconocidos; resultados por giro, sombra, funda y tamaño; latencia p50/p95 y cambios falsos de identidad por track. Medir rendimiento de extremo a extremo incluyendo captura, no solo inferencia.

Objetivos iniciales propuestos para el piloto: ≥95% de identidad correcta en cartas claramente visibles; ≤1% de falsas aceptaciones sobre al menos 300 observaciones desconocidas suficientemente independientes; ≥5 actualizaciones/s de reconocimiento y ≥25 FPS del visor con procesamiento desacoplado. Reportar intervalos de incertidumbre, especialmente si hay pocos errores. Son metas a validar, no resultados ni umbrales universales. No retocar el modelo después de mirar la prueba final sin crear una nueva prueba reservada.

## 12. Entregables y retorno a la PC

- Manifiesto de datos/splits y galería de aumentos revisada.
- Resultados E0–E7 con errores representativos, métricas por condición y recursos consumidos.
- Encoder ONNX, índice vectorial y metadatos, catálogo reducido, preprocesamiento y umbrales versionados.
- Comparación del modelo original frente a FP16/INT8 según hardware. Para INT8, usar calibración cuando el método la requiera; regenerar índice con el encoder desplegado y volver a medir rankings/rechazo.
- Prueba reproducible sobre vídeos reservados, instrucciones de instalación y hashes.
- Adaptador para el contrato del visor: card_id, artwork_id cuando pueda determinarse, esquinas, orientación, score no calibrado, estado de aceptación, track_id y timestamp. Mantener el método anterior seleccionable durante la comparación.

Orden de ejecución: **datos y baseline -> geometría -> embeddings -> aumentos/ajuste -> rechazo/seguimiento -> exportación**. Primer resultado esperable: un informe que demuestre en qué condiciones mejora sobre el prototipo actual, antes de añadir monstruos 3D.

## 13. Reconocimiento multilingüe: alemán, inglés, español, portugués y francés

Requisito del proyecto: reconocer la misma identidad de carta en impresiones **de, en, es, pt y fr**. El idioma de la carta física, el idioma de la interfaz y la identidad son datos independientes. Reconocer una carta alemana debe permitir mostrar su nombre y efecto en español si el catálogo contiene esa traducción. No se promete identificar la edición exacta a partir del dibujo.

### Representación y catálogo

- Mantener un `card_id` canónico común a todos los idiomas y resolverlo mediante el cruce de identificadores ya auditado. Conservar por separado `artwork_id`, `printing_id` si se conoce y `printed_language`, que puede ser desconocido.
- Auditar la cobertura real de YGOJSON para los cinco idiomas antes de construir la galería: nombres, textos, impresiones e imágenes disponibles por carta/idioma. No asumir que disponer de un nombre traducido implica tener una imagen de esa impresión. Registrar faltantes y fuente; no inventar traducciones oficiales.
- Empezar comparando embeddings del dibujo con embeddings de la carta completa y una combinación de ambos. El dibujo es un candidato a reducir dependencia del texto; medir si pierde detalles que distinguen cartas similares. Adaptar su recorte a los distintos diseños, incluyendo Péndulo, sin usar una ventana fija para todo el catálogo.
- Para el índice de dibujo, compartir referencia cuando la ilustración sea realmente la misma entre idiomas; conservar referencias adicionales cuando existan diferencias visuales. Para el índice de carta completa, registrar el idioma de cada referencia y evaluar si hacen falta varios prototipos por idioma. Mantener ilustraciones alternativas bajo la misma identidad sin confundirlas con cartas distintas.

### Datos y entrenamiento

Ampliar el piloto con un subconjunto emparejado: objetivo inicial de 15–20 identidades presentes en los cinco idiomas, preferentemente con ilustración equivalente, dentro de las 50 identidades propuestas. Es una meta de recolección, no material disponible actualmente. Si no se consiguen todas las combinaciones, publicar una matriz de cobertura y separar las conclusiones por idioma. Capturar impresiones reales con fundas, sombras, giros y tamaños variados; imágenes de catálogo por sí solas no validan el uso con cámara.

Anotar idioma, identidad, ilustración y sesión. Las vistas de una misma identidad en diferentes idiomas son positivos del aprendizaje contrastivo; otra identidad visualmente parecida es un negativo difícil. Balancear muestreo para que inglés no domine. Probar enmascarado ocasional de las zonas de texto para reducir dependencia del nombre, como experimento separado, manteniendo ejemplos completos. Superponer texto traducido artificialmente no sustituye fotos de impresiones reales.

Mantener las separaciones por sesión y copia física de la sección 4. Añadir una evaluación de transferencia entre idiomas: reservar un idioma del ajuste y probar consultas reales de ese idioma contra una galería que no incluya imágenes de esa misma impresión. Repetir para los cinco idiomas cuando la cobertura lo permita y distinguir este ensayo del reconocimiento con referencias multilingües disponibles.

### OCR como evidencia complementaria

Primero recuperar candidatos visuales. Si la resolución y calidad lo permiten, probar OCR local del nombre y de identificadores impresos para verificar o resolver candidatos. Evaluar soporte real para los cinco idiomas, acentos y caracteres como ä, ö, ü, ß y ç; conservar el texto original y usar una versión normalizada solo para búsqueda aproximada. Elegir el motor después de medir precisión y latencia en destino.

Cruzar el texto con los nombres localizados del catálogo. No exigir texto legible para aceptar una identidad visual suficientemente respaldada. Si OCR y visión discrepan con evidencia sólida, rechazar o esperar otro fotograma. La identificación del idioma se evalúa por separado y puede quedar desconocida aunque la identidad esté confirmada; nunca inferirlo únicamente del idioma de la referencia visual más cercana. OCR no garantiza reconocer ilustraciones inéditas ni recuperar texto tapado por reflejos.

### Experimentos y criterios de aceptación

Extender E2 con tres alternativas: dibujo, carta completa y combinación. Extender E3/E4 con positivos entre idiomas y balance de muestras. En E6, comparar con y sin verificación OCR. Cada comparación debe mantener las mismas particiones y medir su coste adicional.

Reportar top-1/top-5 de identidad, precisión de aceptaciones, cobertura/rechazo y latencia **por cada idioma**, además del promedio equilibrado y el peor idioma. Desglosar por ilustración conocida/nueva, condiciones de luz y tamaño. Si se implementa detección del idioma, reportar su precisión y cobertura por separado de la identidad.

La meta inicial de ≥95% de identidad en cartas claramente visibles debe evaluarse por idioma; un buen promedio no compensa fallos sistemáticos en uno de ellos. Indicar número de observaciones independientes e incertidumbre. Si faltan muestras de un idioma, marcarlo como pendiente de validación, no como soportado. Medir también falsos positivos de cartas desconocidas en los cinco idiomas.

Añadir a los entregables: informe de cobertura del catálogo, manifiesto de referencias con idioma, resultados multilingües, catálogo de nombres/textos localizados disponibles y política de nombre alternativo cuando falte traducción. Ampliar el contrato del visor con `printed_language` opcional y `display_language`; mantener `card_id` independiente de ambos. Este requisito entra desde la preparación de datos y el baseline, antes de entrenar o exportar.

## 14. Múltiples artes y acabados de rareza

Requisito explícito: una misma identidad puede aparecer con artes diferentes y con acabados cuya apariencia cambia mucho según luz, ángulo y funda. No equiparar rareza con ilustración ni asumir que cada archivo es una carta distinta.

Modelo de datos propuesto:

- `card_id`: identidad y reglas de la carta, común entre idiomas, artes y rarezas.
- `artwork_id`: ilustración; una identidad admite varias.
- `printing_id`: impresión/edición, cuando exista correspondencia fiable con el catálogo.
- `printed_language`: idioma impreso, independiente del arte.
- `rarity` y `finish`: rareza declarada y acabado observado, opcionales y con procedencia. No deducirlos solo por color/brillo de una foto.
- `reference_id`: imagen concreta, fuente, hash y condiciones conocidas. Varias referencias pueden representar la misma combinación anterior.

La primera entrega reconoce identidad. Arte, idioma, impresión y rareza pueden quedar desconocidos aunque la carta esté reconocida. Identificar el acabado exacto es una tarea adicional que necesita sus propias etiquetas y evaluación; no bloquear el reconocimiento principal por ello.

### Galería y aprendizaje

Indexar referencias por arte, agregando las puntuaciones por identidad al decidir. No promediar todos los artes de una carta en un único vector inicial: podría perderse la estructura visual de cada variante. Probar varios prototipos para un arte si los acabados producen diferencias medibles. Limitar y calibrar el efecto de tener más referencias para unas identidades que para otras.

En aprendizaje de identidad, diferentes artes, idiomas y acabados de una misma carta son positivos. Para una cabeza auxiliar de ilustración pueden ser clases distintas, pero su pérdida no debe contradecir el objetivo principal. Usar positivos de dificultad progresiva y evaluar si forzar artes muy distintos a coincidir perjudica la separación entre identidades parecidas.

Un arte nunca visto puede compartir poco contenido visual con la galería: los embeddings no garantizan reconocerlo. Evaluar ese caso explícitamente, recurrir a texto/identificadores legibles y aceptar desconocido cuando no haya evidencia. Incorporar referencias revisadas antes de declarar soporte para la nueva variante.

### Capturas de rarezas y reflejos

Añadir al piloto pares de la misma identidad y, cuando sea posible, del mismo arte con acabados distintos. Registrar acabado/rareza desde la impresión conocida, sin inferir etiquetas del nombre de archivo. Capturar secuencias cortas variando la dirección de luz y ángulo, con y sin funda: importa cómo evoluciona el reflejo, además de una foto aislada.

Entrenar y comparar aumentos de reflejos locales, variación cromática y contraste sobre ejemplos reales. Evitar tratar una sombra oscura como equivalente de una reflexión saturada. Conservar la opción de rechazar un fotograma y combinar evidencia de otros con zonas visibles. Probar selección temporal del recorte con mejor calidad antes de métodos más complejos.

Extender la prueba con grupos separados: arte y acabado conocidos; arte conocido/acabado reservado; arte reservado; combinación reservada de idioma y acabado; varias copias de igual identidad con acabados distintos simultáneas. Separar copias físicas y sesiones entre entrenamiento y prueba. Publicar métricas por grupo y suficientes ejemplos reales para no atribuir robustez a aumentos sintéticos únicamente.

### Colección CardsOricaBR

El usuario solicita descargar toda la carpeta pública, incluyendo sus subcarpetas. Usar `research/download_cardsoricabr.py`: inventario recursivo, archivos locales con ID Drive para evitar colisiones, ruta original conservada, SHA-256 y reanudación verificando archivos previos. Guardar originales en `downloads/cardsoricabr/` y derivar recortes aparte.

Descargar no equivale a aceptar todo como dato etiquetado: auditar duplicados, formatos, idiomas, artes y correspondencias con el catálogo. Mantener Rush Duel y material no verificado identificados por separado para decidir su uso después. No asignar arte/rareza por los sufijos `(2)`, `(3)`, etc. Verificar el manifiesto final y no afirmar descarga completa si quedan carpetas o archivos pendientes.

## Referencias técnicas

- [Recursos locales de The Dawn of a New Era: imágenes, sprites, idiomas y alias](tdoane/REVISION.md). Incorporar sus IDs de origen con un cruce revisado; no tratarlos todos como passwords oficiales. Sus imágenes digitales no sustituyen capturas reales de acabados y rarezas.

- [Evaluación de CardsOricaBR y YCCLP: muestra visual, descargas y plan de ingesta](references-20260924/FUENTES_IMAGENES_ADICIONALES.md). CardsOricaBR es candidato de galería, pendiente de cobertura multilingüe y auditoría; YCCLP aporta metadatos históricos, no imágenes para entrenar.

- [OpenCV: homografía y corrección de perspectiva](https://docs.opencv.org/4.x/d9/dab/tutorial_homography.html).
- [OpenCV: ecualización y CLAHE](https://docs.opencv.org/4.x/d5/daf/tutorial_py_histogram_equalization.html).
- [Torchvision: transformaciones de imágenes y anotaciones](https://docs.pytorch.org/vision/stable/transforms.html).
- [FAISS: coseno, normalización y producto interno](https://github.com/facebookresearch/faiss/wiki/MetricType-and-distances).
- [Inventario y límites de los recursos descargados](references-20260924/REVISION.md).
