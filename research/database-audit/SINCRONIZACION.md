# Sincronización aditiva del catálogo

`sync_catalog.py` prepara una copia del catálogo, añade identidades presentes
en el registro y referencias de ilustraciones del manifiesto YGOPRODeck.
Comprueba cada imagen incorporada con SHA-256 y apertura/validación del formato,
y comprueba la relación UUID de arte → identidad contra el registro.

Conserva todos los archivos, filas existentes, revisiones y referencias con
contenido repetido. Cada UUID de arte tiene su referencia; dos referencias
pueden apuntar a archivos idénticos o incluso a una misma ruta de procedencia.
No se inventan copias nuevas donde el manifiesto ya comparte un archivo.
Los assets ausentes quedan registrados como no disponibles en `asset_sources`.
Un enlace de fuente no equivale a revisión visual humana.

La ruta rota de Fanfan sólo se corrige si existe un único candidato con hash
idéntico. No se renombra ni se toca la imagen. Los manifiestos originales se
conservan; la corrección queda en el informe de sincronización.

Publicación: transacción SQLite que incorpora nuevas filas y la reparación
verificada. Primero compara el catálogo con la copia inicial; si cambió durante
la preparación, aborta y pide repetir el proceso. No reemplaza el archivo de
base abierto por los servicios. Revisiones y descarga Neuron usan otras bases y
permanecen intactas. Hay respaldo `catalog-before.sqlite`, staging y `result.json`
en una carpeta `sync-FECHA` nueva por ejecución.

`build_catalog.py` pasa a usar esta sincronización cuando ya existe un catálogo:
un rebuild ordinario no debe descartar referencias acumuladas. La construcción
desde cero sigue disponible cuando no existe la base.

Prueba: `qa_catalog_sync.py` conserva dos imágenes idénticas como dos archivos y
dos referencias, comprueba idempotencia y rechaza un hash discrepante.

El índice visual del piloto no se regenera con esta operación. Los nuevos artes
son tipo `art`, no fotografías completas tipo `card`: no deben entrar al encoder
de cartas completas sin una estrategia de recorte y validación compatible.
Tampoco se fusionan aún UUID conflictivos ni se asignan artes a impresiones sin
evidencia. Esos pasos permanecen en el plan de organización.
