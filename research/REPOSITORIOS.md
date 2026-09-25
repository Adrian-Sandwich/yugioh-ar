# Evaluación de repositorios

Fecha: 2026-09-24. Revisión estática de archivos; no equivale a confirmar que los proyectos compilan o funcionan con nuestra cámara. Los repositorios permanecen separados en `../repos/`.

## Descargas y reproducibilidad

| Carpeta | Contenido descargado | Commit |
|---|---|---|
| `repos/tcg-ar` | Checkout completo del último commit, sin pesos y bases externos. | `ee69f2f5a1dc128e3a2932a33b90268f3a530285` |
| `repos/augmented-reality-card-game` | Checkout completo del último commit, incluidos assets versionados. | `c24b00657a74a08829d2065c314a9557996aa7d4` |
| `repos/opencv-identifier-source` | Clone parcial con checkout selectivo: cuatro scripts Python y README. Imágenes, CSV y pickles pesados omitidos. | `4a087053666cc380a9e2e9892d7ce80a79e1f6b7` |
| `repos/hololens-source` | Clone parcial con checkout selectivo: C#, proyectos/soluciones, documentación, licencias y versión Unity. Assets binarios omitidos. | `151cb254c1511dce13222aa9b926e4af35a3000d` |

Todos se clonaron con `--depth 1`. `repositories.json` registra los orígenes y commits; los archivos `*-files.txt` inventarían todos los paths versionados, incluidos los omitidos del checkout. El campo `downloaded_files` cuenta archivos visibles para rg, no todos los archivos ocultos/ignorados. Se comprobó `git status --porcelain` vacío en los cuatro checkouts válidos.

Las carpetas `repos/opencv-yugioh-card-identifier` y `repos/yugioh-hololens` contienen restos de descargas completas interrumpidas, no checkouts utilizables. Se conservaron sin borrar; usar las carpetas `*-source` de la tabla. `opencv-tree.json` es una respuesta HTTP truncada por timeout y no debe usarse como índice; usar `opencv-identifier-source-files.txt`.

Para obtener más adelante todos los assets de un clone selectivo, ejecutar `git -C repos/hololens-source sparse-checkout disable` o su equivalente para `opencv-identifier-source`, con conexión disponible. No hace falta para revisar el código.

## TCG-AR

Origen: https://github.com/ULiege-VIULab/tcg-ar

Licencia declarada: GPL-3.0. Conservar licencia y procedencia de cualquier módulo que se incorpore; decidir licencia del proyecto antes de distribuir una versión con código copiado.

| Archivo | Evidencia y utilidad | Decisión |
|---|---|---|
| `inference/io_module.py` | Abre webcams con OpenCV y backend MSMF en Windows; captura en buffer y publica RTSP. | Adaptar captura y gestión de cierre; dejar RTSP para más adelante. |
| `core/shared_memory.py` | Buffer de fotogramas compartido entre procesos; documenta longitud 1 para descartar imágenes viejas y necesidad de locks. | Aprovechar el patrón de trabajar con el último fotograma. Medir antes de introducir multiproceso. |
| `inference/identification_pipe.py` | Secuencia detección, recorte, orientación e identificación; tiene entrada de vídeo grabado. | Adoptar interfaz modular y evaluación con vídeos. |
| `core/models/identification.py` | ResNet-50 con cabezas ArcFace/triplet y búsqueda contra referencias. | Segunda alternativa si los rasgos locales fallan; requiere evaluar transferencia a Yu-Gi-Oh! y rendimiento local. |
| `inference/registration_module.py` | ORB, BFMatcher y homografía RANSAC entre vistas. | Referencia geométrica. Añadir validación de descriptores vacíos, correspondencias insuficientes y homografía fallida. |
| `inference/render_module.py` | Estado, resolución de sprites, caché y composición; fuerte dependencia de formas y números Pokémon. | Extraer ideas de caché/composición; implementar nuestro estado por instancia. |
| `core/databases.py` | Mezcla descarga de Pokémon, metadatos y generación sintética. | Rescatar estrategia de datos sintéticos, reemplazar proveedores y esquema. |
| `inference/rendering_3d.py` | Implementación OpenGL con pygame, pyrr y pygltflib; el README dice que es opcional y está desactivada. | Referencia experimental; no tratarla como renderer listo. Sus dependencias no están en `requirements.txt`. |

Hallazgo importante: `_recognize_frame` envía identidad y centro XY al estado, pero no las cuatro esquinas ni la pose completa. Nuestro contrato debe preservar geometría, orientación y timestamp para poder anclar contenido 3D. El rendimiento publicado para Pokémon no es un resultado medido en nuestro hardware o cartas.

## Augmented Reality Card Game

Origen: https://github.com/josephjwilson/augmented-reality-card-game

Licencia declarada: MIT. El checkout incluye `Assets`, informe y UML, pero faltan `Packages` y `ProjectSettings` de un proyecto Unity completo.

