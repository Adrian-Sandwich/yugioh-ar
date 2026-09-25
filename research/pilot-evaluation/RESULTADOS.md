# Evaluación inicial del piloto

Dos capturas reales de una sola identidad y sesión, más escenas sintéticas reutilizando referencias. No mide precisión general, rarezas ni soporte multilingüe. Umbrales ONNX experimentales, sin calibrar. Tiempos de CPU tras cargar modelos; excluyen captura y arranque.

| Método | Caso | Identidades/instancias correctas | Falsas aceptaciones | ms |
|---|---|---:|---:|---:|
| sift | synthetic-multiple | 3/3 | 0 | 3443.3 |
| sift | synthetic-shadow-rotation | 3/3 | 0 | 2976.4 |
| sift | blank | 0/0 | 0 | 162.4 |
| sift | synthetic-outside-pilot | 0/0 | 0 | 1884.5 |
| sift | carta-2026-09-25T04-15-11-032Z.jpg | 1/1 | 0 | 4912.5 |
| sift | carta-2026-09-25T04-13-54-278Z.jpg | 1/1 | 0 | 4053.5 |
| draw2-small | synthetic-multiple | 3/3 | 0 | 1722.3 |
| draw2-small | synthetic-shadow-rotation | 3/3 | 0 | 1745.7 |
| draw2-small | blank | 0/0 | 0 | 245.3 |
| draw2-small | synthetic-outside-pilot | 1/1 | 0 | 718.1 |
| draw2-small | carta-2026-09-25T04-15-11-032Z.jpg | 1/1 | 0 | 815.4 |
| draw2-small | carta-2026-09-25T04-13-54-278Z.jpg | 1/1 | 0 | 1780.4 |
| embeddings | synthetic-multiple | 3/3 | 0 | 1810.5 |
| embeddings | synthetic-shadow-rotation | 3/3 | 0 | 1793.3 |
| embeddings | blank | 0/0 | 0 | 280.5 |
| embeddings | synthetic-outside-pilot | 0/0 | 0 | 875.3 |
| embeddings | carta-2026-09-25T04-15-11-032Z.jpg | 1/1 | 0 | 1071.3 |
| embeddings | carta-2026-09-25T04-13-54-278Z.jpg | 1/1 | 0 | 3112.5 |
