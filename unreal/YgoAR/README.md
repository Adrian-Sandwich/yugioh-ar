# YgoAR: HUD y efectos 3D en Unreal Engine 5

Otro cliente del mismo estado que dibuja `/duelo`. El laboratorio (`camera_viewer.py`) sigue siendo
el único dueño de la cámara; Unreal sólo lee lo que el labo ya sirve y dibuja encima del video:

| Ruta del labo | Qué toma Unreal |
|---|---|
| `/snapshot` | el cuadro más nuevo (JPEG) y sus pistas en la cabecera `X-Tracks` |
| `/scene` | la cámara sobre la mesa: intrínsecos y pose en mm (`scene3d.py`) y las zonas en mm |
| `/duel` | LP, turno, fase, cartas en el campo y las últimas jugadas |
| `/card-info?id=` | tipo y nombre de la carta |
| `/cutout/<ref>` | el sprite recortado del monstruo |

Todo está en C++ y en un script de Python del editor, para que viva en git como texto. `Content/`
se genera con `Scripts/make_assets.py` y no se versiona.

## Piezas

- `YgoLab`: cliente HTTP del labo; decodifica el JPEG en otro hilo y lo sube a una textura.
- `YgoTableView`: cámara virtual con la pose y el campo de visión de la real, y el video en un plano
  a 50 m que llena su vista. Sin exposición automática ni curva fílmica: el video sale como lo filmó
  la cámara. El bloom sólo toma luz por encima de 1, que es la de los efectos.
- `YgoStage`: detecta llegadas (mismas reglas que `noticeArrivals` en `web/duel.js`) y los ataques, destrucciones y LP del duelo (`stageEvents`), pone a cada
  carta su figura (monstruo, magia, trampa o el escudo del Milenio de una carta boca abajo) y lanza sus efectos.
- El escudo del Milenio (en `YgoStage`) es un sólido, no una imagen: una malla con sus dos caras y su
  canto, levantada desde el relieve de sus dos dibujos (`tools/make_shield_relief.py` escribe
  `web/fx/shield-millennium-*-relief.png`: normal, metal y altura). Su material, `M_FxMetal`, calcula la
  luz él mismo (la escena no tiene luces, para que el video salga como se filmó): una luz principal y un
  cuarto inventado que el oro refleja al girar. Entra cayendo y girando rápido, y se asienta en una vuelta
  cada 6 s con un leve cabeceo.
- `YgoSummonFx`: círculo mágico, onda expansiva, chispas, pilar de luz y motas. Son los mismos tiempos
  que la versión 2D, alargados a 2.2 s.
- `YgoFx`: activación de magia y de trampa, carta boca abajo e impacto de un ataque.
- `YgoShatterFx`: la figura de un monstruo destruido se rompe en pedazos que caen y se queman.
- `YgoFeel`: cuánto pesa cada momento, en un solo lugar: tres pesos de golpe, sacudida que se acumula y
  decae, un instante congelado que nunca detiene el video, y los sonidos de `Audio/` (Kenney, CC0).
- `YgoParticles`: partículas en una malla instanciada. Niagara se edita sólo en el editor y se guarda
  binario, así que aquí no sirve.
- `YgoHud` y `YgoPlate`: HUD en Slate. Los LP van en cartuchos y las fases en una fila de fichas; todo
  es la misma placa de lapislázuli y oro (`M_UiPlate`), los materiales del escudo del Milenio. Cuando el
  notario necesita una decisión se abre un panel y la zona en duda se marca sobre la mesa; lo que no
  tiene respuesta queda como aviso hasta que se pide. La tipografía es Cinzel (`Fonts/`, licencia OFL).

Las decisiones van al labo igual que desde `/duelo`:

| Tecla | Hace |
|---|---|
| 1-9 | responde el panel |
| Espacio | siguiente fase |
| Z | deshace la última jugada, si sigue en pantalla |
| Tab | pasa al siguiente aviso |
| Esc | deja la pregunta para luego |
| G | muestra las zonas del tablero sobre la mesa |
| M | apaga o enciende el sonido |
| C | modo tranquilo: sin sacudidas, congelados ni destellos |

Para atacar, en la Battle Phase: clic en tu monstruo y luego en el rival, o "Ataque directo". El gesto de
la carta sigue funcionando. El duelo se empieza y se termina desde el panel del centro.

Unreal dibuja todas las cartas de la mesa (`/analysis?view=table`), también las que caen entre zonas. Las
zonas sólo deciden qué cuenta para el duelo: una carta fuera de ellas tiene figura, pero el notario no la anota.

Con la cámara cenital de hoy, la figura se inclina hacia la cámara y se ve como en la vista 2D. Con
una cámara en ángulo, la figura se para vertical.

### Cámara en ángulo