| Archivo/carpeta | Evidencia y utilidad | Decisión |
|---|---|---|
| `Assets/Scripts/Player/PlayerCard.cs` | `ScriptableObject` con nombre, descripción, arte, ataque, defensa, vida, movimiento y cooldowns. | Adaptar el patrón de ficha; sustituir campos de combate libre por nuestro catálogo. |
| `Assets/Scripts/Controllers/BattleController.cs` | Fases y turnos mezclados con UI y corrutinas; usa estado estático. | Referencia para presentación de fases, no motor oficial de reglas. |
| `Assets/Scripts/AudioManager.cs` | Sonidos por nombre, AudioMixer y reproducción/parada. | Candidato pequeño para adaptar al visualizador. |
| `Assets/Scripts/Player/Attack_mage.cs`, `MageSpell.cs` | Instanciación de efectos de ataque, curación e impacto. | Referencia de disparo de efectos por eventos. |
| `Assets/Scripts/EntityManager.cs` | Busca objetos por tags en cada `Update` y deriva victoria/derrota de su presencia. | Reemplazar por registro explícito de instancias; no confundir pérdida visual con derrota. |
| `Assets/Scenes/`, carpetas de personajes y efectos | Escenas y contenido de fantasía, no catálogo completo de monstruos Yu-Gi-Oh!. | Inspeccionar visualmente después; no basar el reconocimiento en estos assets. |

Ejemplo de defecto observado: en `BattleController.Update`, la condición `sanityCheck == false && state == WON || state == LOST` puede ejecutar repetidamente el resultado LOST por precedencia de operadores. Refuerza que el código debe adaptarse y probarse, no incorporarse íntegro.

## OpenCV-YugiohCard-Identifier

Origen: https://github.com/haddad-github/OpenCV-YugiohCard-Identifier

No se encontró archivo de licencia en el árbol versionado. Mantener como referencia; no asumir permiso de incorporación del código por ser público.

| Archivo | Hallazgo | Decisión |
|---|---|---|
| `main.py` | `matchTemplate(..., TM_CCOEFF_NORMED)` sobre una imagen fija; dimensiones 81×119 en código, ThreadPoolExecutor de 20 workers y recorrido de todo el catálogo. `match` conserva solo el máximo de similitud, no su posición. | No usar como detector en vivo. Sirve de baseline sobre recortes rectificados y un conjunto pequeño. |
| `mainWithGUI.py` / README | Interfaz para seleccionar una imagen de deck y dimensiones. El README reporta 3–4 minutos por ejecución en el equipo del autor. | Flujo de importación como referencia; no confundir con reconocimiento por webcam. |
| `scrapeYugiohDatabase.py` | Catálogo con ID, nombre, tipo y URL; endpoint v8 codificado y selección de la primera ilustración. | Implementar proveedor propio con API vigente verificada al desarrollar, caché y variantes de arte. |
| `createPickles.py` | Persistencia pickle y lectura de CSV separando por comas. | Nuestro catálogo usará JSON/SQLite y un lector CSV real si se importa CSV. No se ejecutaron pickles descargados. |

No resuelve perspectiva, rotación, seguimiento ni varias instancias iguales. La corrección respecto de la recomendación inicial es sustancial: contiene datos/conceptos útiles, pero no es la base de reconocimiento en tiempo real.

## Yugioh-For-HoloLens

Origen: https://github.com/Generalkidd/Yugioh-For-HoloLens

Licencia principal: MPL-2.0; incluye componentes de terceros. Versión en `YuGiOh/ProjectSettings/ProjectVersion.txt`: Unity **5.5.0f3**. El checkout de código no basta para abrir la escena completa sin recuperar assets.

| Archivo/carpeta | Hallazgo | Decisión |
|---|---|---|
| `YuGiOh/Assets/Scripts/BattleHandler/Cards/` y `Game/` | Clases y enumeraciones de cartas, zonas, modos y jugadores. | Referencia más directa para el vocabulario y esquema del dominio. |
| `YuGhiOhBattleHandler/.../Game/Game.cs` | Lógica de turnos, invocación y sacrificios; el README del componente afirma alcance de las primeras 40 cartas. | Revisar una fase posterior; no asumir motor completo ni correcto. Hay dos implementaciones del dominio en el repo. |
| `YuGiOh/Assets/Scripts/Card.cs` | Selección por gesto/clic y enlace al GameManager. Un bloque grande de instanciación de monstruos está comentado. | Referencia para objetos visuales seleccionables; sustituir entrada HoloLens por nuestros eventos. |
| `YuGiOh/Assets/Scripts/ChangeCardMode.cs` | Comando de cambio de modo, incluso por teclado. | Adoptar idea de controles manuales para corregir la detección. |
| `YuGiOh/Assets/Scripts/GameManagerLocal.cs` | Métodos `PromptFor...` pendientes y varios métodos de colocación vacíos; refresco dependiente de contar frames. | No reutilizar como controlador terminado. |

El índice completo permite localizar assets después; no se descargaron ni inspeccionaron visualmente modelos de este repositorio. Su código aporta más a dominio/interacción que a visión por cámara de PC.

## Recursos sin repositorio público confirmado

- **Ourtechart:** https://www.ourtechart.com/augmented-reality/tutorial/augmented-reality-card-game-yugioh/ . Ofrece archivos RAR mediante Google Drive. El navegador de investigación no pudo recuperar los enlaces de modelos/scripts ni proyecto completo; no se ha descargado ni inspeccionado su contenido. Son archivos externos, no un repo Git confirmado.
- **Project A.T.E.M.:** https://crowncorp.netlify.app/ . Referencia para separar eventos del duelo de su visualización. No se encontró un repo público confirmado en la búsqueda realizada.
- **HKMU:** https://www.hkmu.edu.hk/st/computing/final-year-project-home/yu-gi-oh-mr-assistance-system/ . Referencia académica; no se confirmó código público descargable.

## Prioridad de reutilización

Primero captura, reconocimiento y seguimiento medibles; después animación y audio. Las reglas del duelo deben estar separadas de lo que la cámara ve. Una carta que deja de verse no necesariamente salió del campo.
