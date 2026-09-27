# Identidades consolidadas y evidencia de arte

Actualización: el visor ya aplica los aliases a las consultas de la base activa;
ver [INTEGRACION_VISOR.md](INTEGRACION_VISOR.md). El apartado de migración al final
describe el estado previo y los criterios que guiaron esta integración.

Versión inicial publicada: `data/curated/20260926-054217-349436/registry.sqlite`.
El puntero `data/curated/latest.json` identifica la versión de consulta actual.

Resultado: 14,734 UUID de origen conservados; 14,725 identidades de consulta;
9 aliases aceptados por reglas explícitas; 3 casos pendientes y 1 conflicto.
Se conservan las 54,436 referencias visuales, incluidos todos los duplicados,
además de los nombres, identificadores, artes e impresiones originales.
Ningún archivo de imagen se modifica, borra ni sustituye.

## Reglas y trazabilidad

No se fusiona sólo por nombre o passcode. Se exige serial compartido válido,
tipo compatible, efecto idéntico después de normalizar formato, ausencia de
contradicción entre CID y corroboración por CID coincidente o nombre inglés
coincidente. Sólo se elimina el sufijo editorial `(card)` al comparar nombres.
Los pares con diferencias en campos estructurados conocidos quedan en revisión.
Son decisiones basadas en el archivo local YGOJSON, no verificación independiente
de cada carta física. El hash del ZIP, UUID de registros y razones quedan guardados.

El UUID con más idiomas y, en empate, más sets se usa como identidad de consulta.
El UUID anterior permanece en `cards` y en `identity_map`; las vistas agregan
sus observaciones sin borrar filas. No hay cadenas ni ciclos de aliases.
Una reversión se realiza publicando otra versión con un mapa corregido.

### Pendientes preservados

- `20726052`: Maliss C GWC-06, efecto no idéntico entre registros.
- `20938824`: Maliss P March Hare, efecto no idéntico entre registros.
- `20415050`: The Hidden Hecahands / Hecahands, evidencia aún insuficiente.
- `55154344`: Ryu-Ge Realm - Wyrm Winds / Ryu-Ge Rivalry: CID 20600 y 20601,
  nombres y efectos distintos. El serial compartido es un conflicto de datos;
  no se decide aquí cuál de los dos valores corregir.

Los nombres alternativos aceptados tampoco desaparecen: se consultan todos
con su fuente. El nombre preferido y la cronología de cambios editoriales
requieren una política posterior.

## Impresión y arte

Se inspeccionaron las 352,813 entradas de carta en bloques de sets del ZIP:
sus claves son `id`, `card`, `rarity`, `suffix`, `qty` y `replica`. No hay un ID
de arte en esas entradas. El importador consulta `imageID`, pero la descarga
actual no proporciona ese campo: no podemos recuperarlo simplemente renombrando
una columna. Los escaneos declarados en locales pueden servir como evidencia
futura para comparar ilustraciones.

La vista `printing_art_candidates` relaciona cada impresión con artes de su
identidad consolidada. **Todos son candidatos, no asignaciones verificadas**.
Incluso tener un solo arte conocido no demuestra que no existan otros.
La vista indica `same_declared_url` si las URL declaradas coinciden exactamente;
en los demás casos sólo indica `same_identity_only`. No elimina candidatos ni
rellena `printings.artwork_id` mediante suposiciones.

## Uso

```powershell
.\.venv-eval\Scripts\python.exe -X utf8 query_curated.py 06798031
.\.venv-eval\Scripts\python.exe -X utf8 query_curated.py "Blue-Eyes White Dragon"
.\.venv-eval\Scripts\python.exe -X utf8 query_curated.py 55154344
```

El primer caso devuelve una identidad consolidada con sus dos UUID de origen.
El último sigue devolviendo dos identidades: el conflicto no se oculta.
Las vistas disponibles son `resolved_cards`, `resolved_names`,
`resolved_identifiers`, `resolved_artworks`, `resolved_printings` y
`resolved_visual_references`. Los campos `canonical_card_id` y `card_id`
permiten distinguir identidad consolidada de procedencia.

`curated_registry.py` genera otra versión desde una copia SQLite consistente y
actualiza el puntero sólo después de validar. Es una fotografía: no incorpora
automáticamente fichas posteriores del crawler. Las copias de registro y
catálogo no representan una transacción global entre ambos servicios.

El visor y sus OCR siguen usando sus bases originales. La migración de sus
consultas requiere aplicar el mismo mapa a todas las señales (imagen, nombre,
serial y set); hacerlo sólo en una produciría falsos conflictos. Antes del
cambio, probar consultas equivalentes, datos recién importados y reversión.
El entrenamiento y los embeddings tampoco cambian con esta publicación.

Verificación: `qa_curated_registry.py` prueba rechazo por CID/tipo/efecto
contradictorio; el constructor comprueba integridad, ausencia de ciclos,
preservación de identidades y referencias, y cardinalidad de la vista consolidada.
