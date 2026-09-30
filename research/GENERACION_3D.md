# Generación automática de modelos 3D

Parte del plan general: [PLAN_3D_Y_REVISION.md](PLAN_3D_Y_REVISION.md).

Estado, 29/09/2026: banco de pruebas escrito (`gen3d_bench.py`), **sin ejecutar todavía**. TripoSR va sin `--bake-texture`: con esa opción su `run.py` exporta OBJ aunque el archivo se llame `.glb`. Se preparó
en un entorno sin GPU; la lógica del banco se probó con un generador falso, pero ningún generador real.

## Idea

Extender la tubería de los sprites automáticos (`auto_cutout.py`): el recorte de BiRefNet que ya
existe entra a un modelo imagen→3D preentrenado y sale un glTF por `artwork_id`. Después vendrán
completar la figura (las ilustraciones cortan al monstruo), el rig automático y un crítico que compare
renders del modelo con el arte, como el crítico de recortes.

No se entrena con modelos extraídos de Master Duel, Duel Links u otros juegos oficiales. Extraerlos
viola sus términos y son assets de Konami; en un repositorio público pondría en riesgo todo el
proyecto. El estilo se ajustará con prompts o con modelos propios aprobados.

## Candidatos para 12 GB (RTX 4070)

| Generador | VRAM declarada | Licencia | Notas |
|---|---|---|---|
| TripoSR | ~6 GB | MIT | El más simple y permisivo. Calidad más baja. En el banco va con color por vértice: su opción de textura exporta OBJ. |
| Stable Fast 3D | ~6 GB | Stability AI Community | Modelo restringido en HuggingFace: pedir acceso y `huggingface-cli login`. Windows experimental. |
| Hunyuan3D-2mini (forma) | ~6 GB | Tencent Hunyuan Community | Turbo + FlashVDM, 5 pasos. |
| Hunyuan3D-2mini + Paint | 16 GB en total | Tencent Hunyuan Community | El worker libera la forma y usa CPU offload para la textura. Puede no caber o ser lento. |
| TRELLIS | ≥16 GB, solo Linux | MIT | Fuera del banco por ahora. |
| TRELLIS.2 (4B) | ≥16 GB a 512³ | MIT | Materiales PBR y topologías complejas. Para una tanda en la nube. |
| SAM 3D Objects | ≥32 GB, Linux | SAM License | Pensado para objetos ocluidos y recortados, como las ilustraciones. Para la nube. |

Las cifras de VRAM son de cada README o de reseñas, no están medidas aquí. Esa es la tarea del banco.
Escala, animación y modelos para la nube: ver «Generación automática de modelos 3D» en [PLAN_3D_Y_REVISION.md](PLAN_3D_Y_REVISION.md).

## Instalación (Windows, PowerShell)

Cada generador va en su propio clon y venv dentro de `downloads/gen3d/` (ignorado por git), porque sus
versiones de PyTorch chocan entre sí y con `.venv-gpu`. Los tres compilan extensiones CUDA, así que
necesitan Visual Studio 2022 Build Tools (C++) y un CUDA Toolkit de la misma versión mayor que la
rueda de PyTorch.

```powershell
mkdir downloads/gen3d; cd downloads/gen3d
git clone https://github.com/VAST-AI-Research/TripoSR triposr
git clone https://github.com/Stability-AI/stable-fast-3d sf3d
git clone https://github.com/Tencent-Hunyuan/Hunyuan3D-2 hunyuan
foreach ($d in 'triposr','sf3d','hunyuan') {
  py -3.11 -m venv $d/.venv
  & "$d/.venv/Scripts/python.exe" -m pip install -U pip setuptools wheel
  & "$d/.venv/Scripts/python.exe" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
}
# Después, en cada carpeta, los requirements según su README:
#   triposr:  pip install -r requirements.txt
#   sf3d:     pip install -r requirements.txt  (+ huggingface-cli login)
#   hunyuan:  pip install -r requirements.txt; pip install -e .
#             y, solo para textura, compilar hy3dgen/texgen/custom_rasterizer y differentiable_renderer
```

## Uso

```powershell
.venv-gpu/Scripts/python.exe research/gen3d_bench.py run --sprites 6 --approved # 6 recortes aprobados al azar
.venv-gpu/Scripts/python.exe research/gen3d_bench.py run --sprites 6 --only sf3d  # uno solo
python -m http.server -d downloads/gen3d/out 8771                                 # hoja comparativa
```

El banco corre cada generador dos veces, una con 1 imagen y otra con todas, para separar el tiempo de
carga del tiempo por modelo. También registra el pico de VRAM (nvidia-smi menos el reposo), si hubo
falta de memoria, los triángulos, si el modelo tiene textura y el peso del GLB. El informe queda en
`research/qa/gen3d-bench.json` y la hoja en `downloads/gen3d/out/index.html`, con cada recorte junto
a sus modelos girando.

Para decidir hay que mirar la hoja: los números dicen qué cabe y qué tarda, pero no si el monstruo
se parece a su carta.
