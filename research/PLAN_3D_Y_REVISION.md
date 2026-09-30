# Plan: revisión humana, generación 3D y motor gráfico

Fecha: 29/09/2026 (ampliado el mismo día: dibujo, tableta, conjunto de control, candidatos de holograma,
una revisión de coherencia, recarga de sprites en el visor, `build()` que respeta rechazos, crítico
combinado y una revisión contra literatura y proyectos parecidos: ver [Referencias](#referencias)).

**Cómo se hizo:** en un entorno remoto temporal (Linux, sin GPU, sin tus datos), sobre un clon del
repositorio público. Nada se subió a GitHub; todo llega en `yugioh-ar-plan-3d.patch`. Resume una conversación de planeación y deja los pasos para aplicarlos en la PC
con la RTX 4070. Nada de lo nuevo se ejecutó todavía con datos reales ni con GPU: se escribió en un
entorno sin GPU y se probó con datos sintéticos (detalle en [Qué está probado](#qué-está-probado)).

## Índice

1. [Decisiones](#decisiones)
2. [Conceptos: homografía, solvePnP y pose](#conceptos-homografía-solvepnp-y-pose)
3. [Motor gráfico](#motor-gráfico)
4. [Revisión humana y ciclo de reentrenamiento](#revisión-humana-y-ciclo-de-reentrenamiento)
   - [Corregir dibujando](#corregir-dibujando)
   - [Tableta y red local](#tableta-y-red-local)
   - [Conjunto de control: ¿mejoró de verdad?](#conjunto-de-control-mejoró-de-verdad)
   - [Hologramas: revisar el recorte que perdió](#hologramas-revisar-el-recorte-que-perdió)
   - [Reglas del ciclo](#reglas-del-ciclo)
   - [Qué mejora cada cosa](#qué-mejora-cada-cosa)
5. [Generación automática de modelos 3D](#generación-automática-de-modelos-3d)
   - [Fase posterior: Magias de Campo](#fase-posterior-magias-de-campo)
6. [Pasos en casa](#pasos-en-casa)
   - [Prueba rápida antes de la sesión larga](#prueba-rápida-antes-de-la-sesión-larga)
   - [Qué correr en paralelo](#qué-correr-en-paralelo)
7. [Tareas abiertas](#tareas-abiertas)
8. [Referencias](#referencias)
9. [Qué está probado](#qué-está-probado)

## Decisiones

- **El siguiente paso es 3D**, pero antes hay que asegurar las entradas: los recortes 2D. Un
  modelo 3D generado desde un mal recorte sale mal, así que primero se revisan y mejoran los sprites.
- **Revisión humana por teclado, dedo o lápiz** de cada recurso generado: arte original a la
  izquierda, lo generado a la derecha. `→` aprueba y `←` rechaza con motivo. `D` corrige
  dibujando: verde para «el recorte se comió esto», rojo para «esto sobra». La misma herramienta
  sirve después para revisar los modelos 3D.
- **Tableta en la red de casa** (`--lan`, con clave de acceso), sin exponer nada a internet.
- **Conjunto de control** revisado a ciegas antes y después de cada reentrenamiento, fuera del
  entrenamiento, para medir la mejora sin engañarnos.
- **Los veredictos entrenan al crítico adversarial** en rondas: revisar, recalibrar, regenerar y
  volver a revisar lo que cambió.
- **Modelos 3D con generadores imagen→3D preentrenados**, comparados en un banco de pruebas en la 4070.
- **No se usan modelos 3D extraídos de juegos oficiales** (Master Duel, Duel Links, Legacy of the
  Duelist), ni como entrenamiento ni como muestra. Extraerlos viola los términos de esos juegos y
  son assets de Konami; en un repositorio público pueden traer una notificación DMCA que tumbe el
  proyecto entero. Una muestra pequeña tampoco bastaría para entrenar un generador 3D. El estilo
  se ajusta con prompts o con nuestros propios modelos aprobados.
- **Motor gráfico: Three.js en el navegador primero.** Unity, después, si hace falta algo más
  parecido a un juego. Unreal queda como opción para una salida de alta calidad por OBS.

## Conceptos: homografía, solvePnP y pose

**Homografía.** Es la transformación que lleva un plano a otro plano; se calcula con 4 puntos. Con las
cuatro esquinas de una carta sabemos cómo pegar una imagen plana encima con la perspectiva
correcta. Es lo que hacen hoy los sprites 2D (`web/ar.js`). Su límite: sólo sirve para cosas planas.
Un monstruo de pie tiene altura y no se puede dibujar bien sólo con una homografía.

**solvePnP** (OpenCV). Recibe puntos cuya posición real se conoce (por ejemplo, las esquinas de una
carta de 59 × 86 mm, o los marcadores ArUco del tapete), dónde aparecen en la imagen y los
parámetros internos de la cámara (distancia focal, centro, distorsión). Devuelve la rotación y la
traslación de la cámara respecto a ese objeto.

**Pose 3D.** Es esa rotación más traslación. Con ella, un motor 3D coloca una cámara virtual igual
que la real, y el modelo se ve apoyado en la mesa desde cualquier ángulo.

**¿Pose del tapete o de la carta?** Cada uno cumple un papel:

- **El tapete** define el suelo del mundo 3D. Es grande y tiene muchos puntos (ArUco), así que su
  pose sale estable. Con la cámara fija basta calcularla una vez y refrescarla de vez en cuando.
- **Cada carta** sólo necesita su posición y su giro *sobre ese plano*. Eso ya lo da la homografía
  actual, llevada a coordenadas del tapete. Calcular la pose 3D con la carta sola haría temblar
  al monstruo, porque la carta es pequeña y su inclinación sale ruidosa.

Requisito previo: **calibrar los intrínsecos de la cámara** una vez por cámara, con un tablero
ChArUco impreso y `cv2.aruco.calibrateCameraCharuco`, o con un tablero de ajedrez. Hoy no están
calibrados.

**Cuidado con la cámara cenital: es el peor caso para la pose.** Un plano visto de frente tiene dos
poses que encajan igual de bien (IPPE, Collins y Bartoli 2014), y el `solvePnP` iterativo de OpenCV
sólo devuelve una: en los casos ambiguos se equivoca la mitad de las veces, y el modelo «voltea».
La ambigüedad crece cuando el objeto es pequeño o está lejos, que es la razón de fondo para usar el
tapete y no la carta. Además, desde arriba un monstruo 3D se ve casi sólo su cabeza. Por eso:

- **Dos cámaras, como TCG-AR:** reconocer con la cenital (lo que ya funciona) y dibujar el 3D en una
  cámara **en ángulo**, donde el tapete se ve oblicuo y la pose sale bien condicionada. TCG-AR
  reconoce en la cenital y lleva los resultados a las cámaras laterales con una calibración única;
  para 3D, cada cámara necesita su propia pose del tapete (sus ArUco deben verse en ella).
- **Resolver con `cv2.solvePnPGeneric(..., flags=cv2.SOLVEPNP_IPPE)`**, que devuelve las dos
  soluciones con su error; elegir la más cercana a la del cuadro anterior y refinarla con
  `cv2.solvePnPRefineLM` usando todos los ArUco visibles, no sólo cuatro puntos.
- **Suavizar** con un filtro que no meta retraso cuando la cámara se mueve (por ejemplo el
  «One Euro»). Con la cámara fija, promediar varios cuadros al calibrar la mesa basta.

## Motor gráfico

La arquitectura ya separa análisis y dibujo: el servidor en Python manda esquinas e identificadores,
y el navegador dibuja. El motor 3D es otro cliente de ese mismo estado.

| Opción | Ventajas | Costos | Cuándo |
|---|---|---|---|
| **Three.js** (o Babylon.js) en `web/` | Sigue la arquitectura actual; carga glTF; no toca el backend | Menos herramientas de animación y efectos | **Primero**: prototipo con un modelo de prueba |
| **Unity** (+ AR Foundation) | Animación, física y efectos; camino a gafas y a app móvil | Hay que mandarle el vídeo o darle la cámara (regla: un solo dueño de la cámara); proyecto aparte en C# | Si Three.js se queda corto |
| **Unreal** | Mejor calidad visual; aprovecha la 4070 | El más pesado de integrar e iterar | Salida en alta calidad por OBS |

El plan inicial (`PLAN_DE_ACCION.md`) ya proponía Unity como visualizador 3D después de validar el
reconocimiento, y la revisión de `REPOSITORIOS.md` anota que el estado debe llevar geometría,
orientación y marca de tiempo para anclar 3D. Ambas cosas siguen vigentes.

## Revisión humana y ciclo de reentrenamiento

### Por qué

El crítico de `auto_cutout.py` es una regresión logística sobre 7 rasgos de la máscara. Aprendió
de los close-ups de TDOANE (IoU ≥ 0.8 = bueno), y esos close-ups sólo existen para cartas que *ya*
tienen sprite hecho a mano. Los unos 7,000 sprites automáticos los juzga un crítico que nunca vio
ese tipo de carta. Los veredictos humanos son exactamente las etiquetas que faltan.

Lo que este ciclo mejora, con honestidad:

- **Mejora al crítico**, es decir, qué recorte se elige entre los candidatos y cuándo conviene el
  holograma. Es barato, porque son 7 números por carta, y se nota rápido.
- **No reentrena a BiRefNet.** Afinar el segmentador necesita máscaras correctas, no sólo sí o no.
  Los recortes aprobados sí sirven como pseudo-verdad para afinarlo más adelante, cuando haya
  cientos. Eso es una fase posterior (ver [Tareas abiertas](#tareas-abiertas)).

### Cómo sirve al 3D

- Los recortes **aprobados** son las únicas entradas confiables para el generador 3D. El banco
  debería tomar sus muestras de ahí.
- El motivo **«El arte corta la figura»** marca cartas que necesitan el paso de completar la figura
  antes del 3D.
- La misma herramienta revisa los modelos 3D (`--kind gen3d`) con motivos propios. Esos veredictos
  eligen el generador y, más adelante, entrenan un crítico 3D con la misma receta.

### El revisor (`review_server.py` + `web/review.html`)

```powershell
.venv-gpu/Scripts/python.exe review_server.py                    # sprites; abre http://127.0.0.1:8770/
.venv-gpu/Scripts/python.exe review_server.py --order hologram   # sólo las cartas que cayeron a holograma
.venv-gpu/Scripts/python.exe review_server.py --kind gen3d       # modelos del banco 3D
.venv-gpu/Scripts/python.exe review_server.py --stats            # resumen -> research/qa/sprite-review.json
```

| Tecla | Acción |
|---|---|
| `→` | Aprobar y pasar a la siguiente |
| `←` | Rechazar: abre el panel de motivos |
| `1`–`9` | Marcar o desmarcar motivos (con el panel abierto) |
| `/` | Escribir una nota libre |
| `Enter` / `Esc` | Guardar el rechazo / cancelar |
| `↓` o `Espacio` | Saltar (no estoy seguro); en una ya revisada, sólo avanza |
| `↑` o `Retroceso` | Volver; un veredicto nuevo corrige el anterior |
| `D` | Corregir dibujando (ver abajo); también desde el panel de rechazo |
| `B` | Fondo del sprite: cuadros, oscuro, claro, magenta (el magenta delata halos) |
| `?` | Ayuda |

Todo tiene además un botón grande en pantalla, para uso táctil. Con el dedo (el lápiz queda
para dibujar), los gestos cubren las cuatro acciones:

| Gesto | Acción |
|---|---|
| Deslizar → | Aprobar |
| Deslizar ← | Rechazar: aparecen los motivos grandes abajo; **un toque guarda y pasa a la siguiente**. «Varios motivos o nota…» abre el panel completo; tocar fuera cancela |
| Deslizar ↓ | Saltar |
| Deslizar ↑ | Volver a la anterior |

El sprite sigue al dedo y dice qué va a pasar («Aprobar», «Rechazar»…); al cruzar el umbral
(120 px, o un movimiento rápido) se marca con un borde. Si sueltas antes, regresa a su lugar y
no pasa nada. Así, aprobar es un gesto y rechazar con motivo, un gesto y un toque.

Motivos de sprite: le falta parte del monstruo, incluye fondo, bordes sucios o con halo, el arte
corta la figura, manchas o partes sueltas, recortó otra cosa, mejor el arte completo, eligió mal
entre varias figuras, otro. Un rechazo exige al menos un motivo o una nota.

Para qué sirve cada cosa: las **pills** se cuentan (`--stats` dice qué falla más y eso decide qué
arreglar primero), el **dibujo** dice dónde falló (entrena al segmentador) y la **nota** sirve para
lo que ninguna pill describe. **Regla:** si una nota se repite (por ejemplo, «alas» veinte veces),
se convierte en pill nueva, como «se comió partes finas (alas, cuernos, armas)», en `REASONS` de
`review_server.py`.

**Orden de la cola.** Por defecto se muestran primero los sprites cuyo puntaje del crítico queda más
cerca del umbral de holograma (0.30 hoy): ahí una etiqueta humana cambia más al crítico. Pero ese
«muestreo por incertidumbre» sesga la muestra (Settles 2009; Mussmann y Liang 2018): las etiquetas
se amontonan cerca del umbral viejo y los umbrales y el AUC calculados con ellas no representan a
las 7,000 cartas. Por eso **una de cada cuatro cartas sale al azar**, marcada `sampling: random` en
su veredicto, y `critic_human.py` fija umbrales y mide AUC con ésas. En una simulación con 240
etiquetas, medir con todas daba AUC 0.56, con las 60 al azar 0.73, y el real en la población era
0.83. Las ya revisadas quedan detrás de la posición inicial, alcanzables con `↑`.

**Repeticiones a ciegas (5 %).** Con un solo revisor, el techo de cualquier crítico es qué tan
consistente eres tú. Cerca de una de cada veinte cartas pendientes es una que ya juzgaste, mostrada
de nuevo sin veredicto, sin modelo ni puntaje, y sin poder dibujar. Van a
`research/reviews/sprite-retest.jsonl` (nunca al entrenamiento), y `--stats` reporta el acuerdo
contigo mismo y la kappa de Cohen. Si tu acuerdo es 85 %, ningún crítico va a parecer mejor que eso.

**Dónde se guarda.** En `research/reviews/sprite.jsonl` (y `gen3d.jsonl`): sólo se agrega, nunca se
borra, y la última línea de cada carta es la que vale. Son decisiones humanas y **se versionan en
git**, siguiendo el principio del README de separar los datos regenerables de las decisiones
humanas. Cada línea guarda el modelo y el puntaje del crítico del momento, el motivo, la nota y los
milisegundos que tardó el veredicto.

### Corregir dibujando

Aprobar o rechazar le dice al sistema *qué recorte elegir*; dibujar le dice *dónde se equivocó*.
Con eso se obtiene una máscara corregida, que es lo único con lo que se puede reentrenar BiRefNet.

- `D` (o el botón ✏️) muestra el **arte completo** con lo que está fuera del recorte oscurecido,
  y a la derecha el resultado en vivo. Se dibuja sobre el arte y no sobre el sprite porque el
  sprite está recortado a su caja: las alas que se comió ni siquiera aparecen en él.
- **Verde** (`A`, «Le falta»): marca la parte que el recorte se comió, por ejemplo unas pinceladas
  sobre las alas. **Rojo** (`R`, «Sobra»): cielo, halo, marco. Con lápiz, la goma dibuja en rojo.
- No hace falta pintar todo. `mask_refine.py` convierte unos trazos en la región completa:
  **SAM 2.1** entiende formas («el ala» entera) y **GrabCut** usa sólo OpenCV, funciona siempre y
  va mejor con buen contraste de color. Sólo cambian las regiones que tocan un trazo; lo que está
  bajo el trazo siempre gana.
- `[` `]` grosor (el lápiz además usa la presión) · `Z` deshacer · `X` limpiar · `O` ver u ocultar
  la máscara · `/` nota («se comió las alas») · `Enter` guarda · `Esc` sale sin guardar.
- Las pills también están en el modo dibujo (toque o `1`–`9`). Guardar cuenta como rechazo con
  las pills que marcaste; sólo si no marcaste ninguna se deduce el motivo del color (verde →
  «le falta», rojo → «incluye fondo»), porque un trazo rojo puede ser un halo o un objeto
  equivocado, no fondo.
  Los **trazos** van a la línea del veredicto (versionada, pesa poco) y la **máscara corregida** a
  `data/reviews/masks/<código>.png`. Esa máscara se puede regenerar desde los trazos, y
  `mask_sha1` detecta si un refinador distinto la cambiaría.
- En un holograma se parte del recorte candidato (ver [Hologramas](#hologramas-revisar-el-recorte-que-perdió));
  si no hay candidato, de una máscara vacía, y se dibuja la figura desde cero.
- **Las correcciones se usan de inmediato:** `review_server.py --apply` escribe cada máscara
  corregida como el sprite en uso (modelo `human` en `index.json`); `--apply-corrections` sigue
  funcionando como alias. La recola nunca rehace esas cartas (ver [Reglas del ciclo](#reglas-del-ciclo)).
  Para el crítico sigue contando como rechazo del recorte original, porque la línea del veredicto
  guarda qué modelo lo hizo.
- Conviene dibujar sólo en los rechazos donde el error es claro. Aprobar o rechazar lleva
  segundos; una corrección, de 20 a 40.

**Expectativa realista con partes finas.** Tu ejemplo, unas alas que el recorte se comió, es justo
el punto débil conocido de SAM: con estructuras delgadas da máscaras rotas o con huecos (Ke et al.
2023, HQ-SAM). Y convertir trazos en puntos, como hace `mask_refine.py`, es una aproximación: los
puntos son escasos para formas complejas (SCISSR 2026). Por eso importan tres cosas del diseño:
el trazo siempre gana bajo el pincel, se puede pintar grueso sobre la parte fina, y hay tarea
abierta para probar HQ-SAM contra SAM 2 en las primeras 20 correcciones.

**Instalar SAM 2** (opcional; sin él se usa GrabCut automáticamente). Meta recomienda WSL en
Windows, pero sin la extensión CUDA suele instalar directo. El paquete `sam2` de PyPI **no** es
el oficial: hay que instalar desde el repositorio de Meta.

```powershell
py -3.11 -m venv .venv-sam
.venv-sam/Scripts/python.exe -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
$env:SAM2_BUILD_CUDA = "0"
.venv-sam/Scripts/python.exe -m pip install "git+https://github.com/facebookresearch/sam2" huggingface_hub opencv-python-headless
.venv-sam/Scripts/python.exe review_server.py --refiner sam2 --lan     # descarga sam2.1-hiera-small la primera vez
```

### Tableta y red local

- **Tableta de dibujo conectada a la PC** (tipo Wacom): no hace falta red. Es el navegador de la
  PC; basta `review_server.py`.
- **iPad o tableta Android con lápiz**: la PC hace todo el trabajo (GPU, SAM 2, archivos) y la
  tableta sólo abre la página por la red de casa:

```powershell
.venv-gpu/Scripts/python.exe review_server.py --lan
#   tableta: http://192.168.x.x:8770/?k=CLAVE     <- abrir esto en la tableta
```

  La clave se guarda en `.runtime/review-key` (fuera de git) y se mantiene entre reinicios, así
  que el marcador de la tableta sigue sirviendo. La dirección con `?k=` abre la página directamente
  y deja la clave en una cookie. Sin clave, todo responde 403. Para revocar el acceso de todos los
  aparatos, borra ese archivo. Es HTTP
  simple, pensado sólo para la red de casa: **no abras el puerto en el router**.

  Si la tableta no conecta, casi siempre es el firewall de Windows. Una vez, en PowerShell como
  administrador:

```powershell
New-NetFirewallRule -DisplayName "Yu-Gi-Oh AR revision" -Direction Inbound -Protocol TCP -LocalPort 8770 -Action Allow -Profile Private
```

  La red Wi-Fi debe estar marcada como **privada** en Windows.

**En iPad (tu caso):**

- **Agrégalo a la pantalla de inicio.** Abre la dirección con `?k=` en Safari → Compartir →
  «Agregar a pantalla de inicio». Se abre a pantalla completa, sin barra de Safari y, sobre todo,
  **sin el gesto de atrás desde el borde**, que en Safari te sacaría del revisor a media sesión.
  La app de pantalla de inicio guarda sus cookies aparte de Safari; por eso la dirección conserva
  la clave y la página se sirve con ella directamente, sin redirigir.
- Aun en Safari normal, los gestos que empiezan a menos de 28 px del borde se ignoran, para no
  pelear con el de atrás.
- **Apple Pencil:** presión y rechazo de palma funcionan; no tiene goma que la web pueda leer (el
  doble toque del Pencil 2 y el apretón del Pro no llegan a Safari), así que para marcar en rojo
  se usa el botón «Sobra» o la tecla `R` si tienes teclado.
- **Sin vibración:** Safari no la soporta; la señal es visual (color y borde al cruzar el umbral).
- Mantener el dedo sobre el sprite no inicia el arrastre de imágenes de iPadOS ni el menú de
  «Guardar imagen».
- Con Magic Keyboard funcionan todos los atajos de teclado.

Todo esto se probó en simulación, no en un iPad real (ver [Qué está probado](#qué-está-probado)).

### Conjunto de control: ¿mejoró de verdad?

Mirar las mismas cartas que ya revisaste engaña: las aprobadas quedan fijas y las rechazadas se
rehacen, así que siempre *parece* que mejora. Para medir de verdad:

```powershell
.venv-gpu/Scripts/python.exe review_server.py --control-new 150    # una sola vez: congela 150 cartas al azar
.venv-gpu/Scripts/python.exe review_server.py --control antes       # revisarlas a ciegas ANTES de reentrenar
#   ... reentrenar, regenerar ...
.venv-gpu/Scripts/python.exe review_server.py --control despues1    # las mismas 150, a ciegas, DESPUÉS
.venv-gpu/Scripts/python.exe review_server.py --stats                # control_rounds: aprobación por ronda
```

- Las cartas de control salen de la cola normal y nunca entran al entrenamiento.
- En una ronda de control no se ven el crítico, el modelo ni los veredictos de otras rondas, y
  no se puede dibujar: sólo se juzga.
- Como son sólo 150, el margen de cada ronda es de ±8 puntos alrededor de 60 % (`--stats` da el
  intervalo de Wilson al 95 %). Pero como son **las mismas cartas**, `--stats` también hace la
  comparación **pareada**: cuenta las que pasaron de rechazo a aprobado y al revés, con la prueba
  exacta de McNemar (`control_paired`). Es mucho más sensible: en una prueba sintética, 12 cartas
  que mejoraron contra 1 que empeoró dan p = 0.003, aunque los intervalos de las dos rondas casi se
  tocan. `reading` lo resume: «mejora clara», «empeora» o «sin diferencia demostrable».
- Para que la regeneración llegue a las cartas de control hay que usar
  `critic_human.py --requeue-all` (o reentrenar BiRefNet), porque `--requeue` sólo rehace las
  rechazadas en la cola normal.

### Hologramas: revisar el recorte que perdió

Revisar el holograma en sí aporta poco: sólo dice que el respaldo se ve aceptable, y no juzga
ninguna máscara. Lo valioso es el recorte al que el crítico le dijo que no. Si una persona lo
aprueba, es justo la etiqueta que el crítico necesita para aprender dónde es demasiado estricto.

- `build()` ahora guarda ese recorte perdedor en `data/auto-sprites/candidates/` (con su modelo y
  puntaje en `candidates/index.json`). Para los hologramas ya generados:
  `research/hologram_candidates.py` repite la misma competencia (BiRefNet, BiRefNet volteado,
  isnet-anime, con el crítico actual). Son unos 1,000 hologramas, del orden de 10 a 15 min.
- El revisor muestra el candidato en lugar del holograma (título «Recorte que perdió contra el
  holograma»). **Aprobar** lo pone en uso con `--apply`, y es una etiqueta positiva para el
  crítico. **Rechazar** confirma el holograma. **Dibujar** parte del candidato.
- `--order hologram` muestra sólo estas cartas.
- En las rondas de control se juzga lo que está en uso, es decir, el holograma, no el candidato.

### Reglas del ciclo

Revisadas para que las piezas no se contradigan:

- **Un veredicto vale para el sprite exacto que juzgó.** Cada línea guarda una huella (`fp`: estado,
  modelo, puntaje, corrección). Si `build()` rehace una carta, el veredicto viejo deja de valer y la
  carta vuelve a la cola, sin tener que buscarla. Excepción: si el sprite en uso es justo lo que
  el veredicto puso ahí (su corrección o el candidato que aprobó), sigue contando como revisada.
- **El crítico aprende de cada máscara juzgada**, no sólo de la última por carta: si una carta se
  revisó, se rehízo y se volvió a revisar, dan dos etiquetas, una por máscara.
- **Fijadas (la recola no las toca):** correcciones a mano, candidatos promovidos y recortes aprobados
  tal como están. Un **holograma aprobado como respaldo no se fija**: `--requeue-all` lo rehace,
  por si el crítico nuevo le encuentra un buen recorte.
- **Un rechazo posterior despega:** si rechazas un sprite fijado (una corrección o una promoción
  que luego te parece mal), la recola sí lo rehace. Siempre gana el último veredicto sobre el
  sprite en uso.
- `--requeue` rehace sólo los recortes rechazados que están en uso; los candidatos rechazados
  quedan como holograma. Funciona aunque todavía no haya etiquetas suficientes para ajustar un
  crítico.
- **Lo rechazado no vuelve:** `build()` y `hologram_candidates.py` nunca vuelven a ofrecer, para
  un arte, un recorte que una persona rechazó. Los modelos son deterministas: el mismo modelo daría
  la misma máscara. Si los tres se rechazaron, la carta queda en holograma sin candidato
  (`all_rejected` en `index.json`); ahí la única salida es dibujarla. Aprobar después el mismo
  sprite retira el rechazo.
- **El visor se entera solo:** tras `--apply` o `build`, el servidor de la cámara vuelve a leer qué
  cartas tienen sprite automático, descarta los sprites viejos de su caché y le da a la página una
  URL nueva (`?v=`), así que no hace falta reiniciarlo. Excepción: la vista de duelo (`/duelo`)
  guarda sus recortes por carga de página; hay que recargarla (F5).

**Limitaciones conocidas, a propósito o pendientes:**

- Tras adoptar un crítico, los puntajes de `index.json` siguen siendo los del crítico anterior
  hasta `--requeue-all`, así que el orden «indeciso» de la cola es aproximado mientras tanto.
- `--stats` mezcla veredictos sobre versiones distintas de un mismo sprite. Para medir mejora, la
  referencia es el conjunto de control, no `--stats`.

### Qué mejora cada cosa

| Qué se reentrena | Con qué | Qué cambia | Qué esperar |
|---|---|---|---|
| **Crítico** (`critic_human.py`) | Aprobar/rechazar | Qué candidato se elige y cuándo usar holograma | Menos sprites malos colados. No crea recortes mejores: si los tres candidatos de una carta son malos, sigue igual. Se nota en la primera o segunda ronda. |
| **Un candidato mejor: ToonOut** (hecho) | Nada: ya está entrenado | Los recortes mismos, en las 7,000 cartas | La mejora grande más barata (ver abajo). |
| **BiRefNet** (tarea abierta) | Máscaras corregidas + recortes aprobados | Los recortes mismos, en las 7,000 cartas | La mejora de fondo, pero necesita varios cientos de correcciones, y hay que comprobar con `auto_cutout.py eval` que no empeore contra TDOANE. **No cabe tal cual en la 4070** (ver abajo). |

**ToonOut ya compite.** Es BiRefNet afinado con 1,228 imágenes anime (Muratori y Seytre 2025, MIT):
sube la precisión por píxel de 95.3 % a 99.5 %. En su categoría de acción, la más parecida a las
ilustraciones de Yu-Gi-Oh!, BiRefNet sacaba 76.8 % y ToonOut 99.0 %. `build()` lo prueba en **todas**
las cartas (no sólo en los reintentos) y gana el que el crítico prefiera; también entra en
`hologram_candidates.py` y en `critic_human.py`. Hace falta descargar la exportación ONNX de la
comunidad, `sprited/birefnet-toonout-onnx` en HuggingFace: el archivo `birefnet-toonout.onnx` va a
`downloads/cutout-models/`. Si no está, `build()` avisa y sigue sin él. Las cartas ya generadas
sólo lo aprovechan al rehacerse (`--requeue-all`, que respeta todo lo fijado).

**Afinar BiRefNet en la 4070 no cabe tal cual.** Según su repositorio, entrenar en FP16 pide 22.5 GB
o más; la inferencia a 1024, unos 3.45 GB. Opciones: la variante lite, menos resolución, gradient
checkpointing con lote 1, o rentar una GPU grande unas horas (el entrenamiento es de una vez). ToonOut
muestra la escala que funciona: unas 1,200 imágenes. Y su conjunto de datos es CC-BY 4.0: mezclarlo
con tus correcciones reduce el riesgo de sobreajustar a pocas cartas.

**Revisar también las cartas que ya tienen close-up de TDOANE** (sus recortes automáticos, aunque
en la mesa se use el sprite hecho a mano): son las únicas donde hay a la vez veredicto humano e
IoU. Con 100 a 200 se sabe si «IoU ≥ 0.8 = bueno», el criterio del crítico original, coincide con
lo que a ti te parece bueno; TDOANE repinta partes ocultas y el IoU puede castigar recortes
correctos (tarea abierta).

### Recalibrar el crítico (`research/critic_human.py`)

```powershell
.venv-gpu/Scripts/python.exe research/critic_human.py              # evalúa el crítico actual y ajusta un candidato
.venv-gpu/Scripts/python.exe research/critic_human.py --adopt      # lo adopta sólo si gana (AUC con validación cruzada)
.venv-gpu/Scripts/python.exe research/critic_human.py --requeue    # saca de index.json las cartas rechazadas
.venv-gpu/Scripts/python.exe research/auto_cutout.py build         # rehace exactamente lo que se sacó
```

- Cuentan los recortes en uso y los candidatos de holograma. Un veredicto sobre un holograma juzga
  el respaldo, no una máscara.
- **Dos candidatos, el mejor gana:** uno ajustado sólo con tus veredictos y otro con tus veredictos
  **más** los pares de TDOANE con los que aprendió el crítico actual, para no tirar lo que ya sabía.
  Ambos se juzgan igual, con validación cruzada sobre tus veredictos; se ofrece el mejor, y sólo
  reemplaza al actual si también le gana. `--source human|combined|best` (por defecto `best`) y
  `--human-share` (por defecto 0.5: tus veredictos pesan la mitad del total, sean cuantos sean).
  Los rasgos de TDOANE se calculan una vez (la misma selección que `auto_cutout.py calibrate`, unos
  minutos en GPU) y quedan en `data/reviews/tdoane-features.npz`.
- Recalcula las máscaras con los mismos modelos que usó `build()` para cada carta (birefnet,
  birefnet-flip o isnet-anime), así que necesita la GPU.
- Informe en `research/qa/critic-human.json`: el AUC del crítico actual contra humanos, la
  aprobación por franja de puntaje y cuántos sprites conservó que la gente rechazó. También el
  AUC del candidato con validación cruzada y sus umbrales: holograma por debajo del 30 % de
  aprobación local, reintento por debajo del 50 %.
- `--adopt` guarda el crítico anterior en `auto_cutout_critic.prev.json`.
- `--requeue-all`, tras adoptar, rehace también todas las cartas sin revisar, porque sus puntajes
  vienen del crítico viejo. Tarda aproximadamente 7,000 × 0.45 s, alrededor de una hora en la 4070.
- Pide al menos 150 recortes con ambos veredictos para ajustar un candidato (`--min`).
- **Umbrales y AUC con las cartas al azar:** el candidato se ajusta con todos los veredictos, pero
  los umbrales y el AUC (incluido el del crítico actual, para compararlos) se calculan sólo con los
  tomados al azar, en cuanto haya 40 (`--min-random`). Mientras tanto usa todos, y el informe
  (`evaluated_on`) avisa que están sesgados.

**El ciclo, una ronda:** revisar unos 300 → `--stats` → `critic_human.py` → si gana, `--adopt`
y `--requeue` → `build` → revisar lo regenerado. Repetir mientras el AUC suba. Cuando se aplane,
las mejoras ya no están en el crítico sino en los candidatos (ver [Tareas abiertas](#tareas-abiertas)).

## Generación automática de modelos 3D

Detalle, candidatos, licencias e instalación en [GENERACION_3D.md](GENERACION_3D.md).

**Tubería prevista** (se extiende la de sprites):

1. El recorte aprobado de BiRefNet.
2. Completar la figura cuando el arte la corta (motivo «El arte corta la figura»): un modelo de
   imagen la dibuja de cuerpo entero y, si ayuda, en varias vistas. Todavía no se ha elegido cuál.
3. Imagen → malla con textura: TripoSR, Stable Fast 3D o Hunyuan3D-2mini. TRELLIS queda fuera
   porque pide ≥16 GB y sólo está probado en Linux.
4. Rig automático (por ejemplo, UniRig) → glTF → reducción de polígonos para AR.
5. Crítico 3D: renders del modelo contra el arte, más los veredictos de `review_server.py --kind gen3d`.
6. Caché por `artwork_id`, igual que `data/auto-sprites`.

**Escala: por demanda, no las 7,000.** A 30–60 s por modelo en la 4070, todo el catálogo son de 60 a
120 horas de GPU, casi todas para cartas que nadie juega. Mejor generar primero los monstruos de los
mazos que se usan (la lista de mazo, tarea abierta) y el resto cuando aparezcan, con caché.

**Lo más nuevo no cabe en 12 GB.** TRELLIS.2 (Microsoft, MIT, con materiales PBR) pide al menos 16 GB
a 512³. SAM 3D Objects (Meta) sería ideal porque está pensado para objetos ocluidos y recortados,
como las ilustraciones, pero exige Linux y al menos 32 GB. Ambos quedan para una tanda en la nube
con las cartas más jugadas, comparada en el mismo banco.

**Animación: procedural primero, rig después.** UniRig predice esqueleto y pesos también para no
humanoides, pero un dragón o una máquina no tienen biblioteca de movimientos a la cual adaptarse.
CharacterGen y StdGEN llevan una ilustración a pose A con varias vistas, lo que ayuda al rig, pero
sólo para personajes humanoides. Por eso: primero animaciones de cuerpo entero que sirven para
cualquier modelo sin rig (aparecer, flotar, embestir al atacar, desintegrarse); el rig y las
animaciones por hueso, para las cartas clave.

**Banco de pruebas:** `research/gen3d_bench.py`. Mide tiempo por modelo, pico de VRAM, falta de
memoria, triángulos, textura y peso, y deja una hoja HTML comparativa.

### Fase posterior: Magias de Campo

La idea viene de `DUELO_REMOTO.md` (28/09/2026): con una Magia de Campo activa, su escenario tiñe
o envuelve el tablero de ese jugador. Hay 334 en el registro, 329 reconocibles con el catálogo
completo. Va **después** de la pose 3D con Three.js, no antes, y es un buen primer caso para
validarla: el suelo tiene que quedar pegado al tapete aunque se mueva la cámara.

Se separa en tres piezas, porque sólo la última depende del motor gráfico:

1. **Qué campo está activo y de quién** (sin motor). El motor de duelo ya lleva la Zona de Campo
   de cada jugador (`players[i]['field']`) y ya distingue «activada» de «colocada boca abajo»
   cuando una carta aparece en una zona de Magia. Falta derivar de ese estado un «ambiente» por
   jugador y avisar a la vista cuando cambia. Reglas del juego que respeta: una Magia de Campo
   **colocada boca abajo no tiene efecto**, así que no cambia el ambiente hasta que se activa;
   cada jugador tiene la suya, así que cada lado del tablero puede tener un ambiente distinto; y
   un campo nuevo del mismo jugador reemplaza al anterior.
2. **El suelo** (sin pose 3D). El arte o un derivado se proyecta sobre la mitad del tapete de ese
   jugador, debajo de las cartas. El tapete es un plano: basta la homografía actual y el WebGL que
   ya dibuja los sprites. Probablemente funcione mejor una versión difuminada, o sólo sus colores
   dominantes como tinte, que el arte literal: el arte de un campo suele ser un paisaje en
   perspectiva, y estirado sobre el tapete se ve raro. Se decide probando con unas 10 cartas.
3. **El ambiente** (con pose 3D y motor): cielo o domo con el arte, niebla, partículas y luz que
   tiña a los monstruos 3D. Sin pose, un cielo alrededor del tablero no se vería anclado a la mesa.
   Para la luz existe DiffusionLight (CVPR 2024), que estima un mapa de entorno HDR desde una sola
   imagen, incluso pinturas: se puede precalcular uno por cada una de las 329 cartas y usarlo
   para iluminar a los monstruos.

Las piezas 1 y 2 no se tiran al pasar al motor: la lógica pasa tal cual, y en Three.js el suelo es
casi el mismo código.

**Las que no se reconocen.** Hay varios casos distintos, y ninguno debería dejar el tablero en un
estado raro:

| Caso | Qué hacer |
|---|---|
| **Boca abajo** en la Zona de Campo | Nada: por reglas no tiene efecto. `card_backs.py` ya detecta reversos en las zonas. |
| **Cara arriba pero no identificada** (reflejo, mano encima, fuera de catálogo, proxy) | **La zona lo dice todo:** en la Zona de Campo sólo puede haber una Magia de Campo. Se activa un ambiente genérico con los colores tomados **de la propia carta vista por la cámara**: con sus esquinas ya se puede rectificar el recuadro del arte. No hace falta saber cuál es. |
| **Las 5 que no están en el catálogo** del reconocedor (casi todas de OCG o del anime, según `DUELO_REMOTO.md`) | El mismo ambiente genérico de la fila anterior. Si alguna importa, se agrega su arte al catálogo como cualquier otra carta. |
| **Reconocida un momento y luego perdida** (tapada, reflejo) | Histéresis: el ambiente se mantiene mientras la pista siga en la zona y sólo se apaga tras unos segundos con la zona vacía confirmada. Sin esto, el tablero parpadea. |
| **Reconocida mal** (otro campo) | Cambiar de ambiente específico sólo con identidad **verificada** (arte o passcode, que ya existen); mientras tanto, el genérico. Y un control para corregir a mano, como la corrección de acciones que ya tiene el duelo. |

Así, reconocer la carta mejora el ambiente (el suyo exacto en lugar del genérico), pero no es
requisito para que haya uno.

**Preguntas abiertas:** ¿el ambiente cubre sólo el lado de su dueño o todo el tablero? (Las reglas
dicen «su lado», pero visualmente puede quedar mejor que el último campo activado domine.) ¿Qué pasa
en duelo remoto, donde el tablero rival no tiene cámara? ¿Hay ambientes hechos a mano para los campos
más jugados, y el automático para el resto?

## Pasos en casa

Orden recomendado. Cada fase deja un informe en `research/qa/`.

**0. Aplicar los cambios** (5 min)
```powershell
git apply yugioh-ar-plan-3d.patch   # o copiar los archivos a mano
git add -A; git commit -m "Revisión por teclado, crítico con veredictos humanos, banco imagen→3D y plan"
```

### Prueba rápida antes de la sesión larga

Nada se probó todavía en tu hardware (tableta, SAM 2, navegador real, GPU). Diez minutos antes de
revisar 300 cartas, para que si algo falla sea aquí y no a la mitad:

1. `review_server.py --lan`; abrir la URL en el iPad y **agregarla a la pantalla de inicio**.
   ¿Carga? ¿Responden los botones? ¿El sprite sigue al dedo en las cuatro direcciones? Desliza
   desde cerca del borde izquierdo: no debe salirse de la página.
2. Corregir una carta dibujando con el lápiz: ¿se ve el trazo?, ¿funciona la goma?, ¿se ignora la
   palma?, ¿llega el resultado a la derecha?
3. `review_server.py --apply` con el visor de la cámara corriendo: la carta corregida debe cambiar
   sola en la mesa en uno o dos segundos, sin reiniciar.
4. `python qa_auto_sprite_reload.py`: debe decir `"passed": true`.
5. También `python qa_sprite_cache.py`. En el entorno remoto falló igual antes y después de estos
   cambios, porque sus píxeles de referencia difieren en ±3 con otra versión de OpenCV. En tu PC
   debería pasar; si no, es ese problema de referencia y no la recarga nueva.

### Qué correr en paralelo

Mientras revisas, la máquina puede ir adelantando:

| Trabajo | En paralelo con la revisión | Nota |
|---|---|---|
| Instalar el banco 3D (TripoSR, SF3D, Hunyuan) | Sí | Compila extensiones y descarga pesos: ideal de fondo |
| Correr el banco con TripoSR, SF3D o Hunyuan (sólo forma) | Sí | ~6 GB de GPU + 1–2 GB de SAM 2 caben en 12 GB |
| Correr Hunyuan con textura | No | Pide ~16 GB con descarga a CPU; hazlo cuando no revises |
| `hologram_candidates.py` | Antes, no en paralelo | La revisión de hologramas necesita su resultado |
| `critic_human.py` y `build` | Entre rondas | Dependen de lo que acabas de revisar |
| Calibrar la cámara (ChArUco) | En ratos sueltos | No depende de la revisión; desbloquea la pose 3D |

**1. Control y primera ronda de revisión de sprites** (45–60 min)
- `review_server.py --control-new 150`, y luego `--control antes`: 150 veredictos a ciegas.
  Hazlo **antes** de agregar ToonOut, para que el control mida también su efecto.
- Opcional: SAM 2 en `.venv-sam` y `--lan` para la tableta (ver [Tableta y red local](#tableta-y-red-local)).
- `review_server.py`, unos 300 veredictos, dibujando en los rechazos con un error claro. El
  revisor muestra el ritmo en la barra superior.
- `research/hologram_candidates.py` (10–15 min, GPU) y luego `review_server.py --order hologram`:
  aprobar los recortes que se salvan.
- `review_server.py --apply` para usar ya en la mesa los sprites corregidos y los candidatos
  aprobados. El visor los toma solo; sólo `/duelo` necesita recargar la página.
- Criterio: ¿lo pondría así sobre la mesa? Si hay duda, `↓`.
- `review_server.py --stats` y anotar la aprobación por franja del crítico.

**1b. ToonOut** (30 min más ~1 h de GPU)
- Descargar `birefnet-toonout.onnx` a `downloads/cutout-models/` (ver [Qué mejora cada cosa](#qué-mejora-cada-cosa)).
- `auto_cutout.py eval`: IoU contra TDOANE de todos los modelos, ToonOut incluido.
- `critic_human.py --requeue-all` y `auto_cutout.py build`: rehace con ToonOut todo lo no fijado.
- `--control despues-toonout`: la comparación pareada dice si mejoró de verdad.

**2. Recalibrar** (10–20 min, GPU)
- `critic_human.py`: compara el candidato sólo-humanos con el combinado con TDOANE. Si
  `beats_current`, adoptar y hacer `--requeue`; luego `auto_cutout.py build`, que ya no repite
  recortes rechazados.
- Segunda ronda de revisión sobre lo regenerado.
- Éxito: `--control despues1` aprueba claramente más que `antes`. Además, sube la aprobación en
  la franja 0.3–0.8 y baja `kept_but_rejected`.

**3. Banco 3D** (1–3 h, sobre todo instalación)
- Instalar TripoSR primero (el más sencillo) según `GENERACION_3D.md`.
- `gen3d_bench.py run --sprites 6 --approved`: sólo recortes que aprobaste.
- Luego SF3D y Hunyuan3D-2mini, con `--only`.
- `review_server.py --kind gen3d` para juzgar los modelos por teclado.

**4. Pose 3D y primer monstruo en Three.js** (una tarde)
- Decidir la cámara del 3D: una segunda cámara en ángulo, o inclinar la actual (ver
  [Conceptos](#conceptos-homografía-solvepnp-y-pose)). Desde arriba la pose es ambigua y el
  monstruo se ve sólo por encima.
- Calibrar cada cámara con ChArUco; guardar los intrínsecos por cámara.
- `solvePnPGeneric` con IPPE sobre los ArUco del tapete → pose de la mesa, eligiendo la solución
  coherente con el cuadro anterior; esquinas de cada carta → posición y giro sobre el plano.
- Enviar la pose junto a las pistas actuales y dibujar un glTF del banco sobre la carta en `/duel`.
- Éxito: el modelo no se desliza al mover la carta y no tiembla con la cámara quieta.

**5. Después**
- Completar la figura, rig y animación de invocación.
- Magias de Campo: primero el estado y el suelo, luego el ambiente 3D (ver
  [Fase posterior: Magias de Campo](#fase-posterior-magias-de-campo)).
- Decidir Unity según lo que Three.js no alcance.

## Tareas abiertas

1. **Afinar BiRefNet** con las máscaras corregidas (`data/reviews/masks/`) y los recortes aprobados
   como pseudo-verdad, cuando haya varios cientos. Los trazos también sirven de supervisión
   parcial, con pérdida sólo en los píxeles marcados. Medir con `auto_cutout.py eval` contra TDOANE
   y con una ronda de control. Exportar el resultado a ONNX para que `build()` no cambie.
2. **Revisar los recortes automáticos de cartas con close-up de TDOANE** y comparar veredicto e
   IoU: ¿el umbral 0.8 del crítico original coincide con el juicio humano? Hace falta una opción
   `--order tdoane` en el revisor, que genere esos recortes al vuelo.
3. **Crítico 3D**: rasgos de renders del modelo (silueta frontal contra la máscara del recorte,
   simetría, peso) y veredictos de `gen3d.jsonl`.
4. **Elegir el modelo para completar figuras** y medir si mejora el 3D en las cartas marcadas.
5. **Artes alternativos de cartas con sprite TDOANE:** `targets()` salta la carta entera si
   cualquiera de sus artes tiene sprite hecho a mano, así que sus otros artes no reciben sprite
   automático. Decidir si se cubren.
6. **La vista de duelo no recarga sprites sola:** `web/duel.js` guarda `/cutout/<ref>` por carga
   de página. Si molesta recargar `/duelo` tras `--apply`, darle la misma versión `?v=` que ya
   usa la vista de cámara.
7. **Fusionar el orden «indeciso» con el crítico nuevo:** hasta `--requeue-all` la cola se ordena
   con puntajes del crítico anterior.

8. **Probar HQ-SAM** contra SAM 2 en las primeras 20 correcciones de partes finas (alas, cuernos,
   armas), como refinador más de `mask_refine.py`.
9. **Lista de mazo por duelo.** TCG-AR pasa de 85 a 96 aciertos de cada 100 al limitar el
   reconocimiento a los ~60 cartas de los mazos declarados. La idea de «piloto» del repositorio va
   en esa dirección; exponerla por duelo ayudaría también con las Magias de Campo.
10. **3D por demanda, no para todo el catálogo:** ver [Generación automática](#generación-automática-de-modelos-3d).

Hechas desde la primera versión de este plan: `build()` respeta los rechazos, el crítico combina
TDOANE con los veredictos, el visor recarga los sprites automáticos sin reiniciar, ToonOut compite
como candidato, la cola mezcla un 25 % al azar, hay repeticiones a ciegas y el control se compara
en pareado.

## Referencias

Revisión contra literatura y proyectos parecidos, 29/09/2026:

- **TCG-AR** (Cioppa et al., Universidad de Lieja, 2026; arXiv 2607.02090;
  github.com/ULiege-VIULab/tcg-ar): el proyecto publicado más parecido, para Pokémon con sprites
  2D. Reconocimiento por similitud con una base de referencia; 85 % de acierto contra la base
  completa y 96 % con los mazos declarados; cenital para reconocer y cámaras laterales para mostrar;
  tres cámaras HD a 30 fps en una GPU de consumo. Su paso siguiente declarado es el 3D.
- **Muestreo por incertidumbre y su sesgo:** Settles 2009 (reseña de aprendizaje activo);
  Mussmann y Liang 2018 (arXiv 1812.01815); estudio empírico en arXiv 1909.09389.
- **ToonOut** (Muratori y Seytre 2025, arXiv 2509.06839; pesos MIT en HuggingFace joelseytre/toonout;
  ONNX de la comunidad en sprited/birefnet-toonout-onnx; datos CC-BY 4.0).
- **BiRefNet** (Zheng et al. 2024): guía de afinado y requisitos de memoria en su repositorio.
- **HQ-SAM** (Ke et al. 2023, arXiv 2306.01567): SAM con bordes finos; **SCISSR** (2026, arXiv
  2603.18544): trazos como indicación para SAM 2.
- **IPPE** (Collins y Bartoli 2014, IJCV): pose de planos y su ambigüedad; en OpenCV como
  `SOLVEPNP_IPPE` con `solvePnPGeneric`.
- **Imagen a 3D:** TRELLIS.2 (Microsoft 2025, arXiv 2512.14692); SAM 3D Objects (Meta 2025, arXiv
  2511.16624); CharacterGen (arXiv 2402.17214) y StdGEN (arXiv 2411.05738) para humanoides.
- **Rig:** UniRig (Zhang et al., SIGGRAPH 2025, arXiv 2504.12451).
- **Luz desde una imagen:** DiffusionLight (Phongthawee et al., CVPR 2024).

## Qué está probado

- `review_server.py`: la cola en los tres órdenes, el token, los rechazos sin motivo rechazados,
  motivos desconocidos filtrados, rutas con `..` bloqueadas, `--stats` y el modo `gen3d`. Probado
  con un índice falso de 5 cartas.
- `web/review.html`: el flujo completo por teclado probado en jsdom contra el servidor real:
  aprobar, rechazar con motivos y nota, que los números no marquen motivos mientras se escribe,
  volver, saltar sin sobrescribir, fin de la cola, ayuda y fondos. También el modo dibujo con
  eventos de lápiz simulados: trazo, palma ignorada, goma en rojo, deshacer, nota y guardar. Y
  los botones táctiles y el deslizamiento. **No** se probó en un navegador real, ni con una tableta
  o lápiz reales, ni el dibujo en canvas (jsdom no dibuja).
- `mask_refine.py` (GrabCut): con una imagen sintética en la que el recorte se comió un ala y dejó
  una mancha de cielo, un trazo verde y uno rojo dejan IoU 1.0 contra la verdad, en 0.4 s en CPU.
  **SAM 2 no se probó**: aquí no hay torch ni acceso a sus pesos.
- Servidor: reconstrucción exacta de la máscara desde el sprite recortado (IoU 1.0), refinado,
  guardado de la corrección, conjunto de control (fuera de la cola, a ciegas, sin dibujo) y
  clave de acceso en `--lan` (403 sin clave, cookie tras la primera visita, clave persistente entre
  reinicios).
- Ciclo completo con datos sintéticos (40 artes, 8 hologramas con candidato): aprobar, rechazar
  y corregir candidatos y recortes; `--apply` (2 corregidos, 1 holograma promovido);
  `critic_human.py` con máscaras falsas (28 etiquetas, 3 de candidatos); `--requeue` (sólo
  rechazos vigentes); regeneración simulada (los rehechos vuelven a la cola, lo aprobado sigue
  revisado); un rechazo posterior despega un promovido; y `--requeue-all` rehace el holograma
  aprobado como respaldo y respeta lo fijado.
- `build()` con modelos simulados: un arte con BiRefNet rechazado sale con otro recorte, uno con
  los tres rechazados sale en holograma sin candidato, y una aprobación posterior del mismo sprite
  retira el rechazo. `hologram_candidates.py` sólo compila; necesita los modelos ONNX.
- Crítico combinado con datos sintéticos (220 veredictos, 600 pares TDOANE): compara las dos
  opciones con validación cruzada, elige la mejor y respeta `--source` y `--human-share`. **No** se
  probó con rasgos reales de TDOANE.
- Gestos (jsdom contra el servidor): arrastre corto que regresa sin actuar, largo y rápido que
  aprueban, abajo salta, arriba vuelve, borde y lápiz ignorados, rechazo rápido de un toque,
  cancelar tocando fuera, «Varios motivos…» al panel completo, teclado abre el panel completo. La
  dirección con `?k=` se sirve sin redirigir y con cookie. **No** se probó en un iPad real: el
  gesto de atrás de Safari y el arrastre de imágenes sólo se pueden comprobar ahí.
- ToonOut en `build()` con modelos simulados: gana cuando el crítico lo prefiere, se descarta si
  lo rechazaste para ese arte, y sin su archivo `build()` avisa y sigue. **No** se corrió el ONNX
  real; el preprocesamiento sigue la ficha de la exportación (ImageNet, salida ya en 0..1).
- Cola: patrón «tres indecisos, uno al azar», sin duplicados, `sampling` guardado en cada
  veredicto; repeticiones a ciegas (5 % de lo pendiente, sin modelo ni dibujo, a su propio archivo,
  omitidas si se saltan); `--stats` con intervalo de Wilson, McNemar exacto (12 contra 1 → p = 0.0034)
  y acuerdo contigo mismo con kappa.
- `critic_human.py` con datos simulados sesgados: umbrales y AUC con la submuestra al azar (0.73)
  frente a todos (0.56), con el real en 0.83.
- Recarga en el visor: `qa_auto_sprite_reload.py` (nueva) pasa. Cubre caché del overlay, mapa de
  sprites del reconocedor y URL versionada, sobre una carpeta temporal y con los módulos reales
  (`ar_overlay`, `vision_onnx`, `camera_viewer`). **No** se probó con la cámara ni con el navegador.
- `critic_human.py`: la tubería completa con máscaras falsas (recolección de veredictos, rasgos,
  validación cruzada, adopción condicionada y recola) y el ajuste logístico con datos sintéticos
  separables (AUC 0.94). **No** se probó con BiRefNet ni con veredictos reales.
- `gen3d_bench.py`: con un generador falso. **Ningún** generador real.
