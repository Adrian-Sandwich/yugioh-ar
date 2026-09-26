# Bitácora inicial (24 y 25 de septiembre de 2026)

Texto conservado del primer README del proyecto. Describe el visor de cámara
original y la primera versión de reconocimiento con SIFT. Para operar el
piloto actual con múltiples cartas, seguimiento y vídeo independiente, usar
[ENTREGA_PILOTO.md](../research/ENTREGA_PILOTO.md) y
[PIPELINE_ESTADO.md](../research/PIPELINE_ESTADO.md).

## Visor de cámara Android

Ejecutar `python camera_viewer.py` y abrir http://127.0.0.1:8765 en esta PC.
Usa IP Webcam en http://192.168.1.18:8080 por defecto; para cambiarla:
`python camera_viewer.py --camera http://IP:8080`.

Solo requiere Python, sin instalar paquetes. Muestra fotogramas JPEG hasta 5
veces por segundo, permite pausar y guardar la imagen mostrada en las descargas
del navegador. Si falla la conexión, reintenta. Mantener IP Webcam iniciado y
ambos dispositivos en la misma red. Detener el servidor con Ctrl+C.

Comprobación sin interfaz: `python camera_viewer.py --check`. El estado actual
y las pruebas de navegador se documentan en
[PIPELINE_ESTADO.md](../research/PIPELINE_ESTADO.md). El vídeo y el análisis
tienen bucles independientes; los tiempos de descarga de JPEG no son latencia
total cámara-pantalla.

## Primer reconocimiento

Instalar dependencias con `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`
(crear antes el entorno con `python -m venv .venv` si no existe). Arrancar con
`.\.venv\Scripts\python.exe camera_viewer.py --recognize` y abrir o recargar el
visor. El modo de cámara sin reconocimiento sigue funcionando con Python sin
dependencias.

Reconoce **una instancia de la ilustración de Blue-Eyes White Dragon de las
capturas del usuario** mediante SIFT y homografía RANSAC; dibuja contorno y
nombre. El catálogo y las esquinas de la referencia están en
`data/references/catalog.json`. Los rasgos se extraen del arte de la carta para
evitar aprender el fondo de la mesa. No es OCR ni reconocimiento universal de
cartas. El número de coincidencias no es una probabilidad de acierto.

`Guardar fotograma` conserva el JPEG original, sin el contorno dibujado. La
casilla `Reconocer carta` alterna entre análisis y vista de cámara. La
visualización en modo reconocimiento espera al análisis; todavía no hay
seguimiento entre fotogramas, múltiples copias iguales ni 3D.

Validación: `.\.venv\Scripts\python.exe check_recognition.py`. Dos capturas
distintas de la referencia detectadas, imagen vacía y fondo con la carta
enmascarada rechazados. Resultados y fotos anotadas en `research/recognition/`.
También prueba el servidor HTTP con una cámara simulada usando una captura
reservada. Es una comprobación pequeña, no una estimación de precisión general
ni una prueba de vídeo en vivo. El primer ensayo tardó aproximadamente 0.7 s
por captura positiva en esta PC. Falta medir el uso en vivo y probar otras
cartas como negativos.

## Colección CardsOricaBR y código de referencia

Colección pública CardsOricaBR: originales e inventario en
`downloads/cardsoricabr/`. Descargar o reanudar con
`.\.venv\Scripts\python.exe research/download_cardsoricabr.py`; validar hashes y
decodificación de imágenes con `.\.venv\Scripts\python.exe research/audit_cardsoricabr.py`.
El manifiesto conserva nombres y carpetas de origen; los nombres locales
incluyen el ID Drive para evitar colisiones. Consultar `download_complete` y
`audit.json` para confirmar integridad. El número de archivos no representa
identidades únicas y los sufijos de nombre no identifican por sí solos arte o
rareza.

Código de referencia en `repos/tcg-ar`, `repos/augmented-reality-card-game`,
`repos/opencv-identifier-source` y `repos/hololens-source`. Los dos últimos
tienen checkout selectivo del código; sus assets grandes están pendientes. Las
otras dos carpetas dentro de `repos/` son descargas interrumpidas, documentadas
en [la evaluación](../research/REPOSITORIOS.md).
