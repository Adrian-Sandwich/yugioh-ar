# Índice de documentos

Qué leer y en qué orden. El estado más reciente gana: si dos documentos se contradicen, vale
el de la sección «Vigentes». Los históricos se conservan (y sus enlaces siguen funcionando)
porque explican por qué el código es como es, pero no describen el estado actual.

Actualizado el 02/10/2026.

## Empezar

- [README](../README.md) · [README en español](../README.es.md): qué es el proyecto, qué funciona y cómo arrancarlo.
- [ARRANQUE_GPU](ARRANQUE_GPU.md): instalar y levantar el laboratorio en la PC con GPU
  (`start_lab.ps1 -Live -Gpu -Full -Review`; en esta PC arranca solo al iniciar sesión).
- [CI](CI.md): qué pruebas corren en GitHub y cómo correrlas en local (`python run_qa.py --ci`).
- [CONTRIBUTING](../CONTRIBUTING.md) · [CONTRIBUTING en español](../CONTRIBUTING.es.md).

## Vigentes

| Documento | De qué trata | Fecha |
|---|---|---|
| [PLAN_3D_Y_REVISION](../research/PLAN_3D_Y_REVISION.md) | **Plan actual**: revisión humana de recortes, generación 3D, motor gráfico | 29/09 |
| [GENERACION_3D](../research/GENERACION_3D.md) | Generadores imagen→3D, instalación en Windows y banco de pruebas | 29/09–30/09 |
| [MOTOR_DE_DUELO](../research/MOTOR_DE_DUELO.md) | Motor de duelo, modo notario, duelo desde la mesa | 26/09–28/09 |
| [DUELO_REMOTO](../research/DUELO_REMOTO.md) | Plan del duelo remoto con AR | 28/09 |
| [TIEMPO_REAL](../research/TIEMPO_REAL.md) | Bucle del visor en vivo, seguimiento, aceptación por arte | 26/09 |
| [REGISTRO_MULTILINGUE](../research/REGISTRO_MULTILINGUE.md) | Registro de nombres, passcodes e impresiones en cinco idiomas | 27/09 |
| [PROTOCOLO_CAPTURAS](../research/PROTOCOLO_CAPTURAS.md) | Cómo capturar cartas reales para pruebas y entrenamiento | 26/09 |
| [CALIBRACION_ESCANEOS](../research/CALIBRACION_ESCANEOS.md) | Umbrales de aceptación calibrados con escaneos de TCGplayer | 27/09 |
| [CODEBASE_MEMORY](../research/CODEBASE_MEMORY.md) | Índice del código con Codebase Memory (herramienta) | 25/09–28/09 |
| [REPOSITORIOS](../research/REPOSITORIOS.md) | Proyectos parecidos evaluados | 27/09 |

## Referencia técnica (estudios de un componente; válidos salvo que el código diga otra cosa)

[GEOMETRIA_CARTAS](../research/GEOMETRIA_CARTAS.md) ·
[OCR_PASSCODE](../research/OCR_PASSCODE.md) ·
[OCR_NOMBRE](../research/OCR_NOMBRE.md) ·
[EVIDENCIA_TEMPORAL](../research/EVIDENCIA_TEMPORAL.md) ·
[ARTE_YGOPRODECK](../research/ARTE_YGOPRODECK.md) ·
[ESTADO_DEL_ARTE_REFLEJOS](../research/ESTADO_DEL_ARTE_REFLEJOS.md) ·
[REFLEJOS_Y_CAPTURAS](../research/REFLEJOS_Y_CAPTURAS.md) ·
[TCGPLAYER_MUESTRA](../research/TCGPLAYER_MUESTRA.md) ·
[CATALOGO_RECONOCIMIENTO_AMPLIADO](../research/CATALOGO_RECONOCIMIENTO_AMPLIADO.md) ·
[PLAN_VECTORES_E_INVARIANCIA](../research/PLAN_VECTORES_E_INVARIANCIA.md) ·
[COLA_EXPERIMENTOS](../research/COLA_EXPERIMENTOS.md)

## Históricos (24–25/09/2026; sustituidos)

| Documento | Lo sustituye |
|---|---|
| [PLAN_DE_ACCION](../research/PLAN_DE_ACCION.md) | este índice y PLAN_3D_Y_REVISION |
| [PLAN_MEJORA_INTEGRAL](../research/PLAN_MEJORA_INTEGRAL.md) | PLAN_3D_Y_REVISION y TIEMPO_REAL |
| [PIPELINE_ESTADO](../research/PIPELINE_ESTADO.md) | TIEMPO_REAL y el código de camera_viewer.py |
| [TRANSFERENCIA_GENERAL](../research/TRANSFERENCIA_GENERAL.md) | ARRANQUE_GPU (traslado a la PC con GPU, ya hecho) |
| [ENTREGA_PILOTO](../research/ENTREGA_PILOTO.md) | ARRANQUE_GPU; el piloto de 35 cartas quedó como alcance `pilot` |
| [CORRECCION_CAMARA_EN_VIVO](../research/CORRECCION_CAMARA_EN_VIVO.md) | TIEMPO_REAL |
| [BITACORA_INICIAL](BITACORA_INICIAL.md) | la historia del README |

## Dónde está cada cosa

- Código del laboratorio: archivos `.py` de la raíz. Rutas y variables de entorno: `settings.py`;
  qué viaja entre partes (detecciones, pistas): `contracts.py`; el análisis en vivo: `pipeline.py`;
  el reconocedor: `vision_onnx.py` con `onnx_models.py`, `reference_index.py` y `promotions.py`.
- `tools/`: herramientas que el laboratorio usa y se corren a mano: recortes automáticos
  (`auto_cutout.py`, `run_auto_cutout.ps1`), crítico con veredictos (`critic_human.py`), candidatos
  de holograma, banco 3D (`gen3d_bench.py`, `gen3d_workers/`), vigilancia de descargas y `doctor.py`.
- `reference/`: entradas versionadas que el código lee: mapa de DRAW2, modelo del crítico de
  recortes, catálogo de TDOANE (`tdoane/`) y correcciones revisadas del registro.
- `reviews/`: veredictos humanos del revisor de recortes (datos, no se regeneran).
- Pruebas: `qa_*.py` (escriben en `.runtime/qa/`, no versionado); `run_qa.py` las corre.
- `research/`: estudios, experimentos y sus informes. Nada del laboratorio depende de aquí.
- `data/`, `downloads/`: datos y modelos, fuera de git.
