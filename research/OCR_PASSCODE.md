# Zoom y lectura del passcode

Actualización: ver [GEOMETRIA_CARTAS.md](GEOMETRIA_CARTAS.md). Las OBB se ajustan
a bordes visibles antes de recortar. Si el ajuste falla, no se muestra un
recorte de texto ni se ejecuta OCR. Se incorpora [OCR del nombre](OCR_NOMBRE.md),
y alternativas del extremo opuesto cuando hay duda de orientación.

Implementado el 25/09/2026. El visor en http://127.0.0.1:8765 incluye **Zoom al identificador**, debajo de las vistas de cámara y último análisis. Recargar con Ctrl+F5 tras actualizar.

## Flujo

1. Se aprovechan las cuatro esquinas detectadas, incluso para candidatos cuya ilustración no alcanzó el umbral de identidad. No hace falta reconocer primero el nombre de la carta.
2. Se rectifica la perspectiva desde el JPEG original, no desde la entrada reducida de 224 px del reconocedor visual. La imagen normalizada mide 630 × 920; ese tamaño no significa que se hayan capturado más detalles.
3. Se ensayan dos recortes inferiores izquierdos y una variante de contraste local, en orientaciones 0/180. Las esquinas orientadas del detector ya proporcionan el eje largo de la carta; invertirlas resuelve la alternativa arriba/abajo.
4. [RapidOCR](https://github.com/RapidAI/RapidOCR), versión 3.9.2 con modelo PP-OCRv6 rec small, lee solamente las líneas recortadas. [Documentación del reconocimiento sin detector de texto](https://rapidai.github.io/RapidOCRDocs/main/en/install_usage/rapidocr/usage/). No usa el nombre previsto ni la lista de passcodes para fabricar una lectura.
5. Sólo números de exactamente ocho dígitos pasan a la consulta SQL de `identifiers.kind='passcode'`. Se conservan ceros iniciales, no se añaden dígitos ausentes ni se convierten O/0 automáticamente. Un ID de imagen no es evidencia de passcode.
6. Se muestran coincidencias exactas, ambigüedades, números ausentes de la base y discrepancias con la identificación visual. El OCR no sobrescribe automáticamente la identidad visual ni modifica el registro.

Las regiones efectivas están en `passcode_ocr.REGIONS`: `tight=[0,.970,.28,1]`, `wide=[0,.948,.49,1]`. Difieren de las propuestas iniciales de `card-anatomy/anatomy.json`: al probar el recorte real comprobamos que excluir el borde izquierdo cortaba el primer dígito. Son regiones iniciales para diseños convencionales, no calibración universal de todos los layouts.

## Qué significan los estados

- **Lectura candidata:** existe una coincidencia pero todavía no hay suficientes capturas concordantes o detalle suficiente.
- **Lectura repetida y coincidencia en la base:** al menos dos JPEG diferentes del mismo objeto espacial repiten el número, con score OCR ≥0.85, estimación de dígitos de al menos 7 px y una sola identidad en el registro. No significa certeza absoluta: los umbrales son experimentales y puede repetirse un error sistemático.
- **Lecturas contradictorias / varias identidades / conflicto visual:** se conserva la duda. Dos códigos con scores separados por menos de 0.08 se consideran ambiguos.
- **Sin lectura fiable:** no se extrajo un número completo. Algunas cartas no tienen passcode; también puede faltar detalle, foco, orientación o contraste.

La confirmación exige nuevas imágenes: volver a leer la misma fotografía o varias versiones de contraste del mismo fotograma no suma votos. Los objetos se asocian por proximidad espacial; cruces, cambios de carta en el mismo lugar u oclusiones pueden requerir nueva confirmación. Un fallo de lectura reinicia la secuencia concordante.

El tamaño estimado de los dígitos usa aproximadamente el 1.5 % del alto original de la carta. Es una guía para acercar el teléfono, no una medición tipográfica exacta. La vista normalizada reduce el movimiento del recorte, pero no implementa seguimiento óptico ni suaviza las esquinas antes de leer: mezclar posiciones de fotogramas distintos puede cortar o emborronar caracteres.

## Ejecución y rendimiento

El OCR se ejecuta en un trabajador separado con un hilo de inferencia CPU. Hay un trabajo activo y un único trabajo pendiente, sustituible por el más reciente. No se acumulan fotogramas antiguos ni se bloquea la captura. Si aparecen más de seis cartas, se rota el grupo procesado en cada trabajo.

`/passcodes` devuelve el último resultado, recortes PNG, número observado, lecturas originales, tamaño nativo, estados y antigüedad. El visor lo consulta por separado. La base abre conexiones de sólo lectura y la descarga de Neuron sigue funcionando.

En la fotografía de referencia de Blue-Eyes (carta de unos 478 × 710 píxeles originales), el OCR leyó **89631139** con score 0.8842 y aproximadamente **602 ms** para las seis variantes. Esto es una prueba concreta, no una tasa de precisión general ni una garantía de tiempos en vivo. Guardamos recortes y resultado en `research/qa/passcode/`.

La prueba inicial con el teléfono detectó cuatro cartas de aproximadamente 275–297 × 409–429 píxeles originales; produjo los cuatro recortes en 1,798 ms de OCR, sin bloquear el vídeo. No obtuvo passcodes completos: el tamaño estimado de dígito era de 6.1–6.4 píxeles. El resultado se registra como no legible y el visor pide acercar la cámara; no se presenta como una identificación exitosa. Evidencia en `research/qa/passcode/live-result.json`.

## Instalación reproducible

Después de instalar `requirements-research.txt`:

```powershell
.\.venv-eval\Scripts\python.exe -m pip install -r requirements-ocr.txt
.\.venv-eval\Scripts\python.exe -m pip install --no-deps rapidocr==3.9.2
```

Se instala RapidOCR sin resolver de nuevo sus dependencias porque el proyecto ya proporciona `cv2` mediante `opencv-python-headless`. Su metadato pide `opencv_python`: `pip check` puede señalar esa diferencia de distribución aunque la API esté disponible y las pruebas pasen. Evitamos instalar dos distribuciones que escriben sobre el mismo módulo `cv2`.

Los modelos vienen en el paquete descargado; no se envían imágenes a servicios externos. Rutas, tamaños y SHA-256 están en `research/qa/passcode/models.json`. El motor se inicia automáticamente con el reconocedor; `--no-passcode` lo desactiva. Si faltan dependencias, el visor informa del error del lector y la cámara continúa.

## Validación

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 qa_passcode.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_passcode_browser.py
```

Pruebas de perspectiva, orientación invertida, ceros iniciales, imagen vacía, carta cortada, fotografía real, consulta tipada de IDs, desacuerdo visual, poca resolución, copias separadas y cola que conserva el trabajo más nuevo. La prueba de navegador muestra recortes reales, busca el número y comprueba que la cámara continúa mientras se ejecuta el OCR.
