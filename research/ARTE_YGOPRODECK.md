# Arte recortado de YGOPRODeck y verificación geométrica — 25/09/2026

## Por qué

El registro guarda, heredadas de YGOJSON, las direcciones de arte recortado
de YGOPRODeck (`images.ygoprodeck.com/images/cards_cropped/`) para 15,014 de
16,121 ilustraciones. Ese recorte es exactamente la región que comparan SIFT
y el encoder, pero nunca se había descargado: el piloto usa 63 referencias de
carta completa de TDOANE. Su guía exige descargar y alojar las imágenes en
lugar de enlazarlas, y bloquea IPs por encima de 20 peticiones por segundo.

## Descarga

```powershell
.\.venv-eval\Scripts\python.exe research/download_ygoprodeck_art.py           # reanudable, 6 peticiones/s
.\.venv-eval\Scripts\python.exe research/download_ygoprodeck_art.py --audit   # hashes y decodificación
```

Sólo biblioteca estándar. Escribe `downloads/ygoprodeck-art/art/<id>.jpg` con
`manifest.json` (id de ilustración del registro → carta, URL, ruta, SHA-256,
bytes, estado `ok`/`missing`/`error`) y `audit.json`. Prioriza las
ilustraciones del piloto y respeta `STOP` como el descargador de Neuron. Un
HTTP 404 se anota como `missing` y no se reintenta: YGOJSON conserva ids de
imagen que la web ya no sirve. El número de archivos no equivale a identidades:
una carta con varios artes tiene varias ilustraciones.

Resultado (25/09/2026, 42 minutos a 6 peticiones/s): **14,249 ilustraciones
descargadas y verificadas**, 765 con HTTP 404 en el servidor, 0 errores, 0
corruptas; 14,087 de las 14,278 cartas con identificador YGOPRODeck tienen al
menos un arte; 2.2 GB en `downloads/ygoprodeck-art/art/`. Los archivos son
624×624 en la mayoría de cartas y 908×712 en Péndulo; unos pocos son PNG
servidos con nombre `.jpg` y se guardan tal cual. El nombre de archivo es el de
la imagen en la URL (único por URL): una primera versión usaba el
`image_source_id` del registro, que es nulo en 651 ilustraciones, y colapsaba
esas descargas en un solo archivo; se corrigió y se reintentó. Ver `audit.json`.

## Verificación geométrica de candidatas (`art_verify.py`)

El embedding propone identidades; `ArtVerifier.verify(rectificada, candidatas)`
comprueba con SIFT y homografía RANSAC si la ilustración fotografiada contiene
el arte de cada candidata (hasta tres, la aceptada visualmente primero). Regla:
≥ 30 inliers, proporción de inliers ≥ 0.6, casco convexo de los inliers ≥ 15 %
del arte de referencia y el mejor con al menos el doble de inliers que el
segundo; si dos candidatas pasan las puertas, `ambiguous`. Nunca propone cartas
fuera de la lista ni cambia los umbrales del reconocedor. El ángulo de la
homografía indica si la carta está boca abajo (SIFT es invariante a rotación,
así que un solo recorte basta).

Integración: el trabajador de OCR recibe `candidate_ids` (top-3 del
reconocedor) junto con la identidad aceptada y añade `art_match` a cada carta
rectificada de al menos 120 px de alto. `card_evidence.fuse` lo incorpora como
fuente `art`: imagen + arte concordantes producen `corroborated`; un arte que
contradice la imagen o el texto produce `conflict`. **La evidencia visual
(imagen o arte) sigue sin ganar `repeated` por repetición: sólo el texto leído
vota.** El visor muestra el resultado bajo la evidencia de cada carta.

## Evidencia

`research/art_verification_experiment.py` → `qa/art-verification/experiment-top3.json`.
Con la escena real anotada (nueve cajas, siete identidades) y tres capturas
de una carta:

- 10 de 10 candidatas con verdad anotada y rectificables verificadas con su
  identidad correcta; ninguna candidata errónea verificada; ninguna ambigua.
  Las dos cajas cortadas por el borde no se rectifican y no se evalúan.
- Incluye las candidatas que el embedding no acepta (similitud 0.42–0.76): la
  carta foil resuelta por geometría, el Mago Oscuro, Juicio Solemne y la
  segunda Ojos Anómalos. El arte las corrobora sin bajar el umbral de 0.80.
- Inliers de la identidad correcta entre 61 y 451; de candidatas erróneas,
  como mucho 40 (Chica Maga Oscura frente a Mago Oscuro), rechazadas por el
  margen 2×. En la caja de Juicio Solemne ocluida por un Blue-Eyes, el
  verificador también encuentra Blue-Eyes (58 inliers) porque el recorte
  contiene ambas cartas: la primera versión del experimento lo mostró como
  falsa verificación y motivó el margen.
- Coste en caliente en esta PC cargada: 143–380 ms por carta con tres
  candidatas (mediana 277 ms), en el hilo asíncrono de OCR, no en `/analyze`.
  Primera extracción de una referencia no cacheada: unos 100 ms adicionales.
- `qa_card_evidence.py` verifica la fotografía real de Blue-Eyes (317 inliers,
  boca abajo detectada por la homografía), negativos sin la carta, lista vacía
  e imagen plana; `qa_passcode_browser.py` exige la fuente `art` en el visor.

