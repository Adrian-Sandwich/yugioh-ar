# Muestra de escaneos de TCGplayer — 25/09/2026

## Qué hay en la página

`https://www.tcgplayer.com/search/yugioh/product?productLineName=yugioh&view=grid`
es una aplicación JavaScript: el HTML descargado (44 KB) no contiene productos.
La rejilla se rellena con una llamada `POST` a
`mp-search-api.tcgplayer.com/v1/search/request`, la misma que hace el navegador.
Cada producto trae `productId`, nombre, set (`setName`, `setCode`), número de
impresión (`customAttributes.number`, p. ej. `MAMO-EN003`), rareza, tipo,
fecha de salida, precios y las primeras ofertas (edición 1st/Unlimited,
condición, cantidad). El escaneo del producto está en
`tcgplayer-cdn.tcgplayer.com/product/<productId>_in_1000x1000.jpg`
(≈1000×680, carta completa con set code, passcode y edición legibles). Con
`productTypeName=Cards` y ofertas activas, la API reportó **46,633 cartas
sueltas en venta** el 25/09/2026.

## Reglas observadas

- `robots.txt` permite `/search/*/product` con `Crawl-Delay: 10` y prohíbe
  las búsquedas por vendedor. El sitemap publica `sitemap/yugioh.0.xml` y
  `yugioh.1.xml` con URLs de producto.
- La API de búsqueda es interna y no documentada; los escaneos son propiedad
  de TCGplayer/Konami. Los términos de servicio no pudieron leerse por HTTP
  (también son una aplicación JavaScript). Por eso el ejercicio es **una muestra
  acotada**, con el retardo de robots, sin redistribución de las imágenes, y
  cualquier uso mayor debe pasar por el programa oficial de API de TCGplayer.
- El descargador respeta `STOP`, guarda manifiesto con hashes y no rebaja
  ninguna cifra a "identidades": un producto es una impresión (set + rareza).

## Ejercicio

```powershell
.\.venv-eval\Scripts\python.exe research/download_tcgplayer_sample.py --pages 5   # 120 cartas, ~3 min
.\.venv-eval\Scripts\python.exe research/download_tcgplayer_sample.py --audit
.\.venv-eval\Scripts\python.exe research/tcgplayer_sample_check.py               # lectores locales + registro
```

Resultado: 120 escaneos (16 MB) en `downloads/tcgplayer-sample/`, todos
verificados; 100 del set MAMO (Magnificent Monsters, orden por defecto de la
búsqueda) y el resto de MP25, CORI, L26D, LAVD, RA01, LDS3 y DUAD; rarezas
Ultra 83, Secret 21, Common 10, Super 5, Prismatic Secret 1. La muestra está
sesgada al orden de la tienda, no es representativa del juego.

Lectores locales sobre el escaneo completo reescalado a 630×920 (condición
ideal: frontal, sin perspectiva ni reflejos), `qa/tcgplayer-sample/check.json`:

| Lectura | Aciertos / 120 |
|---|---|
| Set code exacto (`SetReader`) | 104 |
| Nombre con coincidencia en el registro (`TitleReader`) | 108 |
| Nombre igual al de la ficha de TCGplayer (normalizado) | 94 |
| Passcode leído con confianza ≥ 0.85 (`NumberReader`) | 114 |
| Passcode coherente con el set code en el registro | 109 |

Mediana de 1.04 s por carta con los tres lectores. Hallazgos: 117 de los 120
números de impresión existen en el registro (MAMO ya estaba en la instantánea
de YGOJSON); la propia ficha de TCGplayer tiene erratas (`LAVD-ENO01` con letra
O), lo que confirma la regla de no corregir O/0 en ninguna dirección; los
fallos del set code se concentran en franjas que el reescalado del escaneo con
borde blanco desplaza respecto a las regiones anatómicas fijas.

## Para qué sirve

1. **Verdad de terreno por impresión**: cada escaneo trae set code, rareza y
   edición; permite medir OCR de set code y rareza por acabado (foil, secret)
   con etiquetas fiables, cosa que YGOPRODeck (una imagen por arte) no da.
2. **Referencias por rareza** para el reconocedor: los acabados cambian la
   apariencia del arte; con muestras por rareza se puede medir cuánto.
3. **Precios y disponibilidad** no interesan al reconocimiento; se guardan
   sólo como contexto de la muestra.

## Descarga completa (en curso desde el 25/09/2026 por la noche)

Por decisión del usuario se lanzó la cobertura completa con las tres vías:

1. **Búsqueda completa**: las 1,943 páginas de cartas sueltas en venta (46,633
   productos), una petición cada 10 s (~5.4 h). Aporta los metadatos por producto.
