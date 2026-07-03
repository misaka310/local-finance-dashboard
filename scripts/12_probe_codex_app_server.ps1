$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $python)) {
  throw ".venv が見つかりません。scripts\\01_setup.ps1 を先に実行してください。"
}

$env:PYTHONPATH = Join-Path $Root "src"
& $python -m mfblue.probe_codex_app_server @args
