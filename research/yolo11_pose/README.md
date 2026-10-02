# YOLO11: cuatro esquinas por carta

Experimento preparado el 25/09/2026. **No es el detector del visor.**

## Estado comprobado

- Entorno separado `.venv-pose`: Ultralytics 8.4.163, PyTorch 2.14.0 CPU,
  Python 3.14.7. Dependencias exactas en `requirements-pose-lock.txt`.
- Checkpoints oficiales `yolo11n-pose.pt` y `yolo11s-pose.pt`, URLs y SHA256 en
  `downloads/reference-assets/yolo11-pose/manifest.json`. Son pesos de pose
  genérica usados como punto de partida, no pesos entrenados para cartas.
- Una clase `card`, cuatro puntos con orden anatómico **TL, TR, BR, BL**;
  al girar la carta los índices siguen a la carta, no a la pantalla.
- Se mantiene C2PSA nativo. No se añadieron cabezas de atención nuevas.
- Dataset sintético `data/pose/bootstrap-v1`: 48 imágenes de entrenamiento,
  12 de validación, 116 instancias. Proyección, giros, oclusiones, iluminación
  y desenfoque simples. Los artes de una identidad permanecen en una partición.
  **No reproduce de forma realista las fundas, el foil ni todos los fondos.**
- Validación de etiquetas, coordenadas y separación por identidad: aprobada.
- Prueba de una época a 320 px, batch 2, CPU completada para ambas variantes:
  `runs/yolo11n-smoke-3` y `runs/yolo11s-smoke`. Son pruebas de funcionamiento,
  **no modelos útiles para desplegar**. El evaluador con n no detectó ninguna
  de las 9 instancias en sus primeras cuatro imágenes de validación a conf .25.
  No interpretar esos tiempos como el rendimiento de un detector ya entrenado.

## Preparar datos reales

Dos vías, y las dos acaban en `import_annotations.py`:

1. **Página de capturas** (http://127.0.0.1:8768/capture), la que sigue el
   [protocolo de capturas](../PROTOCOLO_CAPTURAS.md): guarda una anotación por
   carta en `data/pilot/captures/annotations.jsonl`. Como no tiene casilla de
   "marqué todas las cartas", las sesiones exhaustivas se declaran al convertir:

   ```powershell
   .\.venv-eval\Scripts\python.exe research/yolo11_pose/from_captures.py data/pilot/captures data/pose/from-captures-v1 --exhaustive-sessions <sesion1> <sesion2>
   ```

   Sólo sirve si en esas sesiones se marcó **cada carta completa de cada
   foto**; una carta sin marcar se convierte en falso negativo. Prueba:
   `qa_pose_from_captures.py`.
2. **Anotador de pose** (abajo), necesario para negativos (fotos sin cartas),
   que la página de capturas no admite.

Abrir http://127.0.0.1:8767/pose-annotator o la misma ruta en el puerto 8765.
Seleccionar una foto, indicar sesión y partición, marcar TODAS las cartas
completas y confirmar revisión. Exportar JSON junto a la foto original.
Las fotos parcialmente anotadas no sirven como entrenamiento: las cartas sin
etiquetar se convertirían en falsos negativos. Para escenas con cartas ocultas
o cortadas queda pendiente un anotador con visibilidad y cajas explícitas.

La herramienta actual acepta también negativos revisados: imágenes sin cartas.
Debe haber sesiones distintas para entrenamiento, validación y prueba; el
importador rechaza sesiones mezcladas, imágenes duplicadas y hashes incorrectos.

```powershell
.\.venv-pose\Scripts\python.exe research/yolo11_pose/import_annotations.py data/pose/anotaciones-revisadas data/pose/real-v1
```

El directorio de salida debe ser nuevo. `train_ready=false` significa que
faltan particiones. El importador valida estructura, no puede comprobar que
un humano haya hecho clic sobre el borde correcto ni detectar cartas omitidas.

## Entrenamiento y evaluación en destino

Recrear el entorno, instalar PyTorch apropiado para la GPU desde el instalador
oficial y comprobar `torch.cuda.is_available()` antes de elegir `--device 0`.
El lock corresponde a esta PC; si no es compatible con destino, registrar las
versiones nuevas y repetir las pruebas. No copiar `.venv-pose` entre equipos.

```powershell
.\.venv-pose\Scripts\python.exe tools/doctor.py --torch --output research/qa/destino-pose.json
.\.venv-pose\Scripts\python.exe research/yolo11_pose/train.py --size n --data data/pose/real-v1/dataset.yaml --device 0 --epochs 100 --batch 8
.\.venv-pose\Scripts\python.exe research/yolo11_pose/train.py --size s --data data/pose/real-v1/dataset.yaml --device 0 --epochs 100 --batch 8
```

100 épocas y batch 8 son una configuración inicial, no una garantía. Ajustar
batch a VRAM. Comparar n/s con mismas sesiones, semilla, resolución y política
de entrenamiento. Las transformaciones geométricas de Ultralytics y espejos
están desactivados explícitamente: el bootstrap ya transforma puntos e imagen
juntos y no queremos invertir el texto. Diseñar aumentos adicionales sobre
las fotos reales antes del entrenamiento definitivo.

```powershell
.\.venv-pose\Scripts\python.exe research/yolo11_pose/evaluate.py --weights research/yolo11_pose/runs/yolo11n-baseline/weights/best.pt --manifest data/pose/real-v1/manifest.json --split test --device 0 --output research/qa/pose-real-n.json
```

Usar la ruta real impresa por el entrenamiento: los nombres se incrementan si
ya existe una ejecución. El evaluador devuelve precisión/recall de cajas con
IoU≥.5, error de esquina visible en píxeles y relativo a la diagonal, conteos
y latencia de `predict` con dos calentamientos. Asociación greedy uno-a-uno,
sin minimizar artificialmente error mediante rotaciones de índices. Si no
hay coincidencias el error es `null`, no cero. p95 con pocas fotos no es fiable.

## Visibilidad y promoción del modelo

En el código instalado (`ultralytics/utils/loss.py`, `v8PoseLoss`), la máscara
es `gt_kpt[...,2] != 0`: **v=1 (oculto) y v=2 (visible) cuentan como presentes**.
La confianza de salida NO es un clasificador observado/oculto. El generador
conserva ambos estados para evaluación, pero la pérdida estándar no los separa.
Hace falta evaluar una salida de visibilidad específica o combinar la geometría
predicha con evidencia de bordes/segmentación antes de autorizar OCR.

Promover solamente tras medir escenas reales reservadas: esquinas/orientación,
cartas desconocidas, dos copias iguales, cartas superpuestas, brillos, errores
de recorte de serial y p50/p95. Comparar contra la OBB y el refinamiento actual.
Después evaluar PCA, segmentación y atención adicional como experimentos
separados. Entrenamiento de nuevos embeddings y de dígitos continúa pospuesto.

Referencias oficiales: [arquitectura YOLO11-pose](https://github.com/ultralytics/ultralytics/blob/main/ultralytics/cfg/models/11/yolo11-pose.yaml),
[anotaciones](https://docs.ultralytics.com/datasets/pose/),
[PyTorch](https://pytorch.org/get-started/locally/).
