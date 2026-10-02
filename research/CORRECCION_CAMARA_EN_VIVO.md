> **Histórico.** Describe el estado de septiembre de 2026 y fue sustituido por [TIEMPO_REAL](TIEMPO_REAL.md). Índice de documentos: [docs/INDEX.md](../docs/INDEX.md).

# Corrección de cámara en vivo — 25/09/2026

El visor anterior pedía un fotograma mediante `/analyze` y esperaba al análisis completo antes de actualizar la pantalla. Si el reconocimiento tardaba, devolvía 503 por concurrencia o fallaba, la pantalla conservaba la última imagen.

La captura ahora tiene su propio ciclo `/snapshot`, independiente del reconocimiento. El navegador envía el JPEG más reciente a `POST /analyze`; mantiene un único análisis en vuelo por pestaña y reintenta tras errores. El botón Pausar detiene las actualizaciones de pantalla y se descartan resultados de una generación anterior al pausar/cambiar reconocimiento.

Los sprites se devuelven en una capa PNG transparente, sin reemplazar la cámara por la imagen que se analizó. Las marcas caducan a los 2.5 segundos desde la captura analizada; pueden llevar retraso al mover la carta, pues no hay seguimiento óptico entre análisis. No se promete vídeo a 30 FPS.

## Corrección de resultados que llegaban tarde

El límite de 2.5 segundos hacía que un resultado de 3.8 segundos caducara antes de aparecer sobre el vídeo. Eso podía dar la impresión de menor reconocimiento aunque el modelo devolviera las identidades correctas. No se habían cambiado pesos, resolución de entrada ni umbrales.

El visor ahora muestra al lado el **último fotograma analizado**, con sus nombres y sprites sobre la imagen exacta de la inferencia. Conserva ese resultado y muestra su antigüedad incluso cuando es demasiado viejo para dibujarlo sobre la cámara en vivo. Esta segunda vista es una fotografía etiquetada, no vídeo. La cámara continúa actualizándose por separado.

`qa_live_camera.py` incluye una regresión específica: un análisis de tres segundos debe permanecer visible en el panel de resultados aunque ya haya caducado para el vídeo en vivo.

El servidor libera el bloqueo de inferencia antes de escribir la respuesta al cliente. Una espera acotada de dos segundos permite que varias pestañas compitan sin fallar inmediatamente. Se omiten los logs rutinarios de 503, se gestionan desconexiones de Windows y se guarda diagnóstico de hilos si una inferencia supera 20 segundos.

Validación:

- `qa_live_camera.py`: ocho fotogramas recibidos mientras el primer análisis simulado seguía ocupado; recuperación de un fallo de reconocimiento, pausa/reanudación y desconexión/reconexión de cámara; transparencia AR incluso para píxeles negros.
- `qa_camera_live_probe.py`: navegador conectado al teléfono real, imágenes cambiantes y al menos dos análisis completados sin errores JavaScript. El resultado medido está en `research/qa/camera-live-probe.json`; captura en `research/qa/camera-live.png`.

Servicio real: http://127.0.0.1:8765. Tras la actualización, recargar con **Ctrl+F5**. El servicio 8767 es una demostración con fotografía guardada y así se identifica en pantalla.
