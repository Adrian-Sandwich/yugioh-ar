> **Histórico.** Describe el estado de septiembre de 2026 y fue sustituido por [ARRANQUE_GPU](../docs/ARRANQUE_GPU.md); el piloto quedó como el alcance `pilot`. Índice de documentos: [docs/INDEX.md](../docs/INDEX.md).

# Piloto operativo: catálogo, revisión, reconocimiento y AR

Implementado el 25 de septiembre de 2026. No se entrenaron nuevos pesos. El ajuste intensivo permanece reservado para la otra computadora.

## Abrir las herramientas

- Galería y selección del piloto: <http://127.0.0.1:8768>.
- Etiquetar fotografías reales: <http://127.0.0.1:8768/capture>.
- Reconocimiento y sprite sobre una captura guardada: <http://127.0.0.1:8767>. La pantalla identifica explícitamente que no es vídeo en vivo.
- Cámara del teléfono: <http://127.0.0.1:8765>, cuando se arranque el visor con el teléfono accesible en `http://192.168.1.18:8080`.

Al cerrar esta entrega, los tres servicios quedaron iniciados. El teléfono no respondió a dos intentos de conexión de 10 segundos, incluido uno fuera del entorno restringido; por eso la comprobación visual usó la captura guardada. No se afirma validación en vivo.

Arranque cómodo en PowerShell: `./start_lab.ps1`; añadir `-Live` para iniciar también la cámara. Las ventanas de servicio quedan ocultas y sus logs en `.runtime/`. Si un puerto está ocupado, el script lo comunica y conserva la instancia existente; no sustituye ni termina procesos ajenos. El arranque no descarga dependencias ni entrena.

## Catálogo y revisión

`data/catalog/catalog.sqlite`: **14 616 identidades y 40 187 referencias**. Incluye **20 988 referencias enlazadas por ID y nombre**, **14 810 propuestas** y **4 389 sin resolver**. Son referencias de cartas/sprites/campos, no todos ejemplos de entrenamiento.

Nombres disponibles en YGOJSON: inglés 14 616; español 13 777; alemán 13 858; francés 13 874; portugués 12 162. Estas cifras indican cobertura textual, no reconocimiento visual multilingüe.

El cruce mantiene identidad UUID, ID de la fuente, arte, idioma y acabado separados. Un ID concordante no reemplaza una revisión visual. Los nombres de archivo de CardsOricaBR generan propuestas y no ingresan al piloto automáticamente; Rush Duel no se enlaza al TCG solamente por nombre. Se conservaron duplicados y originales.

En la galería se puede buscar en los cinco idiomas, abrir artes, aprobar/corregir identidad, registrar idioma/arte/acabado, descartar una referencia y deshacer una revisión. Las decisiones persisten en **`data/catalog/reviews.sqlite`**, separadas del catálogo regenerable. Respaldar este archivo junto con las anotaciones.

El piloto automático contiene **50 identidades y 63 referencias** de artes diferentes cuando están disponibles. Se pueden cambiar desde la galería. Después de cambiarlo, reconstruir los vectores con `vision_onnx.py` y reiniciar el visor. El método vectorial comprueba versiones del modelo y del piloto al arrancar y rechaza un índice desactualizado. SIFT necesita reiniciarse para cargar la selección nueva.

## Datos reales

La página de capturas recibe JPEG/PNG del usuario y permite marcar cuatro esquinas, identidad o desconocido, idioma, arte/acabado, condición, copia física, sesión y partición. Conserva el original y su hash en `data/pilot/captures/`, con anotaciones en `annotations.jsonl`.

Se impide guardar la misma imagen o una misma sesión en particiones diferentes. No se generan etiquetas ficticias para idiomas o rarezas. Las fotos nuevas siguen pendientes: solo disponemos de las capturas anteriores de Blue-Eyes y escenas sintéticas de prueba.

## Reconocedores

- **SIFT piloto:** admite varios artes y hasta tres instancias por referencia, verifica homografía y evita duplicar detecciones coincidentes. Busca únicamente en las referencias del piloto.
- **DRAW2 Small:** detector OBB y clasificador de 13 659 etiquetas. Mapea a YGOJSON cuando el enlace es inequívoco. Su alcance es más amplio que el piloto.
- **Embeddings:** expone el token CLS normalizado de 768 dimensiones antes del clasificador del ONNX Small, normaliza L2 y realiza búsqueda exacta por coseno contra las 63 referencias. Agrega resultados por identidad y aplica separación entre candidatos. Son features de un clasificador, todavía no afinadas con aprendizaje contrastivo.

