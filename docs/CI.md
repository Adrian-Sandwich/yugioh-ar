# Integración continua

`.github/workflows/ci.yml` corre en cada push a `main` y en cada pull request,
en Ubuntu con Python 3.14 y cuatro paquetes (numpy, opencv-python-headless,
onnxruntime y Pillow, con los mismos pins que `requirements-research.txt` y
`requirements-ocr.txt`).

## Qué corre

1. `python -m compileall -q .`: todos los módulos compilan.
2. Las pruebas `qa_*.py` que pasan en un clon limpio sin `data/`, sin
   `downloads/`, sin pesos ONNX y sin navegador (comprobado el 26/09/2026 en
   un clon temporal con esos tres paquetes):

| Prueba | Qué cubre |
|---|---|
| `qa_duel_engine.py` | motor de duelo completo |
| `qa_shared_snapshot.py` | una petición de cámara compartida entre clientes |
| `qa_sprite_cache.py` | composición de sprites, igualdad píxel a píxel con la referencia guardada |
| `qa_live_tracking.py` | seguimiento de esquinas en fotogramas sintéticos |
| `qa_camera_source.py` | stream MJPEG, respaldo por sondeo, cabecera de pistas |
| `qa_pipeline_core.py` | cola OCR, seguimiento, HTTP del visor con reconocedor simulado |
| `qa_card_geometry.py` | ajuste de esquinas sobre las imágenes de `research/qa` |
| `qa_card_evidence.py` | fusión de evidencias (sin verificador de arte, que se marca como no disponible) |
| `qa_enroll_reference.py` | inscripción de fotos anotadas como referencias |
| `qa_pose_from_captures.py` | conversión de anotaciones de la página de capturas al importador de YOLO11 |
| `qa_catalog_sync.py`, `qa_curated_registry.py`, `qa_download_watch.py`, `qa_printing_art_links.py` | sincronización y registro curado sobre bases temporales |

## Qué no puede correr en CI y por qué

- **Datos y modelos fuera de Git.** `data/`, `downloads/` y los pesos DRAW2
  no se distribuyen (imágenes de terceros, varios GB). Quedan fuera
  `qa_vision_pipeline.py`, `qa_geometry_recognition.py`, `qa_embedding_fast.py`,
  `qa_inference_host.py`, `qa_passcode.py`, `qa_name_ocr.py`, `qa_workspace.py`,
  `qa_registry*.py`, `qa_recognition_catalog.py`, `qa_printing_art_release.py`
  y `qa_identity_resolution.py` (necesita `data/curated`).
- **Navegador.** `qa_live_camera.py`, `qa_shared_camera.py`,
  `qa_passcode_browser.py`, `qa_browser.py`, `qa_registry_browser.py`,
  `qa_card_quality.py` y `qa_pose_annotations.py` usan Playwright con Edge.
- **OCR.** RapidOCR y sus modelos se instalan aparte (`requirements-ocr.txt`).

Pyright no está en CI: el repositorio tiene decenas de avisos previos por los
stubs de OpenCV y por atributos dinámicos del servidor HTTP; añadirlo exigiría
limpiarlos primero o silenciarlos, y silenciar no es limpiar.

## Suite local completa

Desde la raíz, con `.venv-eval` preparado según `research/ENTREGA_PILOTO.md`:

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 qa_pipeline_core.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_passcode.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_live_camera.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_shared_camera.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_passcode_browser.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_card_quality.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_sprite_cache.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_vision_pipeline.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_live_tracking.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_camera_source.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_inference_host.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_enroll_reference.py
.\.venv-eval\Scripts\python.exe -X utf8 qa_duel_engine.py
```

La lista histórica completa está en `research/PIPELINE_ESTADO.md`
("Verificación reproducible").
