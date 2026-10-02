> **Histórico.** Describe el estado de septiembre de 2026 y fue sustituido por [TIEMPO_REAL](TIEMPO_REAL.md). Índice de documentos: [docs/INDEX.md](../docs/INDEX.md).

# Pipeline de cámara: revisión y mantenimiento

Revisión del 25/09/2026 mientras continúa Neuron. No se cambiaron pesos,
referencias ni umbrales de reconocimiento. El entrenamiento de vectores y del
lector especializado sigue pospuesto.

## Recorrido actual

Estado consolidado y traslado: [TRANSFERENCIA_GENERAL.md](TRANSFERENCIA_GENERAL.md).
Ahora la adquisición comparte peticiones concurrentes al mismo origen durante
150 ms, conservando fecha original y sin devolver éxitos viejos ante errores.
La búsqueda del registro usa lotes y rutas exactas; YOLO11-pose sólo está en
experimentos y no sustituye el detector de producción.

Actualización posterior: [GEOMETRIA_CARTAS.md](GEOMETRIA_CARTAS.md) documenta el
ajuste de bordes anterior al encoder y al OCR, sus pruebas y limitaciones.
Las cajas no resueltas se conservan para reconocimiento visual, se marcan como
aproximadas y no producen recortes de texto. Incluye lectura del nombre: ver [OCR_NOMBRE.md](OCR_NOMBRE.md).

1. `web/camera.js` solicita `/snapshot` aproximadamente cada 200 ms, con una
   única petición de cámara en curso. `camera_viewer.py` obtiene el JPEG del teléfono.
2. El bucle de reconocimiento envía el JPEG original más reciente a `/analyze`.
   Las pestañas del mismo origen y perfil de navegador coordinan el turno con
   Web Locks y comparten resultados por BroadcastChannel. El servidor conserva
   su lock y el rechazo 503 tras dos segundos para otros clientes concurrentes.
3. `vision_onnx.py` detecta hasta 20 cajas orientadas, rectifica y compara las
   orientaciones 0/180 con el catálogo del piloto. Conserva candidatos rechazados.
4. El seguimiento asigna instancias y confirma tras dos observaciones. La capa
   AR usa geometría de la captura analizada. En vídeo se retira a los 2.5 s desde
   la solicitud de captura; el panel detallado conserva la imagen de referencia.
5. `passcode_ocr.py` recibe el JPEG y contornos en una cola separada: un trabajo
   activo y uno pendiente reemplazable. Procesa hasta seis cartas por lote.
6. El navegador consulta `/passcodes`. El OCR no sobrescribe la identidad visual:
   conserva ambigüedades, conflictos y número exacto observado.

## Correcciones aplicadas

- **Menos repintados:** el canvas de vídeo se actualiza cuando llega otro
  fotograma, cambia la capa AR o vence el resultado. Antes volvía a dibujar el
  mismo JPEG de resolución completa a la frecuencia de refresco de pantalla.
- **Respuestas obsoletas:** comprobación de generación antes y después de las
  operaciones asíncronas. Pausar, cambiar reconocimiento o perder señal invalida
  pinturas pendientes. Una respuesta antigua no debe actualizar nombres ni OCR.
- **OCR por tamaño:** si la altura estimada del dígito es menor de 7 px, conserva
  el zoom y pide acercamiento, pero omite las seis inferencias. Ese era ya el
  mínimo para confirmar consenso; ahora también evita trabajo sin confirmación
  posible. La estimación es heurística (`altura nativa de carta * 0.015`), no una
  medida del glifo. Puede omitir alguna lectura candidata pequeña: queda explícito
  como `ocr_skipped=small_text`. El lector offline conserva sus pruebas completas.
- **Reparto del OCR:** rota por lotes realmente procesados, no por número de
  solicitudes. Descartar trabajos pendientes ya no fija accidentalmente siempre
  el mismo subconjunto cuando la escena y el orden de cajas son estables.
- **Cierre y carga fallida:** el trabajador descarta pendientes al cerrar, deja
  de aceptar trabajo si no cargó y revisa cierre entre cartas.
- **Seguimiento:** una detección con `card_id` válido no requiere además `id`.
- **Errores del modelo:** un fallo inesperado produce HTTP 500 y traceback en
  el log; libera el lock para la siguiente solicitud.
- **Servicio ocupado:** HTTP 503 conserva el último resultado y los diagnósticos;
  reintenta con una pequeña variación del intervalo para evitar sincronizar
  pestañas. No reinicia la sesión OCR. Las marcas de vídeo siguen caducando.
