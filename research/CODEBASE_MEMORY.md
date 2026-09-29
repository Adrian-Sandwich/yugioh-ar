# Codebase Memory: acceso y estado

25/09/2026. Ejecutable instalado: versión 0.10.8. La prueba independiente de
MCP por stdio pasó `initialize` y `list_projects`. La conexión integrada en la
sesión de Codex que inició el diagnóstico continúa devolviendo `Transport closed`.
No se atribuye el cierre original a una causa confirmada. Dentro del sandbox,
la CLI falla al crear su endpoint local de coordinación; fuera funciona.

El proyecto está indexado con nombre **yugioh**, modo `fast`: 17,916 nodos y
20,085 relaciones en la primera ejecución. `.cbmignore` excluye dependencias,
modelos, imágenes descargadas, bases y clones externos. Se registró un parseo
parcial en `research/tdoane/catalog-localized.json`, un catálogo de datos.
Los resultados y cobertura exacta están en `research/qa/cbm-diagnostic/`.

La consulta de los cinco archivos principales no registró errores de parseo,
pero devolvió `freshness=metadata_changed` incluso después de la indexación.
La causa no se ha determinado: no considerar el grafo una copia verificada del
contenido actual sin contrastar el código fuente y revisar esa señal.

La interfaz CLI usa el mismo motor de Codebase Memory; no es una búsqueda
simulada. Consultas reproducibles desde la raíz:

```powershell
.\.venv-eval\Scripts\python.exe research/cbm_local.py get_architecture research/cbm-architecture-request.json --output research/qa/cbm-diagnostic/architecture.json
.\.venv-eval\Scripts\python.exe research/cbm_local.py check_index_coverage research/cbm-coverage-request.json --output research/qa/cbm-diagnostic/coverage.json
```

Estas llamadas requieren permiso fuera del sandbox en este entorno. La CLI
inicia un daemon temporal cuando hace falta; no se modificó la configuración
global ni se dejó un daemon persistente instalado por este trabajo.

Para el análisis posterior, usar `search_graph` para descubrir símbolos,
`trace_path` para relaciones, `get_code_snippet` para código y comprobar cobertura
de cada archivo antes de concluir. La consulta inicial de ciclos encontró cero
ciclos en 344 aristas CALLS; esto **no prueba ausencia de bucles de ejecución**,
problemas asíncronos o relaciones dinámicas ausentes del grafo.

La reconexión de la herramienta integrada requiere actuar desde el cliente Codex;
la CLI permite continuar entretanto. No es necesario reinstalar el ejecutable
basándose en este diagnóstico. Neuron y el visor no se reiniciaron en esta tarea.

## Revisión del 25/09/2026 (tarde) desde Claude Code

La conexión MCP integrada funcionó en esta sesión. Se reindexó con nombre
`yugioh` en modo `moderate` (18,667 nodos, 21,969 relaciones) tras ampliar
`.cbmignore` con `.venv-pose/`, `transfer/` y `Ultralytics/`. Un primer
reindexado sin nombre creó el proyecto duplicado `C-Users-Adrian-src-yugioh`;
el borrado automático fue denegado por la política de la sesión, así que ese
índice sigue existiendo y puede eliminarse a mano con `delete_project`.

Confirmado: `check_index_coverage` devuelve `freshness=metadata_changed` en los
archivos principales incluso segundos después de reindexar; es un
comportamiento de la herramienta en este entorno, no una diferencia real de
contenido. También se confirmó en el fuente que aristas como
`PasscodeWorker.run → scrape_neuron.fetch` o `→ download_cardsoricabr.request`
son resoluciones heurísticas por nombre (`fetch`, `request`, `wait_for`) sin
llamada real. Usar el grafo para orientarse y `get_code_snippet` o el fuente
para afirmar dependencias.

## 28/09/2026: PC con GPU

Instalada la versión 0.11.0 (binario oficial de DeusData, checksum verificado)
en `%LOCALAPPDATA%\Programs\codebase-memory-mcp`. `cbm_local.py` ya no fija la
ruta del usuario: usa `CBM_EXE` o `%LOCALAPPDATA%`. Reindexado `yugioh` en modo
`moderate` desde `C:/Users/USER/src/yugioh/yugioh`: 20,739 nodos y 30,600
relaciones; 18 parseos parciales, todos en HTML descargado de la auditoría.
