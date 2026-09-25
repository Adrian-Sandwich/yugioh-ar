# OCR del nombre — 25/09/2026

Implementado en `name_ocr.py`, integrado en `passcode_ocr.py` y mostrado en
`web/camera.js`. Comparte el motor RapidOCR existente: no descarga otro modelo.

Lee la franja superior de la carta rectificada en orientaciones 0/180, con
una alternativa estrecha y CLAHE cuando la lectura original tiene confianza
inferior a 0.90 o sin coincidencia literal en el registro. Máximo cuatro lecturas por carta. Sólo procesa geometría
`contour_refined` y altura estimada de texto de al menos ocho píxeles nativos.
El serial tiene su propio filtro: puede omitirse mientras el nombre sí se lee.

El índice de nombres EN/ES/DE/FR/PT se obtiene de SQLite en modo lectura y se
revisa como máximo una vez por minuto, incluyendo cambios del WAL. Conserva
acentos para coincidencias; normaliza mayúsculas, puntuación y espacios.
Una lectura de confianza >=0.85 puede producir una coincidencia. Las
aproximaciones son sugerencias, nunca confirmaciones. Múltiples identidades
son ambiguas y las discrepancias con serial o reconocimiento visual se muestran
como conflictos. El OCR no recibe el nombre esperado del reconocimiento visual.
No infiere el idioma impreso a partir de los idiomas compatibles del catálogo.

La lectura participa en el consenso y la fusión descritos en
[EVIDENCIA_TEMPORAL.md](EVIDENCIA_TEMPORAL.md), sin modificar automáticamente la identidad visual. Sus errores no interrumpen
el lector de serial. El trabajador asíncrono conserva la cola acotada existente.

## Verificación y límites

- `qa_name_ocr.py`: normalización, ambigüedad, conflictos, sugerencias, refresco,
  imagen vacía, foto real y rotación de 180 grados. Cinco textos renderizados
  en los idiomas objetivo: pasan, pero no sustituyen fotografías físicas.
- `qa_pipeline_core.py`: filtros independientes de tamaño y aislamiento de
  errores del nombre respecto del serial.
- `qa_passcode_browser.py`: nombre y serial reales visibles; vídeo continúa;
  una foto fija no cuenta como múltiples capturas independientes.
- Resultados: `qa/name-ocr/validation.json` y `qa/name-ocr/scene-results.json`.
  En la escena de nueve candidatas, cuatro tienen geometría utilizable:
  Blue-Eyes y Utopia coinciden, Dark Magician se lee mal y Odd-Eyes queda
  con confianza baja. No está resuelta la identificación de toda la escena.
- Una lectura caliente de nombre midió aproximadamente 101 ms en esta PC.
  No es la latencia total del pipeline ni una medición p50/p95.

## Próximos pasos en destino

Validar fotografías reales por idioma, rareza y distancia; calibrar confianza;
mejorar la geometría y detectar la región de texto; probar alternativas incluso
cuando un texto incorrecto tiene confianza alta; elegir el mejor fotograma y
añadir consenso temporal sin transferir lecturas entre cartas. El OCR de set code y la fusión inicial ya están implementados; falta validarlos en clips reales.

Recrear dependencias con `requirements-ocr.txt`. Los modelos RapidOCR están
dentro del entorno actual: para una instalación sin internet hay que copiar
también los pesos y configurar sus rutas; copiar sólo el código no basta.
Referencia del modelo: https://rapidai.github.io/RapidOCRDocs/main/en/model_list/
