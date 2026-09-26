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

Pendiente: si se quiere una cobertura mayor (por set o por rareza), solicitar
acceso a la API oficial o limitarse al sitemap con el retardo de robots, y
documentar el permiso antes de escalar. No integrar estas imágenes en el
piloto sin decidir su licencia.