- **Observabilidad:** `/analyze` incorpora `pipeline_ms`: espera del lock,
  captura, reconocimiento, posprocesado y total. No incluye descarga del cuerpo
  POST, serialización JSON ni envío al navegador. En POST, `capture` contiene
  solo preparación local; la captura del teléfono ya ocurrió en otra petición.
- **Edad de captura:** `/snapshot` devuelve `X-Captured-At`, tomado antes de
  solicitar el JPEG al teléfono. El navegador lo envía en POST; el servidor lo
  conserva en resultado y OCR, junto con `received_at`, `completed_at` y
  `capture_time_basis`. Rechaza valores no finitos, más de 1 s en el futuro o
  más de 60 s antiguos. No es la hora de exposición del sensor, que IP Webcam
  no proporciona aquí. Clientes antiguos sin encabezado usan hora de recepción.
- **Pestañas:** una pestaña obtiene el turno de reconocimiento y transmite el
  resultado original a las demás. Pausa y activación son locales. Los seguidores
  calculan antigüedad con la fecha de origen, no con la recepción del mensaje;
  ignoran resultados anteriores al último aceptado o a su reinicio de sesión.
  Si Web Locks/BroadcastChannel no están disponibles, se conserva el modo
  anterior con protección del servidor. Cerrar una pestaña libera el turno del
  navegador; no cancela una inferencia nativa que ya esté corriendo.

## Verificación reproducible

Desde la raíz, con `.venv-eval` preparado:

```powershell
.\.venv-eval\Scripts\python.exe qa_pipeline_core.py
.\.venv-eval\Scripts\python.exe qa_passcode.py
.\.venv-eval\Scripts\python.exe qa_live_camera.py
.\.venv-eval\Scripts\python.exe qa_card_quality.py
.\.venv-eval\Scripts\python.exe qa_shared_camera.py
.\.venv-eval\Scripts\python.exe qa_sprite_cache.py
.\.venv-eval\Scripts\python.exe qa_passcode_browser.py
# 26/09/2026 (noche), ver TIEMPO_REAL.md:
.\.venv-eval\Scripts\python.exe qa_vision_pipeline.py
.\.venv-eval\Scripts\python.exe qa_live_tracking.py
.\.venv-eval\Scripts\python.exe qa_camera_source.py
.\.venv-eval\Scripts\python.exe qa_inference_host.py
.\.venv-eval\Scripts\python.exe qa_enroll_reference.py
.\.venv-eval\Scripts\python.exe qa_duel_engine.py
```

Las pruebas de navegador requieren Edge y Playwright. Resultados en
`research/qa/pipeline-core.json`, `research/qa/passcode/validation.json`,
`research/qa/live-camera.json` y `research/qa/card-quality/validation.json`.
Los errores 500/502 simulados durante las pruebas son deliberados.

La prueba de cámara simulada exige que avance durante una inferencia de tres
segundos, comprueba recuperación, pausa/reconexión y rechaza una pintura tardía.
También comprueba que no se repinte continuamente el mismo fotograma. La prueba
OCR conserva la lectura real `89631139`, ceros iniciales y consenso conservador.
Esto verifica funcionamiento; no mide precisión general ni aceleración en GPU.

Antes del coordinador entre pestañas, la sonda del servicio real recibió 135 fotogramas
y una respuesta de análisis HTTP 200, pero no alcanzó los dos análisis completados
exigidos en 30 s: hubo varios HTTP 503 por inferencia ocupada. Esa comprobación
no se considera aprobada. No se promete rendimiento estable bajo solicitudes
concurrentes; los tests controlados y la continuidad de vídeo se reportan aparte.

Con el coordinador, `qa_shared_camera.py` verificó dos pestañas del mismo contexto:
misma fecha de análisis recibida, una sola inferencia simultánea, todas las
respuestas de análisis HTTP 200, pausa independiente y relevo al cerrar una
pestaña. Informe `research/qa/shared-camera.json`. La prueba del OCR en navegador
conservó la lectura real `89631139` y no confirmó una foto fija como capturas distintas.

## Límites y siguiente trabajo

### Segunda revisión con Codebase Memory

Se consultaron `search_graph` y `trace_path` mediante la CLI de Codebase Memory
porque la conexión integrada de Codex seguía cerrada. Evidencia en
`research/qa/cbm-diagnostic/search.json` y `trace-encoder.json`. El grafo sugirió
llamadores del encoder que se verificaron en el fuente. Algunas aristas de salida
apuntan a OCR sin llamada directa correspondiente; no tratarlas como prueba de
dependencia real. La cobertura también señalaba `metadata_changed`.

