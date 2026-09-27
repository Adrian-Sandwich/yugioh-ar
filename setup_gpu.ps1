<#
Arranque del laboratorio en la computadora con GPU (Windows, Python 3.14).

Crea los dos entornos, instala PyTorch para la GPU indicada y verifica con
research/doctor.py. No descarga datos ni modelos: la carpeta data/ y downloads/
llegan con el zip o por copia; las bases limpias están en transfer/<fecha>/.

  powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_gpu.ps1
  powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_gpu.ps1 -TorchIndexUrl https://download.pytorch.org/whl/cu126

Elegir el índice de PyTorch según el controlador NVIDIA instalado (nvidia-smi
muestra la versión de CUDA soportada): https://pytorch.org/get-started/locally/
#>
param(
    [string]$Python = 'python',
    [string]$TorchIndexUrl = 'https://download.pytorch.org/whl/cu128',
    [switch]$SkipPose,
    [switch]$RestoreDatabases
)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location $root

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

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

Step 'Entorno .venv-eval (visor, OCR, pruebas)'
if (-not (Test-Path '.venv-eval\Scripts\python.exe')) { & $Python -m venv .venv-eval }
& .\.venv-eval\Scripts\python.exe -m pip install --upgrade pip
& .\.venv-eval\Scripts\python.exe -m pip install -r requirements-research.txt -r requirements-ocr.txt
& .\.venv-eval\Scripts\python.exe -m pip install --no-deps rapidocr==3.9.2
& .\.venv-eval\Scripts\python.exe -m pip check
& .\.venv-eval\Scripts\python.exe -m playwright install msedge 2>$null

Step 'Verificación del entorno de visores'
& .\.venv-eval\Scripts\python.exe -X utf8 research/doctor.py --output research/qa/destino-visores.json

if (-not $SkipPose) {
    Step ".venv-pose (YOLO11) con PyTorch desde $TorchIndexUrl"
    if (-not (Test-Path '.venv-pose\Scripts\python.exe')) { & $Python -m venv .venv-pose }
    & .\.venv-pose\Scripts\python.exe -m pip install --upgrade pip
    # PyTorch primero, para la GPU; después el resto del lock sin sus líneas de torch.
    & .\.venv-pose\Scripts\python.exe -m pip install torch==2.14.0 torchvision==0.29.0 --index-url $TorchIndexUrl
    $lock = Get-Content requirements-pose-lock.txt | Where-Object { $_ -notmatch '^(torch|torchvision)==' }
    $tmp = Join-Path $env:TEMP 'pose-lock-sin-torch.txt'; $lock | Set-Content $tmp -Encoding ascii
    & .\.venv-pose\Scripts\python.exe -m pip install -r $tmp
    & .\.venv-pose\Scripts\python.exe -m pip check
    Step 'Verificación de la GPU'
    & .\.venv-pose\Scripts\python.exe -X utf8 research/doctor.py --torch --output research/qa/destino-pose.json
}

Step 'Pruebas rápidas sin navegador'
foreach ($t in 'qa_duel_engine.py', 'qa_live_tracking.py', 'qa_camera_source.py', 'qa_vision_pipeline.py') {
    Write-Host "-- $t"; & .\.venv-eval\Scripts\python.exe -X utf8 $t | Select-Object -Last 1
}
Write-Host "`nListo. Arrancar el laboratorio: .\start_lab.ps1 -Live (ajusta --camera a la IP del teléfono en esta red)." -ForegroundColor Green
