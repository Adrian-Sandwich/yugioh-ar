# Continuar en la otra computadora

Decisión del usuario, 25/09/2026: aprovechar la descarga de Neuron para reunir
material y preparar experimentos. Medir rendimiento de verdad en la otra PC.
Esta prueba local es exploratoria de calidad; sus tiempos bajo carga no sirven
para decidir qué hardware comprar ni para comparar CPU contra GPU.

## Estado y material

- Tres repositorios descargados: `repos/DocSHRNet`, `repos/SHDocs` y
  `repos/UnReflectAnything`. Commits exactos en `downloads.json`.
- Tres checkpoints completos en `downloads/glare-models/`, aproximadamente
  3.92 GB decimales en total. Hashes y tamaños en `downloads.json`; URLs y
  variantes en `sources.json`. UnReflectAnything además coincide con SHA-256
  LFS del publicador.
- DocSHRNet y MIMO-UNetPlus se cargaron con `weights_only=True` y verificación
  estricta de claves. No se entrenaron pesos.
- Original de la mesa: `table-original.jpg`, con hash en `samples.json`.
  Siete recortes nativos rectificados y una foto cercana de control en `inputs/`.
- `samples.json`: siete instancias, seis identidades; dos Ojos Anómalos separados.
  Las etiquetas de identidad combinan la descripción del usuario y revisión
  visual de `contact-sheet.png`. Los seriales de la mesa son expectativas
  consultadas en el registro, NO transcripciones legibles de esos píxeles.
- Salidas PNG, observaciones OCR y decisiones por variante en `outputs/`.
  `comparison.html` y `summary.json` resumen la comparación completada: las
  cuatro variantes aceptaron las mismas 4/7 cartas, sin seriales en la mesa;
  todas leyeron correctamente el serial en la foto cercana de control.
- Entorno de restauración separado: `.venv-glare`; versiones en `environment.txt`.
  Entorno del reconocedor/OCR: `.venv-eval`, definido por los requirements de
  la raíz y RapidOCR 3.9.2. No copiar entornos virtuales entre computadoras.

## Copia mínima para reproducir esta muestra

Conservar la estructura relativa respecto a la raíz del proyecto:

```text
research/glare-benchmark/                         # scripts, datos, resultados y documentos
research/ESTADO_DEL_ARTE_REFLEJOS.md
research/REFLEJOS_Y_CAPTURAS.md
repos/DocSHRNet/                                  # código y documentación originales
repos/SHDocs/
repos/UnReflectAnything/
downloads/glare-models/                           # checkpoints y configuración
vision_onnx.py
passcode_ocr.py
data/pilot/catalog.json
data/pilot/embeddings.json
data/pilot/embeddings.npy
data/models/vit_small_features.onnx
data/models/vit_small_features.json
downloads/reference-assets/draw2/onnx/            # detector, encoder base y etiquetas
research/references-20260924/draw2-small-ygojson-map.json
requirements-research.txt
requirements-ocr.txt
research/OCR_PASSCODE.md
research/qa/passcode/models.json
```

Para repetir solo restauración no hace falta el reconocedor, catálogo ni OCR.
Para evaluar la muestra congelada no hace falta copiar la SQLite que sigue
actualizándose: `samples.json` ya conserva las etiquetas necesarias. Tampoco
hace falta copiar las 17818 imágenes de CardsOricaBR para este experimento.

Para reconstruir entradas desde cero con `prepare.py`, copiar adicionalmente
`research/qa/passcode/real-rectified.png`. NO ejecutar `label_scene.py` sobre
una escena nueva: contiene asignaciones manuales específicas de esta captura.

Para trasladar el proyecto completo, conservar también bases, imágenes,
anotaciones y decisiones manuales según `research/ENTREGA_PILOTO.md`. No copiar
a ciegas una SQLite que está escribiendo el crawler; generar un respaldo mediante
la API de backup de SQLite o esperar un cierre ordenado. No detener Neuron solo
para preparar este experimento.

## Preparar el entorno nuevo

La PC actual usa Windows, Python 3.14 y PyTorch 2.14.0 CPU. En la otra PC crear
entornos nuevos. Instalar PyTorch apropiado para su GPU/controlador antes de las
dependencias; no instalar la edición CPU por copiar ciegamente nuestro entorno.
Guía oficial: https://pytorch.org/get-started/locally/

Para una réplica CPU en Windows con Python 3.14:

```powershell
python -m venv .venv-glare
.\.venv-glare\Scripts\python.exe -m pip install -r research/glare-benchmark/environment.txt
.\.venv-glare\Scripts\python.exe -m pip check
python -m venv .venv-eval
.\.venv-eval\Scripts\python.exe -m pip install -r requirements-research.txt -r requirements-ocr.txt
.\.venv-eval\Scripts\python.exe -m pip install --no-deps rapidocr==3.9.2
```

OpenCV headless proporciona `cv2`; no añadir OpenCV de escritorio encima para
satisfacer solamente el nombre de dependencia de RapidOCR. Ver detalles en
`research/OCR_PASSCODE.md`. Verificar los tres hashes de modelos OCR contra
`research/qa/passcode/models.json` si se quiere una reproducción exacta.

## Repetir la evaluación de calidad

Ejecutar desde la raíz. Antes de volver a ejecutar, guardar una copia de
`research/glare-benchmark/outputs/`, `summary.json` y `comparison.html`: los
scripts escriben en esos mismos destinos. Las entradas originales se conservan.