**Aplicado:** `Encoder.predict(..., classify=False)` omite softmax, ordenamiento
y traducción del ranking de clasificación cuando solo se necesitan embeddings.
Lo utilizan el reconocimiento por embeddings y la construcción del índice.
El modo clasificador conserva el comportamiento previo. No se alteran el forward
ONNX, los pesos, vectores almacenados ni umbrales.

**Validación:** `qa_embedding_fast.py` compara ocho imágenes reales de la muestra
con el modelo instalado. Los vectores normalizados y las puntuaciones del piloto
son idénticos bit a bit; la prueba comprueba además que se omite softmax y que el
modo clasificador sigue devolviendo cinco candidatos. Informe:
`research/qa/embedding-fast.json`. No se ha medido una ganancia de latencia.

**Cambios derivados de la revisión y pendiente restante:**

1. **Caché de sprites aplicada:** `SpriteOverlay` conserva hasta 16 lienzos
   preparados en LRU (unos 16.4 MB de píxeles adicionales). Reutiliza la
   preparación entre cartas y fotogramas, invalida si se sustituye el array
   original y ofrece `clear_cache(ref)` o `clear_cache()` para cambios de assets.
   No modificar arrays cacheados in situ sin invalidar. `qa_sprite_cache.py`
   verifica igualdad píxel a píxel contra ocho resultados guardados antes del
   cambio, superposición, alfa, reutilización, reemplazo y expulsión LRU.
   Informe: `research/qa/sprite-cache.json`. Ahora la composición float32 usa
   solo la región ocupada: en capas transparentes incluye también las regiones
   previas para preservar exactamente el redondeo original. Las ocho imágenes
   de referencia siguen siendo idénticas píxel a píxel y se verifica una región
   menor al fotograma. La homografía aún genera un buffer de fotograma completo;
   no se afirma una ganancia medida de latencia ni que se haya eliminado ese buffer.
2. `LiveRecognizer.analyze_jpeg` busca referencias linealmente y consulta nombres
   fuera del piloto repetidamente en modo clasificador; usar índices y caché
   con reglas explícitas de invalidación.
3. Coordinación entre pestañas aplicada y probada, según la sección anterior.
4. Fecha original de solicitud de captura preservada hasta OCR y navegador.

La optimización aplicada requiere reiniciar el proceso Python. La simple
recarga del navegador solo actualiza el JavaScript.

- ONNX continúa ejecutando secuencialmente dos orientaciones por candidato.
  Un timeout del navegador no cancela el forward nativo: el lock sigue ocupado
  hasta que termina. Un bloqueo nativo real requeriría aislamiento por proceso
  con reinicio controlado; el watchdog actual solo registra stacks a los 20 s.
- El coordinador actúa entre pestañas actualizadas del mismo origen y perfil.
  Otros perfiles, navegadores, clientes HTTP o pestañas sin recargar pueden
  competir por el lock. Cada pestaña todavía solicita su propio vídeo al teléfono;
  compartir adquisición sería otro cambio. No hay aislamiento de tracker/OCR
  entre clientes externos; usar el visor coordinado para evaluaciones controladas.
- Las peticiones de cámara tienen timeout de 8 s; los fallos de red pueden dejar
  visible la última imagen, etiquetada como sin señal. No confundir esto con
  inferencia bloqueada.
- La rotación de lotes OCR no es seguimiento de todas las cartas omitidas.
  Cambios de orden o geometría todavía pueden reiniciar consenso.
- Siete píxeles es un filtro conservador pendiente de calibrar con más capturas.
  No convertir ampliación de imagen ni restauración aprendida en evidencia del serial.
- Medir tiempos controlados en la siguiente PC; consultar
  [TRANSFERENCIA.md](glare-benchmark/TRANSFERENCIA.md). Los modelos de eliminación
  de reflejos siguen fuera del camino de vídeo: la muestra local no mejoró las
  cuatro identidades aceptadas de siete cartas.

Los cambios Python requieren reiniciar los servicios de cámara/demo. Después,
recargar el navegador para usar el JavaScript nuevo. `start_lab.ps1` conserva
procesos existentes y por sí solo no recarga su código. Neuron y el registro
son servicios independientes y no necesitan reiniciarse por estos cambios.

## Revisión con Codebase Memory y limpieza (25/09/2026, tarde)

Índice reconstruido con nombre `yugioh` (modo `moderate`, `.cbmignore` amplía
la exclusión a `.venv-pose/`, `transfer/` y `Ultralytics/`). Ver
[CODEBASE_MEMORY.md](CODEBASE_MEMORY.md) para las advertencias vigentes.

### Stall log del 25/09 11:08 (`.runtime/camera-8765-stall.log`)

