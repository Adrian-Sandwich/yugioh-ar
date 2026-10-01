param([switch]$Live, [switch]$Gpu, [switch]$Full, [switch]$Review)
# -Review: también el revisor de recortes en la red de casa (review_server.py --lan, puerto 8770).
# -Full: reconocer todo el catálogo (data/full, catalog.export_full) en lugar del piloto.
if ($Full) { $env:YUGIOH_SCOPE = 'full' }
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
if ($Gpu) {
    # Detector y encoder en CUDA (encoder fp16 descuantizado, ver research/dequantize_encoder.py).
    $pythonPath = Join-Path $projectRoot '.venv-gpu/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Falta .venv-gpu. Instalar con requirements-gpu.txt (ver docs/ARRANQUE_GPU.md).' }
    $env:YUGIOH_ONNX_DEVICE = 'cuda'
} else {
    $pythonPath = Join-Path $projectRoot '.venv-eval/Scripts/python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Falta .venv-eval. Consulta research/ENTREGA_PILOTO.md para instalarlo.' }
}
function Start-LabService($name, $port, $arguments, $python = $pythonPath) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); Write-Host "Puerto $port ya ocupado; no se inicia otra instancia de $name."; return }
    catch { }
    finally { $client.Dispose() }
    # supervise.py restarts the service if it dies and turns on faulthandler (see its docstring).
    $process = Start-Process -FilePath $python -ArgumentList (@('supervise.py', $name, '--') + $arguments) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "$name.log") -RedirectStandardError (Join-Path $runtimeDir "$name.error.log")
    Write-Host "$name iniciado (PID $($process.Id)). http://127.0.0.1:$port"
}
Start-LabService 'catalog' 8768 @('catalog_server.py', '--port', '8768')
if (Test-Path -LiteralPath (Join-Path $projectRoot 'data/registry/registry.sqlite')) { Start-LabService 'registry' 8769 @('registry_server.py', '--port', '8769') }
Start-LabService 'demo' 8767 @('camera_viewer.py', '--backend', 'embedding', '--ar', '--port', '8767', '--image', 'data/captures/carta-2026-09-25T04-13-54-278Z.jpg')
if ($Live) { Start-LabService 'camera' 8765 @('camera_viewer.py', '--backend', 'embedding', '--ar', '--port', '8765') }
if ($Review) {
    # SAM 2 refines the drawn corrections when .venv-sam exists (PLAN_3D_Y_REVISION.md); else GrabCut.
    $samPython = Join-Path $projectRoot '.venv-sam/Scripts/python.exe'
    if (Test-Path -LiteralPath $samPython) { Start-LabService 'review' 8770 @('-X', 'utf8', 'review_server.py', '--refiner', 'sam2', '--lan') $samPython }
    else { Start-LabService 'review' 8770 @('-X', 'utf8', 'review_server.py', '--lan') }
}
