# Reparaciones de identidades e importaciones

Se mantienen todos los registros originales, imágenes y referencias duplicadas.
La resolución cambia la capa de consulta; no elimina afirmaciones de las fuentes.

## Identidades

Los tres pares pendientes se revisaron individualmente: los dos Maliss tienen
el mismo CID y serial, y sólo varía el nombre propio en el efecto. Hecahands
corresponde a una denominación/traducción anterior: la respuesta actual de
YGOPRODeck para 20415050 coincide con The Hidden Hecahands de Neuron CID 21938.
No se relajó globalmente la comparación aproximada de efectos.

Se pasa de 9 a 12 aliases aceptados: 14,734 registros de origen y 14,722 identidades
de consulta. `reviewed-corrections.json` fija los UUID, hashes de registros,
motivos y evidencia; si cambia un registro o archivo de evidencia, se aborta
la publicación y se exige revisar esa decisión.

Ryu-Ge conserva dos identidades distintas. La atribución de 55154344 a Rivalry
queda `disputed`: las fuentes consultadas asignan 55154344 a Wyrm Winds y
81549048 a Rivalry. La observación original sigue en `identifiers`; queda
excluida de `resolved_identifiers` y del lector de serial. No se afirma haber
descartado cualquier posible error de impresión histórico: una evidencia
física posterior permitiría reabrir la decisión por impresión.

Fuentes consultadas:
- https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=20590&request_locale=en
- https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=21160&request_locale=en
- https://www.db.yugioh-card.com/yugiohdb/card_search.action?ope=2&cid=21938&request_locale=en
- https://yugioh.fandom.com/wiki/Ryu-Ge_Rivalry
- https://yugioh.fandom.com/wiki/Ryu-Ge_Realm_-_Wyrm_Winds
- https://db.ygoprodeck.com/api/v7/cardinfo.php?id=20415050,81549048,55154344

La respuesta API está conservada en `evidence-20260926/ygoprodeck-cards.json`.

## Importaciones

`repair_registry_observations.py` crea un respaldo coherente antes de una
transacción aditiva y registra decisiones en `issue_resolutions`.

- Tres valores con comentarios HTML ya tienen su serial limpio en la base:
  quedan `already_present_clean`; no se inventan ni duplican números.
- Diez packs del juego: identidad respaldada por código de set existente y
  nombre o serial concordante. Se incorporan como observaciones de esa fuente,
  sin afirmar validación de rareza física ni arte.
- Siete IDs de tokens: la cadena de aliases del juego resuelve la identidad,
  pero el código de set no está corroborado. Se añaden identificadores `game_id`,
  quedan `game_identity_only` y no generan impresiones físicas.
- Noventa incidencias de CID ambiguo bloqueaban partes de la importación.
  Se reprocesan 80 archivos distintos de índices/fichas desde caché con los
  aliases aceptados. Descargar y registrar una fuente no garantizaba que sus
  filas de nombres/impresiones hubieran sido importadas; ahora se recuperan.

`registry.resolved_neuron_matches` aplica el mapa al importar; si el destino no
existe en la base, conserva la consulta original. Los conflictos todavía no
resueltos siguen rechazándose. Las incidencias históricas de `issues` se conservan;
consultar `issue_resolutions` para distinguir lo recuperado de lo pendiente.

Informes: `import-repairs.json`, `import-repairs-result.json` e
`import-repairs-verification.json`. `qa_registry_repairs.py` comprueba que cada
observación anterior siga existiendo y que los siete tokens no generen impresiones.

## Alcance pendiente

Estas reparaciones no resuelven la asociación impresión–arte de todo el corpus,
las referencias visuales propuestas/sin resolver ni la validación física de
acabados y rarezas. El registro 8769 muestra evidencia original; el visor y
las vistas consolidadas usan las decisiones revisadas. Reiniciar los visores
es necesario para cargar el nuevo mapa, que permanece fijo durante cada proceso.
