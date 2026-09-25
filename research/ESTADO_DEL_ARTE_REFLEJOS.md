# Reflejos en cartas: evaluación y estado del arte

Revisión de fuentes primarias: 25/09/2026. La revisión inicial fue seguida por
una [comparación local reproducible](glare-benchmark/README.md): DocSHRNet y
MIMO-UNetPlus/SHDocs se descargaron y ejecutaron sin entrenamiento. Ambos
mantuvieron 4/7 identidades aceptadas, igual que el original y CLAHE, sin
recuperar seriales en la toma de mesa. UnReflectAnything está descargado pero
su ejecución queda pendiente del acceso autorizado al encoder DINOv3.
La [guía de traslado](glare-benchmark/TRANSFERENCIA.md) conserva comandos,
limitaciones y protocolo para medir tiempos en la siguiente computadora.
El entrenamiento del lector especializado y las mejoras de vectores siguen
pospuestos según la decisión del usuario.

## Diagnóstico local

En `qa/camera-live-failure.png`, la última prueba real muestra siete contornos
detectados y cuatro identidades aceptadas: Utopía, Dragón Blanco de Ojos Azules,
Dragón Negro de Ojos Rojos y Juicio Solemne. Según el usuario, las otras tres
instancias son Mago Oscuro y dos Ojos Anómalos. Esta captura no demuestra que
todos los rechazos se deban al foil. Hay que separar localización, orientación,
cobertura de artes, tamaño/enfoque e identificación.

La captura registra 11755 ms para un análisis. La prueba adicional recibió
respuestas 503 de reconocimiento ocupado mientras el vídeo avanzaba. Añadir
restauración a todas las cartas en cada fotograma agravaría la carga; primero
comparar offline sobre recortes originales y medir latencia incremental.

El panel actual mide blanco saturado en miniaturas, conserva algunas muestras
recientes y no modifica el reconocimiento. Puede omitir reflejos coloreados y
confundir zonas blancas impresas. No es un detector entrenado de especularidad.

Se distinguen tres problemas físicos/visuales:

- Reflejo que reduce contraste pero conserva trazos: potencialmente corregible.
- Saturación que elimina detalle: requiere otra observación para recuperar
  evidencia; una reconstrucción aprendida no verifica un serial.
- Cambios de apariencia del acabado con el ángulo: deben evaluarse aparte del
  reflejo blanco y del arte alternativo. No se encontró validación específica
  de los siguientes métodos en rarezas foil de Yu-Gi-Oh!.

## Candidatos y disponibilidad

| Método | Evidencia y aporte | Disponibilidad observada | Decisión para el proyecto |
|---|---|---|---|
| DocSHRNet / DocHighlight, PRCV 2025 (actas citadas como 2026) | Diseñado para documentos; preservación estructural y adaptación a distintas escalas de reflejo. Dataset de 2201 pares reales de alta resolución. | Código oficial PyTorch, inferencia por ventanas y enlace a checkpoints. Descarga y ejecución no verificadas. Dataset CC BY-NC-SA 4.0. | Primera prueba de restauración de nombre/serial y carta completa. |
| SHDocs, NeurIPS 2024 / MIMO-UNetPlus | Benchmark de documentos con evaluación OCR, además de métricas de imagen. Permite comprobar si restaurar realmente ayuda a leer. | Código, enlaces a pesos reentrenados y dataset. | Baseline aprendido importante; no confundir checkpoints de deblurring con los reentrenados para reflejos. |
| UnReflectAnything, CVPR 2026 Oral | Predice mapa de reflejos y reconstrucción con DINOv3 y reparación de tokens; supervisión sintética basada en geometría. | Código, paquete y ficha HF públicos. GitHub advierte que la API v1.0.2 no carga pesos oficiales, pero también documenta comandos de descarga; HF anuncia pesos. Compatibilidad pendiente de verificar. | Muy interesante por la máscara, antes de usar su reconstrucción para reconocer. No asumir tiempo real en CPU. |
| HAFNet, CVPR 2025 | Filtrado adaptativo jerárquico para reflejos extensos sobre texto, tarjetas y pósteres; datos sintéticos con Unity3D. | Artículo oficial localizado; no se confirmó repositorio oficial ni pesos durante la búsqueda. | Referencia directamente relacionada con nuestras superficies planas; no presentarlo como ejecutable disponible. |
| L²HRNet / DocHR14K, preprint 2025 | Pirámide laplaciana, localización del reflejo y difusión para detalles; 14902 pares, con tarjetas y documentos enfundados. | Artículo completo; publicación de código/dataset anunciada para después de aceptación. No se confirmó una descarga oficial. | Rescatar separación de iluminación y detalle. Los autores reconocen inferencia lenta y fallo con sobreexposición extrema. |
| One-Step SHR + ProbLoRA, ICCV 2025 | Adaptación de SD Turbo para eliminación de reflejos en una pasada. | Artículo y suplemento oficiales; no se confirmó código/pesos oficiales. | Comparador de investigación; una pasada no garantiza baja latencia en nuestra PC. |
| StableDelight | Difusión de un paso aplicada a superficies con textura, implementación pública. | Repositorio y loader Torch Hub; descarga/ejecución no verificadas. | Comparación exploratoria sobre arte. No inferir exactitud de dígitos a partir de imágenes visualmente convincentes. |
| Pixel clustering, SIBGRAPI 2018 | Separación mediante cromaticidad, implementación C++/OpenCV y CUDA opcional. | Código público. | Baseline clásico sin entrenamiento; no es el estado del arte reciente. Validar supuestos sobre foil. |

