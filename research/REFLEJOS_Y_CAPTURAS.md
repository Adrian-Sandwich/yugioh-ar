# Reflejos y capturas por carta — 25/09/2026

Investigación posterior: [estado del arte, candidatos y protocolo de evaluación](ESTADO_DEL_ARTE_REFLEJOS.md).

Se añadió al visor el panel «Reflejos y capturas por carta». Recargar con Ctrl+F5
http://127.0.0.1:8765. Solo cambian HTML/JavaScript: no hace falta reiniciar el
servidor ni alterar el entrenamiento pendiente.

## Funcionamiento implementado

- Usa la imagen original de cada análisis, nunca el sprite AR. Recorta hasta
  20 contornos detectados, incluidos los que no tienen identidad aceptada.
- En una miniatura de hasta 220 píxeles, excluye el exterior del polígono y
  mide la proporción de píxeles con los tres canales RGB >=245. Advierte a
  partir del 3%; es un umbral exploratorio, no calibrado con cartas foil.
- Para cartas identificadas compara hasta cuatro muestras dentro de diez
  segundos. Asocia por identidad, proximidad, tamaño y vecinos mutuamente
  más cercanos sin empate. Las copias iguales tienen muestras separadas.
- Compara tamaños similares y evita elegir una captura mucho más oscura;
  muestra a la derecha la muestra con menor proporción de blanco saturado.
- Descarta historial ante ausencia, identidad desconocida, caducidad o
  interrupción del reconocimiento. La comparación tiene edad visible al
  actualizar y está separada de las marcas del vídeo.

## Límites

Esto es una herramienta de diagnóstico; todavía no realimenta el detector
ni el OCR y no demuestra una mejora en reconocimiento. Blanco del dibujo
puede disparar el aviso; reflejos coloreados o no saturados pueden pasar
inadvertidos. Menos blanco no equivale necesariamente a más detalle.
La miniatura no es una medición fotométrica sobre los píxeles nativos y el
recorte es una caja con máscara poligonal, sin rectificación de perspectiva.
La asociación espacial no garantiza continuidad si se intercambian copias
iguales entre capturas; no se usa para propagar identidad en AR.

## Validación

`qa_card_quality.py`: prueba en navegador de dos instancias de la misma
identidad, reflejo localizado, elección de captura previa limpia, caducidad,
rechazo de asociación con carta desconocida, desaparición y recorte mínimo.
Ver resultados y captura en `qa/card-quality/`.

`qa_live_camera.py`: regresión aprobada; ocho fotogramas recibidos mientras
el primer análisis seguía ocupado. Comprueba recuperación de errores,
pausa/reanudación, reconexión y ausencia de errores JavaScript.

La comprobación adicional contra el servicio real recibió un análisis HTTP
200 y después respuestas 503 de reconocimiento ocupado. No consiguió dos
análisis en el plazo de 30 segundos, por lo que no se considera aprobada.
El vídeo siguió avanzando (102 fotogramas al terminar). La eficacia con foil
real y la comparación temporal en esa escena quedan por validar.

## Ensayo con las cartas del usuario

Procesamientos candidatos para evaluar, sin entrenamiento nuevo:

- Máscara de posibles reflejos por saturación, color y pérdida de textura;
  contrastarla entre capturas para distinguirla de zonas blancas impresas.
  Excluir regiones afectadas de correspondencias locales; no simplemente
  pintarlas de negro antes del encoder global, que no fue entrenado así.
- CLAHE sobre luminancia, conservando original y versión normalizada como
  alternativas. Ya existe una variante CLAHE para OCR; extenderla al arte
  requiere comparar aciertos y falsos positivos, no solo apariencia.
  [OpenCV CLAHE](https://docs.opencv.org/3.4.0/d2/d74/tutorial_js_histogram_equalization.html).
- Fusión temporal después de rectificar y registrar la misma instancia:
  elegir por región evidencia no saturada y nítida. Requiere que el reflejo
  cambie y que al menos una captura conserve el detalle; una mediana temporal
  ciega puede borrar texto o duplicar bordes si hay desalineación.
- Fusión de exposiciones si la cámara permite capturarlas: una exposición
  corta puede preservar altas luces. No separa por sí sola reflexión y tinta.
  [OpenCV HDR](https://docs.opencv.org/4.13.0/d2/df0/tutorial_py_hdr.html).
- Inpainting solo para presentación: rellena usando información vecina y
  no constituye evidencia del serial o del arte oculto. No alimentar con
  dígitos reconstruidos una identificación confirmada.
  [OpenCV inpainting](https://docs.opencv.org/5.0/main_modules/photo_inpaint.html).

Escena declarada: Utopía, Dragón Blanco de Ojos Azules, Dragón Negro de Ojos
Rojos, dos Dragones de Péndulo de Ojos Anómalos, Mago Oscuro y Juicio Solemne.
Son siete instancias y seis identidades; esta declaración no significa que
el detector ya encuentre las siete.

1. Mantener teléfono y cartas fijos, guardar una captura inicial.
2. Mover solo la luz hacia un lado o difuminarla. Comparar capturas, aviso de
   reflejo y número de identidades aceptadas; guardar el nuevo original.
3. Repetir con otra orientación de luz y registrar qué instancia falla.
4. Si se detecta el contorno pero falla el nombre incluso sin reflejo, revisar
   tamaño, enfoque y correspondencia del arte con las referencias del piloto.

Siguiente mejora posible: seleccionar recortes para OCR con nitidez y
reflejo evaluados en su zona concreta, y validar seguimiento geométrico
antes de mantener identidades durante fallos. No se implementaron en este
paso; entrenamiento especializado y trabajo adicional de vectores siguen
pospuestos por decisión del usuario.
