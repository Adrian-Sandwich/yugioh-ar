# Comparación exploratoria de reflejos — 25/09/2026

Trabajo preparado mientras continúa la descarga de Neuron. Los tiempos de
rendimiento se medirán en la siguiente computadora. La guía de traslado y los
comandos reproducibles están en [TRANSFERENCIA.md](TRANSFERENCIA.md).

## Resultado observado

Se compararon una captura real de siete cartas (seis identidades, dos copias
de Ojos Anómalos) y una foto cercana de Dragón Blanco como control.

| Variante | Primera opción correcta, mesa | Identidades aceptadas, mesa | Seriales leídos, mesa | Serial cercano correcto |
|---|---:|---:|---:|---|
| Original | 7/7 | 4/7 | 0/7 | Sí |
| CLAHE | 7/7 | 4/7 | 0/7 | Sí |
| DocSHRNet | 7/7 | 4/7 | 0/7 | Sí |
| MIMO-UNetPlus / SHDocs | 7/7 | 4/7 | 0/7 | Sí |

Ninguna variante recuperó las identidades rechazadas: Mago Oscuro y ambas
copias de Ojos Anómalos. Las cuatro aceptadas fueron Utopía, Dragón Negro,
Juicio Solemne y Dragón Blanco. No hubo falsas aceptaciones en esta muestra.
Los umbrales del piloto se mantuvieron: similitud 0.80 y margen 0.07.
Una primera opción correcta por debajo de esos umbrales sigue siendo un rechazo.

Esta prueba no demuestra una mejora de reconocimiento con restauración; por
ello estos modelos no se añadieron al visor. Tampoco demuestra que no puedan
ayudar en otras capturas. Solo hay una escena, sin referencia limpia pareada,
y faltan negativos, otros artes, idiomas, rarezas y sesiones independientes.
El serial esperado proviene del registro; no implica que sea legible en la foto.

## Material preparado

- [Galería comparativa local](comparison.html): originales y resultados, identidad,
  similitud, margen y OCR por recorte. Conservar su carpeta `outputs/` al copiarla.
- [Resumen JSON](summary.json) y `outputs/*/evaluation.json`: medidas completas.
- [Muestras y etiquetas](samples.json), `table-original.jpg` e `inputs/`: entradas
  congeladas para repetir la comparación sin variaciones de cámara.
- [Inventario verificado](downloads.json): tres checkpoints, unos 3.92 GB,
  hashes SHA-256, auditoría de serialización y commits de repositorios.
- [Fuentes](sources.json), `environment.txt` y scripts: procedencia y reproducción.

DocSHRNet y MIMO se ejecutaron con carga estricta de pesos. MIMO usa el checkpoint
SHDocs y padding reflect; la diferencia con el padding negro upstream se explica
en la guía. UnReflectAnything se descargó, pero no se ejecutó: el encoder upstream
DINOv3 requiere acceso autorizado y devolvió HTTP 401.

Los tiempos locales archivados incluyen carga concurrente y una sola ejecución;
no son un benchmark controlado. El wrapper permite preparar mediciones CPU/GPU,
calentamiento y repeticiones en destino. La ruta GPU todavía no está validada.

## Orden de continuación

1. Trasladar y verificar el material siguiendo `TRANSFERENCIA.md`.
2. Capturar las mismas cartas con luz difusa/lateral, distintos ángulos y
   acercamientos; guardar originales y etiquetas de funda, arte, rareza e idioma.
3. Repetir la evaluación con negativos y separar errores de contorno, orientación,
   identificación y OCR. Comparar selección temporal de capturas con restauración.
4. Medir rendimiento en destino y decidir integración únicamente si mejora la
   calidad con una latencia aceptable. Vectores nuevos y entrenamiento del lector
   especializado permanecen pospuestos.
