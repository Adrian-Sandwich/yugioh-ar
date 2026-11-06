# Opens the YgoAR editor with Unreal's MCP server (Claude Code's `unreal-mcp` connection, port 8000).
# The plugins are enabled here and not in YgoAR.uproject, so -game runs stay light and nothing about
# them reaches the project. Close the editor before Build.bat: Live Coding blocks it while it is open.
#   .\editor_mcp.ps1            with its window
#   .\editor_mcp.ps1 -Hidden    without one (the server only listens on 127.0.0.1)
param([switch]$Hidden, [int]$Port = 8000)
$editor = 'C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor.exe'
$project = (Resolve-Path (Join-Path $PSScriptRoot '..\YgoAR.uproject')).Path
$arguments = @("`"$project`"", '-EnablePlugins=ModelContextProtocol,AllToolsets,LiveCodingToolset',
    '-ModelContextProtocolStartServer', "-ModelContextProtocolPort=$Port", '-nosplash')
if ($Hidden) { $arguments += '-RenderOffScreen', '-unattended' }
$process = Start-Process -FilePath $editor -ArgumentList $arguments -PassThru
"Editor $($process.Id); MCP en http://127.0.0.1:$Port/mcp"
