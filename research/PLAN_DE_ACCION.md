# Yu-Gi-Oh! AR con cámara y PC

**Plan vigente:** [mejora integral con cámara variable](PLAN_MEJORA_INTEGRAL.md).
Reúne los hallazgos del pipeline y SQL, sustituye el supuesto inicial de cámara
fija y establece prioridades, datos y criterios de aceptación. Las fases que
siguen conservan el contexto histórico del piloto.

Decisión del usuario, 25/09/2026: dejar para una etapa futura tanto el
[lector especializado de dígitos borrosos](digit-references/README.md) como el
[trabajo adicional de vectores e invariancia](PLAN_VECTORES_E_INVARIANCIA.md).
No continuar por ahora su desarrollo, entrenamiento ni integración. Conservar
repositorios, pruebas y planes para retomarlos cuando el usuario lo indique.
El piloto de embeddings y el OCR ya integrados en el visor se mantienen.

Estado vigente, 25/09/2026: catálogo unificado, galería de revisión, anotación de capturas, piloto de 50 cartas, comparación SIFT/DRAW2/embeddings y sprites AR implementados. Consultar [entrega y resultados](ENTREGA_PILOTO.md). Siguen pendientes la validación amplia con cartas reales, entrenamiento y 3D. Lo siguiente conserva el contexto y las fases del plan inicial.

Fecha de revisión inicial: 2026-09-24. Alcance: cámara fija, procesamiento local y vídeo aumentado en monitor. El primer visor (`../camera_viewer.py`) y reconocimiento SIFT se validaron en dos capturas distintas de la referencia de Blue-Eyes.

El entrenamiento intensivo se realizará en otra computadora. Seguir el [plan de vectores e invariancia](PLAN_VECTORES_E_INVARIANCIA.md), que detalla traslado, datos, aumentos, evaluación y exportación. La implementación del piloto evaluó pesos existentes y expuso sus features, sin entrenar pesos nuevos en esta PC.

## Decisión inicial

Referencias: [evaluación de DRAW, DRAW2, Lowhur y Roboflow](references-20260924/REVISION.md). DRAW2 se comparó con SIFT y recuperación vectorial en el piloto; ver el informe de entrega para resultados y limitaciones. Los métodos permanecen seleccionables.

YGOJSON queda como candidato de catálogo local multilingüe. Se descargó y se generó un mapa de 13 631 etiquetas del clasificador compacto con enlace único; 28 casos requieren resolución. El snapshot recibido tiene últimas lecturas principales de abril de 2026. No usar índices del modelo como IDs universales ni interpretar cobertura de catálogo como precisión del detector.

Construir una aplicación pequeña con Python/OpenCV para captura, reconocimiento y seguimiento. Usar un catálogo local de 5–10 cartas y vídeo grabado para medir resultados reproducibles. Integrar Unity como visualizador 3D después de validar el reconocimiento. Mantener los repositorios descargados como referencias independientes.

La consulta del equipo reportó Intel UHD Graphics; no se ha confirmado una GPU NVIDIA ni el rendimiento de inferencia. Priorizar una primera versión para CPU. El entorno de TCG-AR depende de PyTorch y OpenMMLab; no instalarlo completo como requisito de la primera demo.

## Arquitectura propuesta

```text
Cámara/vídeo -> captura con timestamp -> detector -> identificación -> seguimiento
                     |                                      |
                     |                         estado de instancias + eventos
                     +-----------------------> visualizador -> monitor
```

Un único componente posee la cámara. El visualizador recibe vídeo y estado con timestamps compatibles: evitar que Python y Unity intenten abrir la misma cámara. En el prototipo inicial, dibujar contornos y nombres en OpenCV; decidir el transporte de vídeo al integrar Unity y medir su latencia.

Separar `card_id` (identidad de catálogo), `artwork_id` (imagen de referencia) y `track_id` (copia física observada). Mantener esquinas, centro, orientación, confianza, última observación y estado visible/oculto/retirado por instancia. No deducir la identidad de una carta boca abajo sin una observación previa; si se pierde la asociación, marcarla desconocida.

## Fases y criterios de salida

1. **Captura y conjunto de evaluación.** Elegir cámara, resolución y encuadre; grabar cartas quietas, movimiento, dos copias iguales, fundas, reflejos, giro, cartas ajenas al catálogo y manos tapando. Guardar anotaciones y separar clips de ajuste y evaluación. Salida: reproducción local y medición de FPS/latencia sin reconocimiento.
2. **Reconocimiento de 5–10 cartas.** Probar rasgos locales ORB/SIFT y correspondencias verificadas geométricamente; comparar con recortes de zonas de un tapete calibrado si detectar contornos libres resulta frágil. Precalcular descriptores y limitar candidatos al deck. Incorporar rechazo de desconocidos. Salida propuesta: ≥95% de acierto en observaciones claramente visibles del conjunto reservado y ≤1% de falsos positivos en desconocidos; registrar casos y denominadores, no solo un porcentaje global.
3. **Seguimiento estable.** Asociar detecciones por posición/geometría y evidencia visual; confirmar entradas durante varias observaciones y tolerar pérdidas breves. Distinguir dos copias simultáneas. Salida: una sola invocación por entrada y continuidad durante un ocultamiento breve de prueba; no adivinar trayectorias tras ocultamientos ambiguos.
4. **Calibración y primer monstruo.** Calibrar intrínsecos/distorsión de la cámara y plano de mesa; usar marcadores en bordes si ayudan. Homografía para coordenadas del plano; pose y cámara virtual calibradas para 3D. Integrar un modelo con procedencia documentada y animación de invocación. Salida: modelo anclado sin deriva apreciable en posiciones de prueba y vídeo/estado sincronizados.
5. **Ampliación al deck.** Repetir evaluación con 40–60 cartas, varias simultáneas y variantes de arte. Si el método ligero falla, evaluar embeddings y generación sintética de TCG-AR con datos Yu-Gi-Oh! antes de decidir entrenamiento o GPU. Añadir efectos y salida OBS tras estabilizar la visualización.

Objetivos de rendimiento iniciales, pendientes de medir: visualización ≥25 FPS a 720p, reconocimiento ≥5 Hz y actualización visible p95 <300 ms. Revisarlos con la cámara real; no son prestaciones prometidas.

## Primer entregable de implementación

Aplicación que abre cámara o vídeo, permite cargar imágenes de referencia y dibuja identidad, contorno, orientación y confianza. Guarda detecciones y tiempos para evaluar; rechaza cartas desconocidas. La siguiente entrega añade persistencia y eventos; después, un monstruo.

## Datos y componentes pendientes

- Cámara: Android con IP Webcam en `http://192.168.1.18:8080`; recepción de JPEG y servidor local comprobados. Montaje sobre la mesa pendiente.
- Cartas físicas y referencias: seleccionar un pequeño conjunto con ilustraciones distintas y un par difícil.
- Modelo 3D: revisar archivos reales y procedencia; la licencia de un repositorio no prueba por sí sola los derechos sobre cada asset incluido.
- Reglas completas de duelo, multijugador, lectura de cartas ocultas y segmentación de manos: fuera de la primera entrega.
- La revisión inicial no ejecutó los proyectos externos. El piloto posterior usa los pesos ONNX descargados en un entorno separado, con dependencias fijadas y pruebas documentadas.
