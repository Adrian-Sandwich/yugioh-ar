# Reconocimiento especializado del passcode — 2026-09-25

**Pospuesto por decisión del usuario (25/09/2026).** Conservar referencias,
descargas y resultados; no continuar por ahora el desarrollo, entrenamiento
ni integración de este lector. Retomarlo en una etapa futura junto con el
[trabajo de vectores e invariancia](../PLAN_VECTORES_E_INVARIANCIA.md).
El OCR actual del visor se mantiene. Los siguientes pasos descritos abajo
son un plan futuro, no trabajo en curso.

Objetivo: leer los ocho dígitos de la esquina inferior izquierda incluso con
texto pequeño, desenfoque moderado, perspectiva, sombras o reflejos. El idioma,
arte y rareza pueden cambiar el aspecto sin cambiar el passcode. Conservarlo como
texto, incluidos ceros iniciales; admitir cartas sin passcode.

## Referencias revisadas y descargas

| Fuente | Disponible localmente | Qué rescatar / limitación |
|---|---|---|
| [thawro/yolov8-digits-detection](https://github.com/thawro/yolov8-digits-detection) | `repos/yolov8-digits-detection`, commit `b73467a263f95a47cba9fcc45d381144fb5c88bb`; cuatro modelos ONNX | Detector de diez clases, etiquetas de cajas y ejecución CPU. Pesos entrenados con manuscritos HWD+; requieren adaptación a tipografía de cartas. |
| [ScottXTra/BlurryNumberRecognition](https://github.com/ScottXTra/BlurryNumberRecognition) | `repos/BlurryNumberRecognition`, commit `d0b58844a7b5a50cce47a5e4fb9c86e353058c9c`; checkout completo, datos, fuente y `model.h5` de 601008 bytes | Generación de dígitos impresos degradados y CNN pequeña. Clasifica un dígito aislado de 32×32, no localiza ni lee una secuencia completa. Modelo descargado, aún no evaluado aquí. |
| [MarkertSean](https://markertsean.github.io/number_recognition/sklearn_model/) | Página archivada en `markertsean-sklearn.html` | PCA de imagen, proyecciones por filas/columnas y MLP: candidato a baseline económico. Su 97% corresponde a su experimento de dígitos manuscritos, no a códigos de cartas. |
| [Discusión OpenCV](https://stackoverflow.com/questions/37645576/how-to-classify-blurry-numbers-with-opencv) | Revisada; enlace conservado | Ideas de recorte, normalización y clasificación para un display. No aporta una solución validada para cartas. |
| [WT-MM/vit-base-blur](https://huggingface.co/WT-MM/vit-base-blur) | Ficha archivada en `vit-base-blur-model-card.md`; pesos no descargados | Clasificador binario entrenado con imágenes generadas por difusión con distintos pasos. No restaura texto ni hace OCR; su calidad en texto de cámara no está validada. |

No se encontró LICENSE en la raíz de ninguno de los dos repos clonados;
verificar permisos antes de redistribuir código, pesos o la fuente incluida.
La ficha del ViT declara Apache-2.0.

### Detalles relevantes del generador de Scott

`generate_images.py` genera 5000 ejemplos por dígito para entrenamiento y otros
5000 para validación, más 50 por dígito para prueba: 100500 imágenes.
Usa Arial, tamaño 20–26 sobre 32×32, desplazamiento, ruido gaussiano y desenfoque.
Hay dos puntos que corregir al diseñar nuestro generador:

- `randint(2, 3)` siempre produce 2: el desenfoque no varía como afirma el comentario.
- Pasar `angle` a `draw.text` no implementa una rotación de imagen. Aplicar una
  transformación explícita y transformar también las etiquetas.

También usa APIs antiguas (`textsize`, `fit_generator`). No se ejecutó su
entrenamiento ni se instaló TensorFlow en el entorno del visor.

## Prueba local ejecutada

Reproducir desde la raíz del proyecto:

```powershell
.\.venv-eval\Scripts\python.exe research/digit-references/evaluate_yolo.py
```

Se usaron los cuatro ONNX originales, CPU con un hilo y umbral 0.25. Resultados,
hashes SHA-256 de los modelos y detecciones individuales en `results.json`;
imágenes de entrada guardadas junto al informe.

| Entrada | Lectura YOLO, detecciones ordenadas por x |
|---|---|
| Foto real cercana, ROI estrecho, esperado `89631139` | Sin dígitos |
| Misma foto, ROI ancho | Sin dígitos |
| Recorte borroso del visor, sin transcripción independiente | Sin dígitos |
| Línea sintética impresa, lienzo de 48 px de alto | `89631139` |
| Misma línea reducida a lienzo de 20 px | `893139` |
| Misma línea reducida a lienzo de 12 px | `33` |
| Blanco | Sin dígitos |

Estas alturas son del lienzo, no de cada glifo. El ejemplo anotado del propio
repositorio produjo detecciones y sirvió solamente como comprobación del
pipeline. El orden por x no es todavía un lector de líneas con resolución de
solapamientos. No se forzó una salida de ocho dígitos.

El OCR actual, RapidOCR, volvió a leer `89631139` en la carta cercana rectificada,
con puntuación interna 0.8842. Esa puntuación no es una probabilidad calibrada.
YOLO tardó aproximadamente 66–115 ms por entrada en esta ejecución; no incluye
captura ni detector de carta. Esta muestra pequeña demuestra un fallo de
transferencia en estas imágenes, no una tasa de precisión general.

**Decisión:** conservar el lector actual en el visor y usar estas referencias
para entrenar y comparar un lector especializado. No desplegar los pesos
manuscritos como reemplazo del OCR. No se modificó ni reinició el servicio.

## Plan de implementación y entrenamiento en la otra PC

1. **Corpus y verdad de referencia.** Guardar ráfagas de JPEG originales y
   recortes del passcode con esquinas, tamaño nativo, sesión, cámara, identidad,
   impresión e idioma cuando se conozcan. Transcribir y revisar manualmente el
   código; el registro ayuda a verificar, no sustituye la etiqueta. Incluir
   negativos, copyright, códigos de set, cartas sin serial y copias con foil.
2. **Seleccionar evidencia temporal.** Por instancia física, mantener una
   ventana pequeña de recortes. Comparar nitidez, contraste, saturación por
   reflejos y estabilidad geométrica a escala nativa comparable. Elegir los
   mejores fotogramas antes del OCR; conservar la captura original. Ejecutar
   fuera del bucle de vídeo con cola acotada, como el worker actual.
3. **Datos sintéticos de nuestro dominio.** Renderizar códigos como cadenas de
   ocho caracteres y conservar cajas por dígito. Variar fuentes, espaciado,
   grosor y fondos de cartas. Añadir homografía, orientación, reducción hasta
   alturas reales de glifo, blur óptico y de movimiento, ruido, JPEG, sombras
   y reflejos. La homografía corrige perspectiva; el entrenamiento con
   transformaciones aporta tolerancia, no invariancia perfecta. No reducir
   todo a blur gaussiano ni enseñar solamente seriales existentes.
4. **Comparación controlada.** Baseline RapidOCR; baseline ligero PCA/HOG +
   clasificador para dígitos correctamente segmentados; detector YOLO afinado
   para dígitos impresos; lector compacto de secuencia de ocho dígitos con CTC
   y opción de rechazo. Comparar el sistema completo: la clasificación de un
   dígito con recorte perfecto no mide el problema de segmentación real.
5. **Validación sin fuga.** Separar cartas físicas/sesiones entre entrenamiento
   y prueba; reservar códigos y fuentes no vistos y degradaciones distintas.
   Reportar exactitud del código completo, errores por posición, falsos
   positivos en negativos, cobertura frente a rechazo, latencia p50/p95,
   CPU/RAM y resultados por tamaño nativo, idioma, impresión y foil. Una
   precisión por dígito del 97% sería aproximadamente 78% en ocho dígitos
   bajo la hipótesis simplificada de errores independientes.
6. **Integración.** Exportar el ganador a ONNX; usarlo inicialmente en paralelo
   para registrar resultados sin cambiar identidades. Aceptarlo solo si mejora
   códigos completos a igual tasa de falsos positivos y dentro del presupuesto
   de CPU medido. Exigir acuerdo en capturas distintas, validar `kind=passcode`
   y mostrar conflictos con la identificación visual. Conservar ceros iniciales
   y rechazar ambigüedad; no completar dígitos usando el catálogo.

Después se puede probar alineación y fusión de varios recortes originales,
comparándola con elegir el mejor fotograma. Una ampliación interpolada o una
restauración generativa no prueban que los trazos inventados correspondan al
número real. El límite debe medirse con imágenes y transcripciones reservadas.

Primer entregable siguiente: exportador de ráfagas/recortes etiquetables y
selector temporal de calidad; después generador reproducible y entrenamiento
fuera de esta PC. El reconocimiento especializado del passcode sirve para los
cinco idiomas; el código de set necesitará otro lector alfanumérico.