```powershell
.\.venv-glare\Scripts\python.exe research/glare-benchmark/audit_downloads.py
.\.venv-glare\Scripts\python.exe research/glare-benchmark/restore.py --model docshrnet
.\.venv-glare\Scripts\python.exe research/glare-benchmark/restore.py --model mimo-shdocs --padding reflect
.\.venv-eval\Scripts\python.exe -X utf8 research/glare-benchmark/evaluate.py --variant original
.\.venv-eval\Scripts\python.exe -X utf8 research/glare-benchmark/evaluate.py --variant clahe
.\.venv-eval\Scripts\python.exe -X utf8 research/glare-benchmark/evaluate.py --variant docshrnet
.\.venv-eval\Scripts\python.exe -X utf8 research/glare-benchmark/evaluate.py --variant mimo-shdocs
.\.venv-eval\Scripts\python.exe research/glare-benchmark/report.py
```

Abrir `research/glare-benchmark/comparison.html` en el navegador. Las imágenes
se enlazan localmente; no se envían a un servicio externo.

### Diferencias de implementación que hay que conservar o evaluar

- Entrada RGB [0,1], dimensión nativa, CPU de dos hilos en la prueba local.
- DocSHRNet conserva la arquitectura oficial y su padding interno.
- MIMO usa arquitectura y checkpoint SHDocs del primer estudio de generalización;
  NO el modelo GoPro del benchmark OCR inicial del artículo.
- Nuestro primer ensayo usa padding reflect mínimo a múltiplo de ocho. El
  script upstream añade padding negro y ocho píxeles incluso cuando ya es
  divisible. El wrapper permite `--padding upstream` para comparar esa variante.
  Los resultados actuales corresponden a `reflect`; no atribuirlos a una réplica
  exacta del script upstream. No se ejecutó la variante upstream aquí.
- La clasificación mantiene las orientaciones 0/180, similitud >=0.80 y margen
  >=0.07 del piloto de entonces. No se bajaron umbrales para mejorar el conteo.
  **Desde el 26/09/2026 la regla de producción es similitud ≥ 0.50 y margen
  ≥ 0.25** (`vision_onnx.ACCEPTANCE`, calibrada en
  [CALIBRACION_ESCANEOS.md](../CALIBRACION_ESCANEOS.md)) y el piloto tiene 88
  referencias en lugar de 63: repetir esta evaluación hoy da otro conteo de
  aceptaciones por esas dos razones, no por la restauración. Para comparar
  con los resultados guardados hay que fijar la regla antigua en el script.
- CLAHE se aplica a luminancia Lab (clip 2.0, grilla 8×8). El OCR mantiene sus
  variantes originales, incluida su propia normalización de contraste.
- Los recortes vienen de cajas orientadas; no son anotaciones de esquinas
  perfectas. Algunos incluyen fondo. Esto afecta reconocimiento y restauración.

## Medición de rendimiento en destino

Registrar CPU, GPU/VRAM, RAM, SO, Python, PyTorch, CUDA/controlador, resolución,
precisión numérica, batch size e hilos. Evitar otras tareas pesadas y usar las
mismas entradas. Separar carga de pesos, transferencia, inferencia, OCR y
latencia extremo a extremo.

El wrapper quedó preparado con `--device`, `--threads`, `--warmup` y `--repeats`:

```powershell
.\.venv-glare\Scripts\python.exe research/glare-benchmark/restore.py --model docshrnet --device cuda --warmup 2 --repeats 10
.\.venv-glare\Scripts\python.exe research/glare-benchmark/restore.py --model mimo-shdocs --device cuda --warmup 2 --repeats 10 --padding reflect
```

CUDA se sincroniza antes/después del forward; se guardan todos los tiempos
en `all_ms` y su mediana en `ms`. Excluye transferencia de entrada, conversión
de salida y guardado PNG. Falla explícitamente si se pide CUDA y no está
disponible. Este camino GPU NO fue ejecutado en esta PC. La primera ejecución
local precede esta ampliación del wrapper: sus tiempos incluyen forward y
conversión de salida, sin warmup ni repeticiones. No mezclarlos con la futura
serie controlada. Para p95 usar suficientes observaciones y reportar por tamaño,
no mezclar la foto cercana 630×920 con los recortes menores.

## UnReflectAnything: qué falta

Se descargó `full_model_weights.pt` completo (3,441,741,454 bytes), configuración
y código versión 1.1.1. La advertencia del README sobre v1.0.2 está desactualizada
respecto al factory actual. El checkpoint incluye configuración DotMap y requiere
carga compatible; no se ejecutó un `torch.load(weights_only=False)` indiscriminado.

El encoder original `facebook/dinov3-vitl16-pretrain-lvd1689m` devolvió HTTP 401
sin autenticación. Hace falta acceso autorizado al repositorio upstream y su
configuración. No se usó la sustitución por mirror del paquete para sortear esa
restricción. No hay resultados de UnReflectAnything en esta comparación.

En destino, usar la configuración embebida del checkpoint y verificar carga
estricta de todos los pesos; revisar que la resolución, capas seleccionadas y
parámetros del reparador de tokens coincidan. Registrar licencias MIT/DINO y
probar primero una imagen, con memoria y tiempo medidos, antes de procesar vídeos.

## Siguiente trabajo útil mientras termina Neuron

Conservar capturas pareadas con luz lateral/difusa, etiquetas por instancia,
funda/rareza/arte/idioma y varias sesiones. La muestra actual no tiene imagen
limpia pareada ni negativos suficientes y no estima precisión general.
Separar fallo de contorno, orientación, arte, identificación y lectura del serial.
No entrenar ni ampliar vectores automáticamente: ambos siguen pendientes futuros.
