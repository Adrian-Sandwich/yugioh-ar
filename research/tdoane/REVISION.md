# Inspección local: YGOPRO 2 — The Dawn of a New Era

Fuente instalada: `C:/Yu-Gi-Oh! The Dawn of a New Era - YGOPRO 2`. También se encontró el instalador de 1 080 590 720 bytes en Descargas. Inspección local de archivos y SQLite en modo de solo lectura; no se ejecutó el juego, launcher ni instalador.

## Recursos útiles

| Recurso instalado | Cantidad | Uso propuesto |
|---|---:|---|
| `YGOPRO/picture/card` | 14 935 imágenes | Galería visual, vinculada por ID del simulador. |
| `YGOPRO/picture/closeup` | 7 245 imágenes | Candidatos a sprites AR; validar transparencia y correspondencia. |
| `YGOPRO/picture/field` | 188 imágenes | Fondos/texturas de campo; uso opcional. |
| Bases `.cdb` | 7 archivos | IDs, alias, estadísticas y textos localizados. Hay copias repetidas y un catálogo DeckEditor distinto. |

Las muestras de Blue-Eyes son una carta completa en inglés (421 × 614) y un recorte PNG transparente. Un sprite puede dar una primera visualización 2D sobre la carta; no es un modelo 3D. Hay recursos Unity empaquetados, pero no se inspeccionó su contenido interno ni se afirma que contengan monstruos 3D.

El conteo inicial de archivos incluía un marcador sin extensión en closeup y otro en field; la tabla cuenta solo imágenes. Hay además una imagen `picture/null.png`.

## Idiomas

| Base en `MultiLanguage` | Registros en `texts` |
|---|---:|
| English | 14 880 |
| Spanish | 14 902 |
| German | 14 902 |
| French | 14 902 |
| DeckEditor | 14 855 |

No se encontró una base portuguesa. Estas cantidades no equivalen a traducciones completas ni a cartas únicas: hay variantes y posibles cadenas en inglés dentro de catálogos localizados. Consultar `inspection.json` para cobertura por ID, cadenas iguales a inglés, integridad y huecos. Las imágenes están en un directorio compartido: disponer de textos traducidos no demuestra imágenes impresas en los cuatro idiomas.

## Artes alternativos e identificadores

En la base principal hay 1 059 entradas con `alias` distinto de cero. Blue-Eyes tiene 17 entradas que apuntan a `89631139`, además de la entrada base. Se inspeccionaron visualmente `89631139.jpg` y `89631140.jpg`: presentan artes diferentes.

Detalle crítico: la segunda imagen muestra `89631140` como número impreso. Los IDs auxiliares del simulador no deben convertirse automáticamente en passwords oficiales ni IDs canónicos de YGOJSON. Mantener `source_id`, alias y `card_id` por separado; resolver la identidad mediante catálogo y comprobaciones. El campo `alias` es una pista del simulador: no toda relación se debe etiquetar automáticamente como arte alternativo, y no determina rareza.

## Copia y comprobación reproducible

Ejecutar `.\.venv\Scripts\python.exe research/inspect_tdoane.py`. Copia imágenes originales, bases CDB, `pack.db` y documentación/licencias a `downloads/tdoane-reference/`, sin modificar la instalación. Compara hashes fuente/copia y decodifica imágenes. Al finalizar genera aquí:

- `manifest.json`: archivos, tamaño, SHA-256 y dimensiones.
- `inspection.json`: integridad de SQLite, cobertura, transparencia y fallos de imagen.
- `catalog-localized.json`: textos de los cuatro idiomas por ID del simulador, sin afirmar equivalencia canónica.

Resultado verificado: **22 381 archivos, 1 213 560 825 bytes**, hashes de copia correctos, cero errores de decodificación. Incluye 22 369 imágenes, de las que 7 244 en closeup tienen transparencia. Las cartas completas se distribuyen en 14 315 de 421 × 614 píxeles y 620 de 177 × 254. Los informes y el catálogo localizado están generados.

Los cuatro catálogos comparten los 14 880 IDs ingleses. Entre ellos, las descripciones coinciden exactamente con inglés en 946 casos franceses, 945 alemanes y 965 españoles: son casos para revisar, no un conteo probado de traducciones ausentes. Hay 14 934 IDs numéricos entre las imágenes de carta y 14 873 coinciden con la base inglesa; conservar los restantes como pendientes de resolver.

Las siete bases CDB dieron `ok` en `PRAGMA quick_check`. Hay 61 IDs de imagen sin correspondencia inglesa y siete IDs ingleses sin imagen: están enumerados en el informe para resolverlos antes de integrar. No se alteró la instalación.

## Qué tomar para el proyecto

1. Priorizar la galería numérica del juego para un cruce reproducible con la base y YGOJSON; usar CardsOricaBR para ampliar referencias y comparar variantes.
2. Construir un mapa revisado `source_id -> card_id -> artwork_id`, conservando ambigüedades. No aprender los números auxiliares de las imágenes como si fueran identificadores impresos reales.
3. Incorporar textos locales como fuente adicional con procedencia; detectar diferencias con YGOJSON antes de elegir un texto. Buscar portugués aparte.
4. Seleccionar sprites transparentes por identidad/arte para la primera AR sobre la homografía; validar anclaje, orientación y varias copias físicas.
5. Probar cámara con impresiones reales y rarezas distintas. Los renders digitales y recortes no reproducen foil, fundas, reflejos ni todas las variantes de impresión.

El README instalado declara GPLv3 para el software y enlaza los proyectos `Kaiba-Corporation/ygopro-2`, `ygopro-core` y `ygopro-launcher`. Se preservan las licencias; esa declaración no verifica por sí sola las condiciones específicas de cada ilustración.