Fuentes primarias de la tabla:

- [DocSHRNet: código e inferencia](https://github.com/shallweiwei/DocSHRNet) y [DocHighlight: dataset](https://github.com/SCUT-DLVCLab/DocHighlight).
- [SHDocs: artículo NeurIPS](https://proceedings.neurips.cc/paper_files/paper/2024/file/af9199ef7d5ff267451a667170124c04-Paper-Datasets_and_Benchmarks_Track.pdf) y [repositorio](https://github.com/JovinLeong/SHDocs).
- [UnReflectAnything: proyecto](https://alberto-rota.github.io/UnReflectAnything/), [código y advertencia de versión](https://github.com/alberto-rota/UnReflectAnything), [ficha de modelo](https://huggingface.co/AlbeRota/UnReflectAnything).
- [HAFNet: CVPR 2025](https://openaccess.thecvf.com/content/CVPR2025/html/Jiang_Hierarchical_Adaptive_Filtering_Network_for_Text_Image_Specular_Highlight_Removal_CVPR_2025_paper.html).
- [L²HRNet: artículo y limitaciones](https://arxiv.org/html/2504.14238v1).
- [One-Step SHR: ICCV 2025](https://www.openaccess.thecvf.com/content/ICCV2025/html/Atmis_One-Step_Specular_Highlight_Removal_with_Adapted_Diffusion_Models_ICCV_2025_paper.html).
- [StableDelight](https://github.com/Stable-X/StableDelight).
- [Baseline de clustering](https://github.com/MarcioCerqueira/RealTimeSpecularHighlightRemoval).

## Qué cambia la evidencia

SHDocs encontró que varios métodos de eliminación de reflejos empeoraban el
OCR frente al original; las métricas PSNR/SSIM tampoco equivalen a éxito de
lectura. Su evaluación OCR inicial usa MIMO-UNetPlus como modelo de deblurring;
las pruebas posteriores reentrenan modelos sobre SHDocs. No atribuir resultados
de una variante a otra. Este trabajo respalda medir el objetivo final, no
elegir simplemente la imagen más agradable.

Nuestra recomendación es una inferencia de ingeniería: conservar original y
restaurada como alternativas y exigir evidencia adicional antes de aceptar
una identidad nueva. Para un número exacto de ocho dígitos, medir exactitud
de toda la cadena y falsos positivos, no solo semejanza visual o CER promedio.

La polarización sigue siendo relevante incluso en investigaciones recientes:
DocHighlight y SHDocs la utilizan en la adquisición de datos. Para nuestra mesa,
probar luz difusa lateral y, si se dispone de filtros, polarización cruzada;
la respuesta concreta de cada foil debe medirse. Fuente óptica:
[Edmund Optics](https://www.edmundoptics.com/knowledge-center/application-notes/optics/introduction-to-polarization).

## Experimento propuesto sin entrenamiento nuevo

1. Conservar originales de las siete instancias. Identificar manualmente
   posición, arte y serial; registrar si hay funda y acabado. No usar la salida
   del detector como verdad de referencia.
2. Capturar las mismas cartas con tres configuraciones de luz, dos distancias
   y varias orientaciones. Mantener fija la exposición/enfoque cuando sea
   posible. Reservar sesiones distintas para evaluación, no dividir al azar
   fotogramas casi idénticos entre ajuste y prueba.
3. Separar fallos: contorno ausente, orientación incorrecta, identidad rechazada,
   identidad errónea y OCR ilegible. Comparar cada carta contra su propia toma
   con menos reflejo, a tamaño similar; así se reduce la confusión con el arte.
4. Comparar original, CLAHE de luminancia, selección temporal por región,
   DocSHRNet y MIMO-UNetPlus con checkpoint documentado. Añadir UnReflectAnything
   cuando se verifique que los pesos corresponden a la API. No mezclar versiones.
5. Registrar identidad exacta, passcode exacto, rechazos correctos, errores
   confiados, estabilidad de las dos copias, latencia p50/p95 y memoria. Examinar
   también zonas que estaban bien antes del procesamiento para detectar daño.
6. Integrar solo una alternativa que mejore a igual tasa de falsas identidades.
   Ejecutarla sobre recortes difíciles en un worker acotado, conservando vídeo
   independiente. No procesar automáticamente las siete cartas con una red de
   restauración en cada fotograma.

La selección temporal/fusión por regiones es una propuesta para este sistema,
no un resultado SOTA demostrado aquí. Necesita alineación de la misma instancia
y que el reflejo cambie: una cámara y luz inmóviles pueden repetir el mismo
detalle oculto indefinidamente. Preferir primero selección de una región
observada íntegra; fusionar solo si aporta evidencia sin deformar caracteres.

Orden recomendado: diagnosticar la escena y cobertura de artes → benchmark
offline de DocSHRNet y MIMO-UNetPlus → mapa de reflejos de UnReflectAnything
si es reproducible → integración selectiva. No hay resultados locales de
estos modelos nuevos ni promesa de reconocer todas las rarezas.
