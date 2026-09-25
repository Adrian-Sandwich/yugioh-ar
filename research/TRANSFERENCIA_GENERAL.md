# Continuar en la otra PC — estado consolidado

25/09/2026. Entrada principal para retomar el proyecto. Distingue lo probado
de lo pendiente; no sustituir el detector del visor por los pesos de prueba.

Ver también [EVIDENCIA_TEMPORAL.md](EVIDENCIA_TEMPORAL.md): selección reciente de capturas, asociación conservadora, consenso, fusión de evidencias y OCR de set code ya implementados. Las filas pendientes de seguimiento y selección se refieren a flujo óptico, evaluación real y optimización del reconocedor completo.

## Mejoras cerradas en esta sesión

| Área | Resultado | Evidencia |
|---|---|---|
| Geometría | Bordes antes del encoder y los recortes; abstención cuando no hay ajuste | `GEOMETRIA_CARTAS.md`, `qa_card_geometry.py` |
| Nombre/serial | OCR independiente de nombre y serial; ver `OCR_NOMBRE.md` | `qa_passcode_browser.py` |
| YOLO11 | n/s con cuatro esquinas, C2PSA nativo, ambos completaron prueba de entrenamiento | `yolo11_pose/README.md`, `runs/*/experiment.json` |
| Anotaciones | Herramienta de cuatro esquinas visibles, exportación JSON e importador con separación por sesión | `qa_pose_annotations.py` |
| SQL | Un recorrido de coincidencias; nombres/seriales por lote; modos exactos explícitos | `qa_registry_search.py` y `qa/registry-search-optimized.json` |
| Captura | Peticiones simultáneas al mismo origen comparten JPEG durante 150 ms; fecha original preservada | `qa_shared_snapshot.py`, `qa_live_camera.py` |
| Referencias | Mapa por ID para evitar recorrer todo el piloto por cada resultado | `vision_onnx.LiveRecognizer` |
| Descarga | Reanudada tras apagado; ficha portuguesa CID 15519 recuperada | `download_status.py` |
| Bases | Backups SQLite coherentes del registro, catálogo y revisiones con `quick_check` | `../transfer/20260925-194603/manifest.json` |
| Geometría (tarde) | Ajuste por bordes de croma para cajas no resueltas: 5/9 candidatas en la escena real, sin cambios en las anteriores | `GEOMETRIA_CARTAS.md`, `qa_card_geometry.py` |
| Visor y AR (tarde) | Capa AR compuesta en el navegador; sprites ausentes y nombres fuera del piloto cacheados; JS del panel OCR dividido | `PIPELINE_ESTADO.md` |
| Diagnóstico (tarde) | Stall log del 11:08 explicado: forward ONNX > 20 s bajo carga de CPU, no interbloqueo | `PIPELINE_ESTADO.md` |
| Repositorio | Git inicializado en la raíz con `.gitignore` para datos, descargas, entornos y salidas pesadas | `.gitignore` |
| Arte YGOPRODeck (tarde) | Arte recortado autoalojado para las ilustraciones del registro; verificación SIFT de candidatas como evidencia `art`; 10/10 verificadas, 0 erróneas en la escena real | `ARTE_YGOPRODECK.md`, `qa/art-verification/` |

SQL: 27 comparaciones conservan resultados, orden de cartas y prioridad de
nombres. Pasa de hasta 62 consultas a 3 lecturas + SAVEPOINT/RELEASE. En cinco
muestras con servicios activos, búsqueda general ~247–313 ms → ~118–152 ms;
serial y set en modo exacto ~0.12/0.20 ms. Son mediciones bajo carga, no una
comparación de lenguajes. El modo «Todo» conserva `LIKE` y sus comodines; elegir
«Serial exacto» impide confundir un ID de arte con el passcode. No se cambió
esquema ni se añadieron índices al registro que Neuron está escribiendo.

## Qué copiar y cómo arrancar

Copiar el proyecto manteniendo rutas relativas: código raíz, `web`, `research`,
`data`, `downloads` (incluido `downloads/ygoprodeck-art`, ~1.4 GB, o reanudar su
descarga en destino), `repos` y los archivos `requirements*.txt`. No copiar los
entornos `.venv*`, temporales ni procesos de `.runtime` como si fueran portables.

La carpeta `transfer/20260925-194603` contiene **las bases y un manifiesto**, no
todo el proyecto ni todos los modelos. Sus tres backups son consistentes por
base; no son una transacción conjunta con la caché de páginas que sigue creciendo.
Antes de arrancar servicios en destino, colocar sus tres archivos SQLite en
las rutas indicadas por el manifiesto. No restaurarlos encima del origen activo.
No copiar sólo un `.sqlite` vivo ignorando su WAL.

Si la descarga ha avanzado mucho, crear un respaldo más reciente:

```powershell
.\.venv-eval\Scripts\python.exe research/prepare_transfer.py
```

Cada ejecución crea una carpeta nueva. Comprobar hashes antes de restaurar.
Los hashes de código reflejan el instante de creación del manifiesto. Desde el
25/09/2026 (tarde) la raíz es un repositorio Git: el código, `web`, `research`
(sin pesos de entrenamiento ni benchmark de reflejos) y los `requirements*.txt`
se trasladan clonando o copiando `.git`; `data`, `downloads`, `repos`, `transfer`
y los entornos siguen fuera de Git y se copian aparte.

Recrear `.venv-eval` con `requirements-research.txt` y `requirements-ocr.txt`;
`.venv-pose` con el lock de pose y PyTorch compatible con el destino. Mantener
reflejos en `.venv-glare`, según su guía. Los modelos y Python ya copiados no
prueban disponibilidad de GPU.