No hace falta calibrar la cámara aparte (ChArUco): inclinada 12° o más respecto a la vertical, el
propio tapete da la distancia focal (`scene3d.py`; `/scene` dice `"source": "homography"` en vez de
`"assumed"`). Los pasos:

1. Poner la cámara del lado del jugador mirando la mesa a unos 30-40° de la vertical, con el tapete
   entero en el cuadro.
2. Volver a marcar las esquinas del tapete en `/duelo` (la calibración guardada es de la toma cenital).
3. Mirar `/scene`: `tilt_deg` debe rondar el ángulo real y `reprojection_px` quedar bajo 2.

Comprobado sólo con la toma simulada (`tools/fake_lab.py --tilt`), no con la cámara real. Con ella y
una sola carta, el reconocimiento aguanta igual hasta 40° (0.91-0.93, como en cenital); a 50° baja a
0.80 y pierde el contorno fino, y a 60° ya no la nombra. Falta ver con la cámara real cuánto bajan las
cartas del fondo, que se ven más chicas y escorzadas.

## Instalar

1. Unreal Engine 5.8, desde el Epic Games Launcher.
2. Visual Studio 2026 con *Desarrollo de juegos con C++*:
   `winget install --id Microsoft.VisualStudio.Community --override "--add Microsoft.VisualStudio.Workload.NativeGame --add Microsoft.VisualStudio.Workload.NativeDesktop --includeRecommended --passive"`

## Compilar, generar materiales y correr

```powershell
$UE = 'C:\Program Files\Epic Games\UE_5.8\Engine'
$P = "$PWD\unreal\YgoAR\YgoAR.uproject"
& "$UE\Build\BatchFiles\Build.bat" YgoAREditor Win64 Development "-Project=$P" -WaitMutex
& "$UE\Binaries\Win64\UnrealEditor-Cmd.exe" $P -run=pythonscript "-script=$PWD\unreal\YgoAR\Scripts\make_assets.py" -unattended -nosplash
& "$UE\Binaries\Win64\UnrealEditor.exe" $P -game -windowed -ResX=1920 -ResY=1080   # -LabUrl=http://host:8765
```

Por defecto se conecta a `http://127.0.0.1:8765`, que es el labo con `start_lab.ps1 -Live -Gpu -Full`.

Unreal mantiene despierto el reconocimiento del labo: `AnalysisLoop` se duerme si ningún cliente le
pide `/analysis`, así que no hace falta tener `/duelo` abierto. `make_assets.py` también importa los sonidos.

Para ver una invocación sin mover cartas: `-YgoReplay=4` hace que las cartas que ya están en la mesa
vuelvan a entrar 4 s después del primer cuadro (para entonces ya pasaron los tirones de la carga).
`-YgoDemo=4` reproduce todas las animaciones con esas cartas: entradas, una magia, una trampa, un
ataque con su destrucción y un ataque directo. `-YgoQuitAfter=<s>` cierra el juego solo.

La primera vez que se abre tarda en compilar shaders: mientras tanto los efectos no se ven.

## Trabajar con el editor por MCP

Unreal 5.8 trae su servidor MCP (experimental). `Scripts/editor_mcp.ps1` abre el editor con él en
`http://127.0.0.1:8000/mcp`, y Claude Code se conecta como `unreal-mcp`. Con `-Hidden` no abre ventana.
Los plugins se activan en ese script y no en `YgoAR.uproject`, para que `-game` siga ligero.

Da correr el juego en el editor en segundos, leer el registro, y pedirle a Slate el árbol real del HUD
(con sus textos) o una captura. Cierra el editor antes de `Build.bat`: Live Coding lo bloquea.

## Probar sin cámara

`tools/fake_lab.py` sirve el mismo contrato con una captura guardada y un duelo de guion: dos
invocaciones, un monstruo boca abajo con su escudo, un ataque y cambios de fase, en un ciclo de 40 s. Con
`--tilt 40` filma la misma mesa desde el lado del jugador, a 40° de la vertical (deforma la captura y
el tapete con la homografía del plano de la mesa). Con `-YgoShots` Unreal guarda
capturas de pantalla para revisar cómo se ve:

Ojo: una de cada dos capturas de `-YgoShots` sale sin los efectos translúcidos, aunque en pantalla sí
están (comprobado grabando la ventana). Cuenta sólo las que los traen.

```powershell
.\.venv-eval\Scripts\python.exe tools\fake_lab.py --port 8799
& "$UE\Binaries\Win64\UnrealEditor.exe" $P -game -windowed -ResX=1920 -ResY=1080 -LabUrl=http://127.0.0.1:8799 `
    -YgoShots=Saved\Shots -YgoShotEvery=0.25 -YgoQuitAfter=22
```
