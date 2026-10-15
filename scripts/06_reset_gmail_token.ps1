$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root
$env:PYTHONPATH = Join-Path $Root "src"
& .\.venv\Scripts\python.exe -m mfblue.auth reset