El watchdog de 20 s se disparó una vez en el servicio de cámara en vivo. La
traza muestra el hilo de la petición `POST /analyze` dentro de
`onnxruntime ... run` llamado desde `Encoder.predict` en `ResearchRecognizer.detect`,
el hilo de OCR esperando trabajo y el servidor en `serve_forever`. No es un
interbloqueo: es un forward del encoder que superó 20 s. A esa hora corrían las
restauraciones de reflejos (`glare-benchmark/outputs/docshrnet` 11:05,
`mimo-shdocs` 11:13, PyTorch en CPU) además de Neuron y los servicios, así que la
explicación más plausible es saturación de CPU. Sigue pendiente el aislamiento
de ONNX en proceso recuperable; el watchdog sólo registra pilas. Los números de
línea corresponden a la versión de `camera_viewer.py` de esa hora.

### Cambios aplicados

- **Capa AR sólo en el cliente:** `/analyze` ya no compone ni codifica una segunda
  imagen JPEG con los sprites; envía `ar_layer` (PNG transparente) y el navegador
  la dibuja sobre el JPEG original en el panel de análisis. `ar_image` desaparece.
  Comprobado con `qa_live_camera.py` (sprites transparentes con píxeles negros)
  y `qa_shared_camera.py`.
- **Sprites ausentes cacheados:** `SpriteOverlay` guarda `None` para referencias
  sin asset y deja de consultar SQLite en cada fotograma; `clear_cache` sigue
  siendo la invalidación explícita.
- **Nombres fuera del piloto:** `LiveRecognizer` cachea los nombres de identidades
  del clasificador que no están en el piloto (límite 2000 entradas, catálogo de
  sólo lectura durante el proceso). Cierra el pendiente 2 de la sección anterior.
- **Registro en el OCR:** una conexión de sólo lectura por lote en lugar de una
  por carta; `lookup(code)` conserva su firma para las pruebas.
- **Visor:** `qualityTracks` se declara antes de `clearRecognition`, que ya la usaba
  (zona temporal muerta latente); `refreshPasscodes` se divide en funciones de
  render por tarjeta sin cambiar el DOM generado.
- **Geometría:** ajuste por bordes de croma para cajas no resueltas; ver
  [GEOMETRIA_CARTAS.md](GEOMETRIA_CARTAS.md).
- **Limpieza:** `qa_workspace.py` crea su carpeta temporal dentro de `.runtime/`
  y tolera archivos SQLite bloqueados (antes dejaba `tmp*` en la raíz). Los
  scripts de pose crean `.runtime/ultralytics-pose` antes de importar Ultralytics,
  que de lo contrario escribe `Ultralytics/settings.json` en la raíz (con
  `sync` e integraciones activadas). Se eliminaron esos restos.
- `name_ocr.TitleReader.read` pierde una lista sin uso; `vision_onnx` una
  importación sin uso.

### Verificación

Pasan `qa_pipeline_core`, `qa_passcode`, `qa_sprite_cache`, `qa_shared_snapshot`,
`qa_card_evidence`, `qa_workspace`, `qa_name_ocr`, `qa_embedding_fast`,
`qa_card_geometry`, `qa_geometry_recognition`, `qa_card_quality`,
`qa_passcode_browser`, `qa_live_camera` y `qa_shared_camera` con `.venv-eval`
(Python 3.14.7, OpenCV 5.0.0, onnxruntime 1.30.0) mientras Neuron y los cuatro
servicios seguían activos. Los servicios en ejecución usan el código anterior
hasta reiniciarlos. No se midió latencia de extremo a extremo.

### Arte de YGOPRODeck y verificación de candidatas (25/09/2026, tarde)

`research/download_ygoprodeck_art.py` descarga y aloja el arte recortado de
todas las ilustraciones del registro; `art_verify.py` comprueba con SIFT y
homografía los candidatos del embedding dentro del trabajador de OCR y
`card_evidence` lo fusiona como fuente `art`. `/analyze` envía ahora
`candidate_ids` (top-3) al trabajador. Resultados y límites en
[ARTE_YGOPRODECK.md](ARTE_YGOPRODECK.md). Coste en el hilo asíncrono:
143–380 ms por carta con tres candidatas en esta PC cargada; `/analyze` no cambia.

`qa_live_camera.py` interceptaba `createImageBitmap` para retrasar una pintura
tardía; con la PC cargada el bucle de cámara llegaba antes y la espera quedaba
colgada sin límite. Ahora sólo retrasa el `fetch` de la imagen de análisis
(URL `data:`); el comportamiento probado del visor no cambió.