2. **Sitemap**: `sitemap/yugioh.0.xml` y `yugioh.1.xml` listan **47,824 ids de
   producto** (todo Yu-Gi-Oh!, incluidos sellados y sin stock); sus escaneos se
   descargan por id desde el CDN a 3 imágenes por segundo (~4.4 h, ~7 GB).
   Los productos que no aparezcan en la búsqueda quedan sólo con su `slug`.
3. **API oficial**: `developer.tcgplayer.com` redirige a `docs.tcgplayer.com`,
   que sólo documenta la autorización de aplicaciones ya creadas; el artículo
   de ayuda sobre acceso está detrás de un desafío de Cloudflare y no pudo
   leerse desde aquí. Hasta donde se sabe, TCGplayer no acepta solicitudes
   nuevas desde 2023; confirmarlo en el navegador antes de contar con esa vía.

```powershell
.\.venv-eval\Scripts\python.exe research/download_tcgplayer_sample.py --all --sitemap --image-rate 3
```

Reanudable; `STOP` en la carpeta pausa búsqueda e imágenes. Registro en
`.runtime/tcgplayer-full.log`. Al terminar: `--audit`, actualizar aquí las
cifras y repetir `tcgplayer_sample_check.py` sobre una muestra estratificada
por rareza (leer los 47k escaneos costaría unas 13 h de OCR). No integrar
estas imágenes en el piloto sin decidir su licencia.

## Reinicio del 26/09 y reconstrucción sin repetir el rastreo

La PC se reinició a las 10:47 del 26/09 con la descarga a medias. Los
escaneos en disco sobrevivieron (29 truncados se borraron), pero el
manifiesto quedó con 36 MB de ceros: se perdieron el progreso por set y los
metadatos de unos 20,000 productos. Desde entonces el descargador escribe con
`fsync`, conserva `manifest.bak` y puede reconstruir el estado desde disco
(`--rebuild-from-disk`).

Por decisión del usuario no se repitió el rastreo completo como vía principal.
Reconstrucción sin red (`research/tcgplayer_reconstruct.py`):

1. La URL de cada producto en el sitemap (`yugioh-<set>-<carta>[-<rareza>]`)
   da set, nombre y a veces rareza; los 618 nombres de set de la búsqueda
   permiten segmentar la URL.
2. El registro resuelve el nombre a `card_id` y, con el producto YGOJSON del
   set, el número de impresión; se prefieren códigos `-EN` o sin locale.
3. `research/tcgplayer_scan_numbers.py` lee set code y passcode **en el propio
   escaneo** de los productos sin número resuelto: 16,340 escaneos con cuatro
   procesos en unos 100 minutos. La fusión (`--with-scans`) sólo acepta un
   código leído si el registro lo conoce; las lecturas no verificadas quedan
   como evidencia (`number_read_unverified`), fieles a la regla de no corregir.

Resultado final (`qa/tcgplayer-sample/reconstruct.json`, 27/09/2026, con el
rastreo por sets completo: 613 de 613 sets, 46,325 productos con metadatos
exactos de la búsqueda):

| | Productos |
|---|---|
| Total en el sitemap | 47,824 |
| Escaneos válidos en disco | 46,058 (1,766 sin imagen en el CDN) |
| Set identificado | 47,737 |
| Carta identificada (nombre o passcode leído) | 45,901 |
| Número de impresión resuelto | 46,362 (búsqueda 46,208 · registro 115 · escaneo 39) |
| Sin número | 47, más 17 ambiguos entre varias impresiones |
| Código leído sin verificar (conservado como evidencia) | 12 |

Antes de completar el rastreo, la reconstrucción sin red ya resolvía 36,440
números (búsqueda 11,934 · registro 21,232 · escaneo 3,274) con 250 lecturas
en conflicto con el registro: el rastreo sustituyó casi todas las inferencias
por el dato exacto de TCGplayer.

Lo que no se recupera sin la API: ediciones ofertadas y precios, irrelevantes
para el reconocimiento. El rastreo por sets continúa en segundo plano y va
sustituyendo las inferencias por metadatos exactos; `STOP` lo detiene.

**Muertes silenciosas del rastreo (26/09, 16:29 y 19:24).** El error estaba
en `tcgplayer-full*.error.log`: `PermissionError` al rotar `manifest.json` a
`manifest.bak`, porque en Windows `os.replace` falla mientras otro proceso
tiene el archivo abierto para lectura (la reconstrucción y la calibración lo
leen). Desde entonces `save()` reintenta la rotación hasta diez segundos y,
si sigue ocupado, conserva la copia anterior y sigue; la partición por sets
hace que relanzar con `--all --image-rate 3` retome donde iba. Los escaneos
sirvieron además para calibrar la regla de aceptación del reconocedor y las
regiones del set code: [CALIBRACION_ESCANEOS.md](CALIBRACION_ESCANEOS.md).
