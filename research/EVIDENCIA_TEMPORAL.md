# Selección de capturas, seguimiento y set code

Implementado el 25/09/2026 en `card_evidence.py`, `set_ocr.py` y el trabajador
`passcode_ocr.py`. El visor muestra una evaluación conjunta; no cambia las
identidades ni los overlays del reconocedor visual automáticamente.

## Comportamiento

- Asociación entre lotes por posición, escala, apariencia rectificada e identidad
  visual compatible. Correspondencia única en ambos sentidos: dos candidatas que
  compiten por la misma anterior empiezan sin votos heredados. Ausencia, cambio
  de identidad, movimiento grande, geometría incierta o intervalo superior a
  tres segundos reinician el seguimiento.
- Calidad: nitidez, resolución nativa y proporción de píxeles muy claros poco
  saturados. Esta última es sólo una aproximación a reflejos; también puede
  penalizar dibujos blancos. La geometría sigue siendo un requisito previo.
- Reutiliza evidencia textual resuelta de una captura de menos de 1.5 segundos
  si la carta tiene píxeles idénticos o la nueva puntuación cae más del 10 %.
  Conserva los recortes originales y su fecha, muestra que son reutilizados y
  no suma votos. Si no hay evidencia textual resuelta, vuelve a intentar OCR.
  No hay espera para acumular un vídeo: mantiene una tarea activa y una pendiente.
- Consenso por identidad: dos capturas diferentes con evidencia textual
  compatible. Se comprueban hash de la carta rectificada y fecha, de modo que
  cambiar sólo el fondo no cuenta como leer la carta otra vez. Una discrepancia
  vacía los votos. Repetición no es una garantía estadística de exactitud.
- Fusión: intersección de identidades propuestas por imagen, nombre, serial y
  set. Las sugerencias aproximadas no votan. Fuentes discordantes producen
  conflicto; varias fuentes compatibles producen corroboración. Sólo imagen no
  adquiere confirmación textual por repetirse. La fusión queda visible como
  evidencia, sin sobrescribir la identificación visual.
- OCR del set: tres franjas candidatas, dos orientaciones, hasta seis lecturas;
  códigos literales con guion y ceros preservados, confianza mínima 0.85,
  consulta exacta al índice `printings.set_code`. No corrige O/0 ni elige una
  rareza/edición cuando varias comparten código. Formatos fuera del parser y
  layouts sin cobertura quedan sin lectura; no afirmamos cobertura universal.
- Nombre: si un texto tiene confianza alta pero no coincide con ningún nombre
  del registro, también se intenta el recorte alternativo con contraste.

## Validación

`qa_card_evidence.py`: cambios de carta, conflictos, duplicados, competencia entre
copias, orden de detecciones, desapariciones, caducidad, timestamps duplicados,
fondo cambiante, selección por calidad y múltiples impresiones del mismo set.
`qa_pipeline_core.py` y `qa_passcode.py`: cola, aislamiento de errores, umbrales,
serial y geometría. `qa_name_ocr.py`: idiomas renderizados y fotografía real.
`qa_passcode_browser.py`: fotografía real con nombre BLUE-EYES WHITE DRAGON,
serial 89631139, set LED3-EN006 y cuatro fuentes concordantes; vídeo sigue
avanzando y la fotografía fija permanece en una sola captura concordante.
Lecturas del set guardadas en `qa/name-ocr/set-real.json`.

La prueba de navegador utiliza las esquinas conocidas de la referencia. En el
servicio demo con detección automática, la prueba posterior sólo corroboró
nombre e imagen: serial y set quedaron sin lectura. No extrapolar el resultado
de geometría conocida al detector. Informe: `qa/evidence-deployed.json`.
Una ejecución caliente del trabajador completo midió 513 ms con tres candidatas,
de las cuales sólo una tenía geometría utilizable. Es una muestra, no p50/p95.
El teléfono respondió con HTTP 502 a través del visor en esta comprobación:
no hubo validación de cámara en vivo durante esta sesión.

## Límites y trabajo en destino

Es seguimiento conservador entre análisis, no flujo óptico. No garantiza distinguir
dos copias físicamente idénticas que se intercambian entre capturas; cambios
muy sutiles de impresión pueden parecer iguales. Las pruebas de cruces y cambios
de carta son sintéticas: faltan clips reales, métricas de falsas asociaciones,
calibración por rareza/idioma y latencia p50/p95 bajo carga. El detector sigue
siendo el existente; YOLO11 todavía requiere datos y entrenamiento.

La reutilización reduce OCR en algunos casos, pero el set añade hasta seis
inferencias. No se afirma que el pipeline completo sea más rápido sin medición.
Evaluar recortes por detección de texto, flujo óptico, perspectiva extrema y
oclusiones; medir selección con reflejos reales antes de relajar umbrales.
La mejora de embeddings y el lector especializado de dígitos siguen diferidos.