Límites: una escena y tres capturas; negativos sólo entre candidatas del
embedding, sin cartas desconocidas ni artes alternativos fotografiados;
umbrales fijados sobre esos datos, no calibrados; SIFT sobre reflejos fuertes
o fundas no medido. Cartas con varios artes se verifican contra todos; el
`artwork_id` devuelto es evidencia del arte, no de la impresión ni del idioma.

## Índice de embeddings con arte recortado (experimento)

`research/embedding_art_experiment.py` → `qa/embedding-art/comparison.json`.
Tres recuperaciones sobre las mismas fotos (dos escenas con las mismas siete
cartas y tres capturas de una carta, 16 candidatas con verdad anotada y
rectificables), cada una con consulta y referencia del mismo tipo, mismo
encoder, misma regla de aceptación (similitud ≥ 0.80 y margen ≥ 0.07):

| Variante | Referencias | Top-1 correcto | Aceptadas correctas | Aceptadas erróneas | Similitud media de la correcta | Margen medio |
|---|---|---|---|---|---|---|
| Carta completa (actual) | 63 del piloto (TDOANE) | 16/16 | 9 | 0 | 0.773 (mín. 0.418) | 0.571 |
| Arte recortado, piloto | las mismas 63 ilustraciones | 16/16 | 9 | 0 | 0.687 (mín. 0.261) | 0.515 |
| Arte recortado, catálogo | **14,249 artes / 14,087 cartas** | **16/16** | 11 | 0 | 0.721 (mín. 0.359) | 0.420 |

Lectura:

- Con este encoder (ViT de DRAW2, entrenado sobre cartas completas), consultar
  sólo el arte **baja** la similitud de la identidad correcta en el piloto; no
  sustituye al índice actual. La carta foil de Ojos Anómalos cae de 0.63 a 0.40.
- El índice del catálogo completo funciona: la identidad correcta queda en el
  puesto 1 entre 14,087 cartas en los 16 casos, con cero aceptaciones erróneas
  y la regla sin tocar. Las dos aceptaciones extra vienen de un arte alternativo
  del Mago Oscuro que la referencia del piloto no tenía (0.91 y 0.85).
- Los márgenes se estrechan con 14k distractores (0.42 frente a 0.57), como
  cabía esperar; la regla de aceptación deberá recalibrarse con negativos
  reales antes de usar el catálogo completo para aceptar identidades.

Diseño que habilita: **proponer a escala de catálogo y verificar por geometría**.
El índice de arte propone las candidatas (salida "fuera del deck" que el plan
pedía) y `art_verify.py` confirma con SIFT contra el arte exacto, sin bajar
umbrales. Queda en `COLA_EXPERIMENTOS.md` medirlo con negativos y en la otra
PC. Coste aquí: 14,249 embeddings en ~73 min con dos hilos y CPU compartida
(cacheados en `data/pilot/art_index-*.npy`, 44 MB); la consulta a 14k vectores
es un producto matricial despreciable frente al forward del encoder.

Límites: mismas siete cartas físicas en las dos escenas; sin cartas ajenas al
catálogo; la ventana de arte es una región anatómica fija que en Péndulo y en
cartas con marcos distintos recorta parte del arte o incluye texto.

## Frescura de los datos

`checkDBVer.php` devolvió la versión 147.08 del 25/09/2026, mientras la
instantánea de YGOJSON leyó YGOPRODeck el 07/04/2026: unos cinco meses y medio
de cartas nuevas ausentes en el registro (la más reciente de la API tiene fecha
OCG 26/09/2026). No se ha añadido una ruta de actualización directa desde la
API: mantendría procedencia distinta y la API no tiene español. Decidirlo
cuando el crawl de Neuron termine.

## Cartas completas para cartas sin imagen (27/09/2026)

1,255 identidades del catálogo no tenían una imagen de carta enlazada de al
menos 200 × 290 (`catalog.PILOT_REFS`), así que no podían entrar al piloto: 878
sin ninguna imagen y 377 sólo con propuestas de CardsOricaBR o TDOANE. La tabla
`artworks` del registro guarda también `card_url`, la carta completa de cada
ilustración; el mismo descargador la baja con `--kind card`:

```powershell
.\.venv-eval\Scripts\python.exe research/download_ygoprodeck_art.py --kind card --only-missing
.\.venv-eval\Scripts\python.exe research/download_ygoprodeck_art.py --kind card --audit
.\.venv-eval\Scripts\python.exe sync_catalog.py
```

Sólo URLs de `images.ygoprodeck.com/images/cards/`: algunas `card_url` apuntan a
Yugipedia y son arte oficial cuadrado, no la carta. Resultado: 1,157
ilustraciones en 203 s a 6 peticiones/s, 0 errores (1,017 de 813 × 1185, el
resto ~421 × 614) en `downloads/ygoprodeck-cards/`; `sync_catalog.py` añadió
1,157 referencias `ygoprodeck:card:<arte>` enlazadas por el UUID de la
ilustración, sin cambiar ninguna existente. Quedan 456 identidades sin imagen:
194 fichas, 118 de tipo desconocido, 52 skills y 92 monstruos/mágicas/trampas,
casi todas exclusivas de videojuego o anime. TCGplayer cubriría sólo 5 de esas
92 y no se añadió, para no mezclar referencias con los escaneos de calibración.
