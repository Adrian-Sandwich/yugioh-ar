param([switch]$Live)
$projectRoot = $PSScriptRoot
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$pythonPath = Join-Path $projectRoot '.venv-eval/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Falta .venv-eval. Consulta research/ENTREGA_PILOTO.md para instalarlo.' }
function Start-LabService($name, $port, $arguments) {
    $client = New-Object System.Net.Sockets.TcpClient
    try { $client.Connect('127.0.0.1', $port); Write-Host "Puerto $port ya ocupado; no se inicia otra instancia de $name."; return }
    catch { }
    finally { $client.Dispose() }
    $process = Start-Process -FilePath $pythonPath -ArgumentList $arguments -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir "$name.log") -RedirectStandardError (Join-Path $runtimeDir "$name.error.log")
    Write-Host "$name iniciado (PID $($process.Id)). http://127.0.0.1:$port"
}
Start-LabService 'catalog' 8768 @('catalog_server.py', '--port', '8768')
if (Test-Path -LiteralPath (Join-Path $projectRoot 'data/registry/registry.sqlite')) { Start-LabService 'registry' 8769 @('registry_server.py', '--port', '8769') }
Start-LabService 'demo' 8767 @('camera_viewer.py', '--backend', 'embedding', '--ar', '--port', '8767', '--image', 'data/captures/carta-2026-09-25T04-13-54-278Z.jpg')
if ($Live) { Start-LabService 'camera' 8765 @('camera_viewer.py', '--backend', 'embedding', '--ar', '--port', '8765') }
