# Integración de identidades en el visor y monitor de descarga

Implementada el 26/09/2026. `identity_resolution.py` carga el mapa de aliases
aceptados de `data/curated/latest.json` una sola vez por proceso. Las consultas
siguen leyendo `data/registry/registry.sqlite`, de modo que las fichas nuevas
del crawler siguen disponibles sin reconstruir una instantánea completa.
El índice de nombres conserva su refresco existente de hasta un minuto.

Imagen, nombre, serial, set y verificación de ilustración usan la misma resolución.
El nombre y el set agrupan coincidencias de aliases antes de evaluar ambigüedad.
El verificador de arte agrupa los recursos por identidad consolidada, conservando
todos los artes y archivos. Los resultados visuales conservan `source_card_id`;
las coincidencias de texto conservan `source_card_ids`.

Las nueve equivalencias aceptadas no se suman como nuevas fuentes ni como votos
adicionales. Los cuatro seriales pendientes continúan siendo ambiguos. Los UUID
nuevos que no aparecen en el mapa pasan intactos. No se cambian umbrales de
detección, embeddings, identidad propuesta ni posiciones mediante esta operación.

El mapa queda fijo durante la vida del servicio: una nueva publicación requiere
reiniciar los visores para no mezclar versiones con votos o cachés antiguos.
`/config`, `/analyze` y resultados completados de `/passcodes` exponen
`identity_resolution` con versión, número de aliases y errores de carga.
Si no se puede validar el mapa, todas las señales del proceso usan UUID originales.
Rollback: iniciar el servicio con `YUGIOH_IDENTITY_MODE=raw`. No hay mutaciones
de las bases fuente ni de imágenes. La interfaz de registro 8769 sigue mostrando
observaciones originales; el cambio se aplica al pipeline del visor.

## Monitor

`start_download_watch.ps1` inicia oculto `research/watch_download.py` y comprueba
si ya existe uno. Consulta cada 60 segundos, escribe `.runtime/download-watch.json`
y el visor consulta `/download-status` cada 30 segundos. El estado se ve al inicio
de la página. Si el progreso envejece se indica expresamente, sin interpretar
la palabra `running` como prueba de un proceso sano.

Cuando el crawler publica un estado terminal, el monitor compara los IDs esperados
de los índices con los archivos y las fuentes importadas. Guarda el resultado en
`research/database-audit/download-completion.json` y termina. Tener el mismo
número de archivos no basta para afirmar cobertura: debe coincidir el conjunto
esperado. Una descarga detenida o bloqueada no se presenta como completada.
Se conserva la distinción entre cobertura completa y auditoría del contenido.

El monitor no reinicia el crawler, no reintenta automáticamente errores y no
envía notificaciones al chat. El aviso aparece en el visor abierto y queda
registrado localmente. Si el proceso se reanuda después, volver a iniciar el
monitor. Después del cierre: resolver pendientes, auditar hashes/contenido,
publicar una nueva versión consolidada y actualizar el respaldo de transferencia.

## Pruebas

- `qa_identity_resolution.py`: las cinco señales coinciden para los nueve aliases,
  serial y nombre reales dejan de duplicar identidad; conflicto real preservado;
  IDs nuevos, rollback y ciclos/cadenas inválidos.
- `qa_passcode.py` y `qa_pipeline_core.py`: OCR, consenso, colas y recuperación.
- `qa_passcode_browser.py`: lectura de foto real, vídeo, set, arte, versión
  consistente entre configuración y trabajador, y estado de descarga visible.
- `qa_download_watch.py`: un archivo extra no oculta otro esperado que falta;
  la caché y la importación deben cubrir los IDs esperados antes de indicar fin.
