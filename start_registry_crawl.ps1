$projectRoot = $PSScriptRoot
$cacheDir = Join-Path $projectRoot 'data/registry/neuron'
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
if (Test-Path -LiteralPath (Join-Path $cacheDir 'STOP')) { throw 'Existe data/registry/neuron/STOP. Retira ese archivo cuando quieras reanudar.' }
$pidFile = Join-Path $runtimeDir 'registry-crawl.pid'
if (Test-Path -LiteralPath $pidFile) {
    $previousPid = [int](Get-Content -LiteralPath $pidFile)
    $previousProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$previousPid" -ErrorAction SilentlyContinue
    if ($previousProcess -and $previousProcess.CommandLine -like '*scrape_neuron.py*') { Write-Host "La descarga ya está activa: PID $previousPid"; exit 0 }
}
$pythonPath = Join-Path $projectRoot '.venv-eval/Scripts/python.exe'
$process = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','scrape_neuron.py','--details','--update-registry') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'registry-crawl.log') -RedirectStandardError (Join-Path $runtimeDir 'registry-crawl.error.log')
Set-Content -LiteralPath $pidFile -Value $process.Id
Write-Host "Descarga de historiales activa: PID $($process.Id). Progreso: data/registry/neuron/progress.json"
