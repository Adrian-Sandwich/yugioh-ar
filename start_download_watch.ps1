$projectRoot = $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv-eval/Scripts/python.exe'
$runtimeDir = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
$existing = Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like "*$projectRoot*watch_download.py*" -and $_.CommandLine -notlike '*--once*' }
if ($existing) { Write-Host 'El monitor de descarga ya esta activo.'; exit 0 }
$watcher = Start-Process -FilePath $pythonPath -ArgumentList @('-X','utf8','tools/watch_download.py') -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'download-watch.log') -RedirectStandardError (Join-Path $runtimeDir 'download-watch.error.log')
Write-Host "Monitor local iniciado: PID $($watcher.Id). Estado: .runtime/download-watch.json"
