# Runs research/auto_cutout.py build in short fresh processes (600 cards each) until every
# target is done. Creating and freeing ONNX sessions for hours in one process ended once in a
# CUDA init error (28/09/2026); a new process per batch starts from a clean GPU state, and the
# build resumes from data/auto-sprites/index.json.
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root '.venv-gpu/Scripts/python.exe'
$log = Join-Path $root '.runtime/cutout-build.log'
for ($i = 0; $i -lt 40; $i++) {
    $p = Start-Process -FilePath $python -ArgumentList '-u', '-X', 'utf8', 'research/auto_cutout.py', 'build', '--limit', '600' -WorkingDirectory $root -NoNewWindow -Wait -PassThru -RedirectStandardOutput "$log.part" -RedirectStandardError (Join-Path $root '.runtime/cutout-build.err')
    Get-Content "$log.part" | Add-Content $log
    if ((Get-Content "$log.part" | Select-String 'pendientes 0 ')) { break }
    if ($p.ExitCode -ne 0) { Start-Sleep -Seconds 20 }
}
