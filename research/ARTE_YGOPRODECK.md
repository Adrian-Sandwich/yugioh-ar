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

Estado al cierre de la sesión: ver `downloads/ygoprodeck-art/audit.json`
(la descarga completa tarda unos 45 minutos a 6 peticiones/s). Los archivos
son 624×624 en la mayoría de cartas y 908×712 en Péndulo.

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

## Frescura de los datos

`checkDBVer.php` devolvió la versión 147.08 del 25/09/2026, mientras la
instantánea de YGOJSON leyó YGOPRODeck el 07/04/2026: unos cinco meses y medio
de cartas nuevas ausentes en el registro (la más reciente de la API tiene fecha
OCG 26/09/2026). No se ha añadido una ruta de actualización directa desde la
API: mantendría procedencia distinta y la API no tiene español. Decidirlo
cuando el crawl de Neuron termine.
