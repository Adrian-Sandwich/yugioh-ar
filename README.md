# Yu-Gi-Oh! AR — investigación inicial

Objetivo: reconocer cartas físicas con una cámara conectada a una PC y mostrar monstruos sobre el vídeo.

**Continuar aquí:** [estado consolidado, mejoras verificadas y traslado a la otra PC](research/TRANSFERENCIA_GENERAL.md).
La raíz es un repositorio Git desde el 25/09/2026; `data/`, `downloads/`, `repos/`, `transfer/` y los entornos quedan fuera y se copian aparte.
[Experimento YOLO11 de cuatro esquinas](research/yolo11_pose/README.md) ·
[anotador local](http://127.0.0.1:8767/pose-annotator).

**Piloto operativo:** catálogo unificado, galería de revisión, etiquetado de capturas, 50 cartas, comparación SIFT/DRAW2/embeddings y sprites AR. [Guía de uso, resultados y traslado a otra computadora](research/ENTREGA_PILOTO.md). Arrancar con `./start_lab.ps1`; galería en http://127.0.0.1:8768 y prueba con captura guardada en http://127.0.0.1:8767. Los métodos ONNX todavía tienen umbrales experimentales.

- [Evaluación de los cuatro repositorios y componentes concretos](research/REPOSITORIOS.md)
- [Plan de acción y criterios de aceptación](research/PLAN_DE_ACCION.md)
- [Plan vigente: cámara variable, geometría, seguimiento y consultas eficientes](research/PLAN_MEJORA_INTEGRAL.md)
- [Estado actual del pipeline, correcciones y pruebas](research/PIPELINE_ESTADO.md)
- [Reflejos: resultados, imágenes comparativas y modelos descargados](research/glare-benchmark/README.md)
- [Traslado de los experimentos y mediciones en la próxima PC](research/glare-benchmark/TRANSFERENCIA.md)
- [Auditoría de cobertura por idioma y lista de revisión del piloto](research/registry-coverage/README.md)
- [Inventario reproducible: orígenes, commits y tipo de descarga](research/repositories.json)
- [Registro multilingüe: nombres, passcodes, códigos de set y scraping de Neuron](research/REGISTRO_MULTILINGUE.md). Buscador: http://127.0.0.1:8769; SQLite y CSV en `data/registry/`.
- [Estructura de la carta y zonas para reconocimiento](research/card-anatomy/ESTRUCTURA.md)
- [Zoom al passcode: rectificación, OCR local y consulta del registro](research/OCR_PASSCODE.md)
- [Arte recortado de YGOPRODeck y verificación geométrica de candidatas](research/ARTE_YGOPRODECK.md)
- [Muestra acotada de escaneos de TCGplayer y lectura con los OCR locales](research/TCGPLAYER_MUESTRA.md)
- [Cola de experimentos diseñados para la otra PC](research/COLA_EXPERIMENTOS.md)
- [Nuevas referencias: DRAW2, DRAW, one-shot learning y Roboflow](research/references-20260924/REVISION.md)
- [Plan para otra computadora: vectores, rotaciones, sombras y entrenamiento](research/PLAN_VECTORES_E_INVARIANCIA.md)
- [Fuentes de imágenes CardsOricaBR y metadatos históricos YCCLP](research/references-20260924/FUENTES_IMAGENES_ADICIONALES.md)
- [Recursos locales de The Dawn of a New Era: catálogo, idiomas y sprites](research/tdoane/REVISION.md)

Colección pública CardsOricaBR: originales e inventario en `downloads/cardsoricabr/`. Descargar o reanudar con `.\.venv\Scripts\python.exe research/download_cardsoricabr.py`; validar hashes y decodificación de imágenes con `.\.venv\Scripts\python.exe research/audit_cardsoricabr.py`. El manifiesto conserva nombres y carpetas de origen; los nombres locales incluyen el ID Drive para evitar colisiones. Consultar `download_complete` y `audit.json` para confirmar integridad. El número de archivos no representa identidades únicas y los sufijos de nombre no identifican por sí solos arte o rareza.

Código de referencia en `repos/tcg-ar`, `repos/augmented-reality-card-game`, `repos/opencv-identifier-source` y `repos/hololens-source`. Los dos últimos tienen checkout selectivo del código; sus assets grandes están pendientes. Las otras dos carpetas dentro de `repos/` son descargas interrumpidas, documentadas en la evaluación.

## Visor de cámara Android

Ejecutar `python camera_viewer.py` y abrir http://127.0.0.1:8765 en esta PC. Usa IP Webcam en http://192.168.1.18:8080 por defecto; para cambiarla: `python camera_viewer.py --camera http://IP:8080`.

Solo requiere Python, sin instalar paquetes. Muestra fotogramas JPEG hasta 5 veces por segundo, permite pausar y guardar la imagen mostrada en las descargas del navegador. Si falla la conexión, reintenta. Mantener IP Webcam iniciado y ambos dispositivos en la misma red. Detener el servidor con Ctrl+C.

Comprobación sin interfaz: `python camera_viewer.py --check`. El estado actual y las pruebas de navegador se documentan en [PIPELINE_ESTADO.md](research/PIPELINE_ESTADO.md). El vídeo y el análisis tienen bucles independientes; los tiempos de descarga de JPEG no son latencia total cámara-pantalla.

## Primer reconocimiento (bitácora histórica)

Esta sección describe la primera versión SIFT. Para operar el piloto actual con múltiples cartas, seguimiento y vídeo independiente, usar [ENTREGA_PILOTO.md](research/ENTREGA_PILOTO.md) y [PIPELINE_ESTADO.md](research/PIPELINE_ESTADO.md).

Instalar dependencias con `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` (crear antes el entorno con `python -m venv .venv` si no existe). Arrancar con `.\.venv\Scripts\python.exe camera_viewer.py --recognize` y abrir o recargar el visor. El modo de cámara sin reconocimiento sigue funcionando con Python sin dependencias.

Reconoce **una instancia de la ilustración de Blue-Eyes White Dragon de las capturas del usuario** mediante SIFT y homografía RANSAC; dibuja contorno y nombre. El catálogo y las esquinas de la referencia están en `data/references/catalog.json`. Los rasgos se extraen del arte de la carta para evitar aprender el fondo de la mesa. No es OCR ni reconocimiento universal de cartas. El número de coincidencias no es una probabilidad de acierto.

`Guardar fotograma` conserva el JPEG original, sin el contorno dibujado. La casilla `Reconocer carta` alterna entre análisis y vista de cámara. La visualización en modo reconocimiento espera al análisis; todavía no hay seguimiento entre fotogramas, múltiples copias iguales ni 3D.

Validación: `.\.venv\Scripts\python.exe check_recognition.py`. Dos capturas distintas de la referencia detectadas, imagen vacía y fondo con la carta enmascarada rechazados. Resultados y fotos anotadas en `research/recognition/`. También prueba el servidor HTTP con una cámara simulada usando una captura reservada. Es una comprobación pequeña, no una estimación de precisión general ni una prueba de vídeo en vivo. El primer ensayo tardó aproximadamente 0.7 s por captura positiva en esta PC. Falta medir el uso en vivo y probar otras cartas como negativos.

Siguiente paso: reconocimiento en vivo con el teléfono conectado, más referencias y seguimiento por instancia; Unity para visualización 3D después. No se ejecutaron los proyectos externos.