Los dos métodos ONNX prueban la orientación de 0/180 grados después del rectángulo orientado. Sus umbrales de aceptación son experimentales, no probabilidades calibradas. El detector produce rectángulos orientados, no necesariamente las esquinas físicas exactas con perspectiva. Mantener el refinamiento geométrico del plan como trabajo siguiente.

El seguimiento requiere dos observaciones consecutivas para mostrar el sprite, distingue instancias de igual identidad por posición y reinicia confirmación al perderlas. Las asociaciones ambiguas se reinician. No garantiza conservar la identidad de una copia física tras cruces u oclusiones.

Los sprites se proyectan sobre el plano de la carta, manteniendo proporciones dentro del recorte. Se prefiere el sprite del mismo ID de origen cuando está disponible. Es AR 2D, sin modelo 3D ni oclusión física. Guardar fotograma conserva la imagen original sin superposición.

## Resultado de las pruebas

[Tabla detallada](pilot-evaluation/RESULTADOS.md) y [salida completa con candidatos](pilot-evaluation/results.json).

- Dos capturas reales de Blue-Eyes: los tres métodos reconocieron la identidad.
- Escenas sintéticas con dos copias de Blue-Eyes y otra carta: 3/3 instancias, también con giro y sombra simulada, en los tres métodos.
- Imagen vacía: ninguna aceptación.
- Una carta sintética excluida del piloto: SIFT/embeddings la rechazaron; DRAW2 la identificó mediante su catálogo completo.
- CPU en esta ejecución: SIFT ~4.1–4.9 s por captura real; DRAW2 ~0.8–1.8 s; embeddings ~1.1–3.1 s. Hubo otros procesos de evaluación activos: son tiempos observados, no un benchmark aislado ni latencia de cámara.

Las escenas sintéticas reutilizan las referencias y solo verifican funcionamiento. No demuestran precisión general, robustez multilingüe, sombras reales o rarezas. No se cumplen todavía las metas de 5 reconocimientos/s y 25 FPS con reconocimiento desacoplado; el visor actual sigue esperando el análisis.

Pruebas de catálogo/revisión, escritura protegida, separación de sesiones, geometría, seguimiento y proyección: `qa_workspace.py`. Regresión del reconocedor original y HTTP con cámara simulada: `check_recognition.py`. Prueba de navegador con Edge: `qa_browser.py`, pasó búsqueda en portugués, variantes, diálogo, captura y AR sin errores JavaScript. Capturas en `research/qa/`.

## Reproducir y trasladar a otra computadora

Copiar código, `web/`, `data/`, `downloads/` y `research/` conservando sus rutas. Los repos de referencia y licencias deben acompañar cualquier trabajo derivado; el inventario anterior contiene sus commits. No copiar `.venv` ni `.venv-eval`.

En destino, con Python compatible con las dependencias fijadas (aquí Python 3.14, Windows x64):

```powershell
python -m venv .venv-eval
.\.venv-eval\Scripts\python.exe -m pip install -r requirements-research.txt
# Solo si se desea regenerar el catálogo; detener antes los servicios que lo usan.
.\.venv-eval\Scripts\python.exe build_catalog.py
.\.venv-eval\Scripts\python.exe vision_onnx.py
.\.venv-eval\Scripts\python.exe qa_workspace.py
.\.venv-eval\Scripts\python.exe evaluate_pilot.py
.\start_lab.ps1
```

Para ejecutar manualmente cada interfaz:

```powershell
.\.venv-eval\Scripts\python.exe catalog_server.py
.\.venv-eval\Scripts\python.exe camera_viewer.py --backend embedding --ar --port 8767 --image data/captures/carta-2026-09-25T04-13-54-278Z.jpg
# Teléfono conectado; usar en otra terminal:
.\.venv-eval\Scripts\python.exe camera_viewer.py --backend embedding --ar
# Alternativas:
.\.venv-eval\Scripts\python.exe camera_viewer.py --backend draw2 --ar
.\.venv\Scripts\python.exe camera_viewer.py --pilot --ar
```

Elegir una sola instancia por puerto. `requirements-research.txt` incluye las herramientas ONNX y de QA; `requirements.txt` conserva el entorno ligero original.

Siguiente trabajo dependiente de datos/hardware: recoger las sesiones reales del piloto en los cinco idiomas, revisar artes/acabados, calibrar rechazo con desconocidos y mejorar captura/seguimiento desacoplados. Después, medir el beneficio del ajuste contrastivo y la optimización en la otra computadora según el [plan completo](PLAN_VECTORES_E_INVARIANCIA.md).
