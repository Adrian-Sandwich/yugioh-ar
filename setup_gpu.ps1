<#
Arranque del laboratorio en la computadora con GPU (Windows, Python 3.14).

Crea los dos entornos, instala PyTorch para la GPU indicada y verifica con
research/doctor.py. No descarga datos ni modelos: la carpeta data/ y downloads/
llegan con el zip o por copia; las bases limpias están en transfer/<fecha>/.

  powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_gpu.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_gpu.ps1 -TorchIndexUrl https://download.pytorch.org/whl/cu130

Elegir el índice de PyTorch según el controlador NVIDIA instalado (nvidia-smi
muestra la versión de CUDA soportada): https://pytorch.org/get-started/locally/
El índice debe tener torch 2.14.0 para esta versión de Python; si no la tiene,
pip instalaría la de CPU desde PyPI al instalar el resto del lock. Por eso el
script se detiene si PyTorch no ve la GPU. Probado el 27/09/2026 (Python 3.14,
controlador 617.14): cu126, cu130 y cu132 tienen 2.14.0; cu128 no.

Crea también .venv-gpu (visor con onnxruntime-gpu, `start_lab.ps1 -Gpu`).
#>
param(
    [string]$Python = 'python',
    [string]$TorchIndexUrl = 'https://download.pytorch.org/whl/cu132',
    [switch]$SkipPose,
    [switch]$SkipGpuViewer,
    [switch]$RestoreDatabases
)
# Continue, not Stop: in Windows PowerShell a native program writing to stderr
# (pip warnings, Playwright's "already installed") becomes a terminating error
# under Stop. Failures are checked explicitly with Need.
$ErrorActionPreference = 'Continue'
$root = $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }
function Need($what) { if ($LASTEXITCODE -ne 0) { throw "Falló: $what (código $LASTEXITCODE)" } }

Step 'Python del sistema'
& $Python --version

if ($RestoreDatabases) {
    Step 'Bases limpias desde transfer/ (la más reciente)'
    $bundle = Get-ChildItem (Join-Path $root 'transfer') -Directory | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $bundle) { throw 'No hay carpeta transfer/<fecha> con respaldos' }
    foreach ($rel in 'data/registry/registry.sqlite', 'data/catalog/catalog.sqlite', 'data/catalog/reviews.sqlite') {
        $src = Join-Path $bundle.FullName $rel
        if (Test-Path $src) {
            $dst = Join-Path $root $rel; New-Item -ItemType Directory -Force (Split-Path $dst) | Out-Null
            Copy-Item $src $dst -Force; Write-Host "restaurado $rel desde $($bundle.Name)"
        }
    }
    Get-ChildItem (Join-Path $root 'data') -Recurse -Include *.sqlite-wal, *.sqlite-shm -File -ErrorAction SilentlyContinue | Remove-Item -Force
}

function Venv($name) {
    # A venv copied from another PC has python.exe but points at that PC's Python
    # (pyvenv.cfg home): keep it aside as <name>.old and create a fresh one.
    $exe = ".\$name\Scripts\python.exe"
    if (Test-Path $exe) {
        & $exe -c "pass" 2>$null
        if ($LASTEXITCODE -ne 0) { Write-Host "$name no funciona en esta PC; se aparta como $name.old"; Rename-Item $name "$name.old" }
    }
    # Out-Host: inside a function every output line would be returned along with $exe.
    if (-not (Test-Path $exe)) { & $Python -m venv $name | Out-Host; Need "crear $name" }
    & $exe -m pip install --upgrade pip | Out-Host; Need "pip en $name"
    return $exe
}

Step 'Entorno .venv-eval (visor, OCR, pruebas)'
$eval = Venv '.venv-eval'
& $eval -m pip install -r requirements-research.txt -r requirements-ocr.txt; Need 'requisitos de .venv-eval'
# rapidocr declara opencv-python; el proyecto usa opencv-python-headless, así que
# pip check lo reporta y no es un error.
& $eval -m pip install --no-deps rapidocr==3.9.2; Need 'rapidocr'
& $eval -m pip check
# Falla sin daño si Edge ya está instalado en el sistema.
& $eval -m playwright install msedge

Step 'Verificación del entorno de visores'
& $eval -X utf8 research/doctor.py --output research/qa/destino-visores.json; Need 'doctor de visores'

if (-not $SkipPose) {
    Step ".venv-pose (YOLO11) con PyTorch desde $TorchIndexUrl"
    $pose = Venv '.venv-pose'
    # PyTorch primero, para la GPU; después el resto del lock sin sus líneas de torch.
    & $pose -m pip install torch==2.14.0 torchvision==0.29.0 --index-url $TorchIndexUrl; Need "torch 2.14.0 desde $TorchIndexUrl (¿tiene ese índice la versión?)"
    $lock = Get-Content requirements-pose-lock.txt | Where-Object { $_ -notmatch '^(torch|torchvision)==' }
    $tmp = Join-Path $env:TEMP 'pose-lock-sin-torch.txt'; $lock | Set-Content $tmp -Encoding ascii
    & $pose -m pip install -r $tmp; Need 'lock de pose'
    & $pose -m pip check
    Step 'Verificación de la GPU'
    & $pose -X utf8 research/doctor.py --torch --output research/qa/destino-pose.json
    & $pose -c "import sys,torch; sys.exit(0 if torch.cuda.is_available() else 1)"
    if ($LASTEXITCODE -ne 0) { throw "PyTorch no ve la GPU (ver research/qa/destino-pose.json). Revisar controlador e índice $TorchIndexUrl." }
}

if (-not $SkipGpuViewer) {
    Step '.venv-gpu (visor con onnxruntime-gpu; start_lab.ps1 -Gpu)'
    $gpu = Venv '.venv-gpu'
    & $gpu -m pip install -r requirements-gpu.txt -r requirements-ocr.txt; Need 'requisitos de .venv-gpu'
    & $gpu -m pip install --no-deps rapidocr==3.9.2; Need 'rapidocr en .venv-gpu'
    & $gpu -c "import onnxruntime as o; o.preload_dlls(); import sys; sys.exit(0 if 'CUDAExecutionProvider' in o.get_available_providers() else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'onnxruntime-gpu no ofrece CUDA en .venv-gpu' }
    # Encoder en float para la GPU (el int8 cae a CPU en CUDA); ver research/dequantize_encoder.py.
    & $eval -X utf8 research/dequantize_encoder.py; Need 'encoder fp16'
}

Step 'Pruebas rápidas sin navegador'
foreach ($t in 'qa_duel_engine.py', 'qa_live_tracking.py', 'qa_camera_source.py', 'qa_vision_pipeline.py', 'qa_server_loop.py') {
    Write-Host "-- $t"; & $eval -X utf8 $t | Select-Object -Last 1
}
Write-Host "`nListo. Arrancar el laboratorio: .\start_lab.ps1 -Live -Gpu (ajusta --camera a la IP del teléfono en esta red)." -ForegroundColor Green
