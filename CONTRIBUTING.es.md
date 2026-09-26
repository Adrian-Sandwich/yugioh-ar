# Cómo contribuir

*[English version](CONTRIBUTING.md)*

Gracias por querer ayudar. Este proyecto quiere llegar a un motor de duelo de
Yu-Gi-Oh! en realidad aumentada que funcione en tiempo real, y todavía le
falta mucho. Hay trabajo para quien programa y para quien no.

## Sin programar

**Fotos de cartas reales.** Es lo que más falta. Sirven fotos de una o varias
cartas sobre una mesa, tomadas con el teléfono, en cualquiera de estos idiomas:
español, inglés, alemán, francés, portugués. Variedad que ayuda: con y sin
fundas, con brillo o sombra, cartas giradas, dos copias de la misma carta,
cartas raras o con acabado brillante, y también cartas que **no** son de
Yu-Gi-Oh! (sirven como negativos).

Cómo entregarlas:

1. Si tienes el proyecto corriendo, abre http://127.0.0.1:8768/capture, sube
   la foto y marca las cuatro esquinas de cada carta y su identidad. Después
   comparte el contenido de `data/pilot/captures/`.
2. Si no, abre un issue con las fotos adjuntas o un enlace, e indica idioma y
   condiciones. Alguien más las anotará.

No subas fotos con datos personales visibles. Al compartirlas aceptas que se
usen para entrenar y evaluar este proyecto.

**Probar en tu hardware.** Sigue [ENTREGA_PILOTO.md](research/ENTREGA_PILOTO.md)
para arrancar el visor en tu PC con tu cámara, y cuenta qué pasó en un issue:
sistema, Python, cámara, qué se reconoció y qué no, y los JSON que dejan las
pruebas en `research/qa/`.

**Revisar el catálogo.** La galería en http://127.0.0.1:8768 muestra
referencias de arte propuestas que hay que aprobar o corregir. Las decisiones
se guardan en `data/catalog/reviews.sqlite`; comparte ese archivo.

## Programando

Áreas abiertas, de más a menos urgente:

- Entrenamiento con datos reales del detector de cuatro esquinas (YOLO11) y
  ajuste contrastivo de los embeddings. Los experimentos ya están diseñados en
  [COLA_EXPERIMENTOS.md](research/COLA_EXPERIMENTOS.md); hace falta una GPU.
- Seguimiento con flujo óptico y cámara en movimiento.
- Aislar la inferencia ONNX en un proceso recuperable.
- Motor de reglas de duelo: zonas, fases, puntos de vida. Es independiente del
  reconocimiento y se puede empezar desde cero, en Python o en otro lenguaje.
- Capa AR 3D con modelos de licencia clara.
- Reducir latencia: warp limitado a la región de interés, batching, exportación
  de pose a ONNX.

Antes de empezar algo grande, abre un issue para acordar el enfoque. El
[estado consolidado](research/TRANSFERENCIA_GENERAL.md) y el
[plan vigente](research/PLAN_MEJORA_INTEGRAL.md) explican qué se ha decidido
ya y por qué.

## Reglas de la casa

Son las que el proyecto ha seguido desde el primer día. Mantenerlas es lo que
permite que un tercero confíe en lo que dice el repositorio.

1. **Cada cambio dice qué se probó y qué no.** Un pull request describe la
   prueba que lo respalda (`qa_*.py`, informe JSON en `research/qa/`) y sus
   límites. Si algo no se midió, se dice.
2. **No se afirman cifras que no se midieron.** Un tiempo observado bajo carga
   no es un benchmark; una prueba con dos fotos no es una tasa de acierto.
3. **Identidad, arte y copia física son cosas distintas.** `card_id`,
   `artwork_id` y `track_id` no se mezclan.
4. **El OCR es evidencia, no verdad.** No corrige caracteres a ciegas ni
   sobrescribe la identidad visual. Las ambigüedades se conservan.
5. **Los datos regenerables van aparte de las decisiones humanas.** Nada que
   se reconstruya automáticamente debe pisar revisiones o anotaciones.
6. **Los datos pesados no entran en Git.** `data/`, `downloads/`, `repos/`,
   entornos y pesos siguen fuera. Las imágenes de cartas no se redistribuyen.
7. **Documenta en `research/`.** Cada bloque de trabajo deja un documento con
   fecha, qué se hizo, evidencia y pendientes. El idioma del proyecto es el
   español; se aceptan contribuciones en inglés.

## Flujo

1. Haz un fork y una rama por cambio.
2. Ejecuta las pruebas relevantes con `.venv-eval` y adjunta el resultado.
3. Abre el pull request explicando qué cambia, cómo se verificó y qué queda
   fuera.

Para preguntas, abre un issue. No hay canal de chat todavía.
