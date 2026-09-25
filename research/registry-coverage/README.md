# Cobertura del registro durante la descarga

Instantánea UTC: 2026-09-25T17:20:11.920258+00:00

14734 registros de carta; 50 identidades del piloto.

| Idioma | Con nombre | Con observaciones de impresión | Nombre sin impresiones |
|---|---:|---:|---:|
| en | 14734 | 14130 | 604 |
| es | 14314 | 13839 | 492 |
| de | 14332 | 13942 | 410 |
| fr | 14351 | 13943 | 408 |
| pt | 12463 | 12301 | 229 |

Sin passcode: 635. Passcodes compartidos entre registros: 13. Passcodes con formato inválido: 0.

## Cómo usar los archivos

- `pilot.csv`: las identidades del piloto y sus nombres, seriales, artes y cobertura de sets por idioma.
- `cards.csv`: todas las identidades; `review.csv`: registros con algún dato pendiente de revisión.
- `summary.json`: conteos, seriales compartidos e incidencias del importador.

Importar seriales como texto para conservar ceros iniciales. Los nombres alternativos se mantienen juntos, sin elegir una variante canónica.

La ausencia de traducción o impresión no demuestra que exista una edición en ese idioma. Un passcode ausente puede ser legítimo; los compartidos requieren revisión y no se fusionan automáticamente. Los conteos de impresiones son observaciones de fuentes, no unidades físicas únicas. Los registros de arte no prueban rareza ni cobertura visual completa.

El crawler sigue incorporando fichas. Este informe lee una transacción coherente y cierra la conexión antes de escribir CSV; no modifica la base. Repetir al terminar la descarga:

```powershell
.\.venv-eval\Scripts\python.exe research/audit_registry_coverage.py
```

Prioridad: revisar primero `pilot.csv`, después seriales compartidos e incidencias, y finalmente los huecos por idioma cuando termine Neuron. No completar traducciones, artes ni rarezas por inferencia.