```powershell
.\.venv-eval\Scripts\python.exe research/doctor.py --output research/qa/destino-visores.json
.\.venv-pose\Scripts\python.exe research/doctor.py --torch --output research/qa/destino-pose.json
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_lab.ps1 -Live
```

La excepción de política del ejemplo se limita al proceso; no cambia Windows
permanentemente. `start_lab.ps1` no reemplaza servicios ya existentes: comprobar
procesos antes de reiniciar una versión. URLs:

- Cámara: http://127.0.0.1:8765 (IP del teléfono actualmente `192.168.1.18:8080`).
- Foto de prueba: http://127.0.0.1:8767.
- Anotador: http://127.0.0.1:8767/pose-annotator.
- Catálogo: http://127.0.0.1:8768; registro: http://127.0.0.1:8769.

Cambiar la IP del teléfono si la red es diferente. Un 502 de `/snapshot` indica
fallo de adquisición, no prueba de un bloqueo de ONNX. Recargar todas las
pestañas con Ctrl+F5 después de actualizar JavaScript.

## Descarga y recuperación

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 research/download_status.py
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\start_registry_crawl.ps1
```

El contador `completed` es por ejecución. El estado acumulado cuenta fichas
guardadas sobre las **67,552 descubiertas**, no sobre las tareas pendientes de
un arranque. Son combinaciones carta/idioma, no 67,552 identidades distintas.
`running` en un JSON no demuestra un proceso vivo: comprobar fecha y PID.
El iniciador reutiliza caché y evita un segundo proceso si su PID sigue activo.
Si existe `data/registry/neuron/STOP`, respetarlo y revisar antes de reanudar.
El reintento CID 15519/PT se recuperó al volver a entrar en la cola pendiente.

## Pendientes que requieren datos, otra PC o acceso externo

| Prioridad | Trabajo | Criterio para considerarlo terminado |
|---|---|---|
| P0 | Capturas reales en sesiones separadas: ángulos, distancias, fondos, idiomas, fundas, brillos y negativos | Todas las instancias anotadas; train/val/test sin fuga de sesión |
| P0 | Entrenar y comparar YOLO11n/s con datos reales | Error de esquina, orientación, falsas detecciones, recortes válidos y latencia medidos |
| P0 | Anotar oclusiones y visibilidad; comparar pose/segmentación | Distinguir esquina observada de inferida; no usar confianza estándar como visibilidad |
| P1 | PCA y atención adicional | Ablación con mismos datos/configuración frente a C2PSA nativo; conservar sólo mejora medida |
| P1 | Seguimiento óptico y movimiento de cámara | Clips con cruces, sustitución en el mismo sitio, dos copias iguales; sin transferir identidad/votos |
| P1 | Elegir mejores capturas y evitar identificaciones redundantes | Menos inferencias manteniendo detección de cartas nuevas y cambios de identidad |
| P1 | Validar nombres y set code fisicos y selección de ROI por texto | Datos legibles en EN/ES/DE/FR/PT; evidencia separada de la identidad visual |
| P1 | Aislar ONNX en proceso recuperable | Prueba de bloqueo real, reinicio controlado y memoria/latencia medidos; el watchdog actual sólo registra stacks |
| P2 | FTS5/trigramas y revisión de cachés | Primero copia de SQLite, misma semántica de acentos/subcadenas y frescura durante escritura |
| P2 | Restauración de reflejos en GPU | Mejorar identidad/OCR, no sólo apariencia; seguir `glare-benchmark/TRANSFERENCIA.md` |
| P2 | UnReflectAnything | Acceso autorizado al encoder DINO faltante; todavía sin resultados locales |
| P2 | AR con warp limitado a ROI, batching y exportación ONNX de pose | Igualdad visual o tolerancia documentada y mejora p50/p95 real |
| P3 | Nuevos vectores, lector especializado de dígitos, Go/Julia y AR 3D | Etapas futuras; no iniciadas por preparar YOLO11 |

El refinamiento actual sólo resolvió 4/9 candidatas de una captura. Sus filtros
pueden rechazar perspectivas fuertes. No presentamos eso como geometría resuelta.
El anotador inicial sólo admite cuatro esquinas visibles; las escenas parciales
deben esperar el flujo de oclusiones. Los modelos de una época tienen precisión
muy baja y no están desplegados.

## Pruebas y mediciones en destino

```powershell
.\.venv-eval\Scripts\python.exe qa_card_geometry.py
.\.venv-eval\Scripts\python.exe qa_pipeline_core.py
.\.venv-eval\Scripts\python.exe qa_shared_snapshot.py
.\.venv-eval\Scripts\python.exe qa_live_camera.py
.\.venv-eval\Scripts\python.exe qa_shared_camera.py
.\.venv-eval\Scripts\python.exe qa_passcode_browser.py
.\.venv-eval\Scripts\python.exe qa_registry_search.py
.\.venv-eval\Scripts\python.exe qa_registry_browser.py
.\.venv-eval\Scripts\python.exe qa_pose_annotations.py
```

Las pruebas de navegador esperan Edge; las del registro/anotador requieren sus
servicios. Registrar CPU/GPU/VRAM/RAM, SO, versiones, hilos, resolución y carga.
Calentar modelos y medir p50/p95 por etapa con las mismas capturas. Separar
latencia de inferencia de edad real de imagen y de extremo a extremo.

Plan completo: [PLAN_MEJORA_INTEGRAL.md](PLAN_MEJORA_INTEGRAL.md). Arquitectura y
fallos conocidos: [PIPELINE_ESTADO.md](PIPELINE_ESTADO.md). Experimento de esquinas:
[yolo11_pose/README.md](yolo11_pose/README.md). La integración nativa de Codebase
Memory sigue cerrada; su CLI y las advertencias de frescura están documentadas
en [CODEBASE_MEMORY.md](CODEBASE_MEMORY.md).
