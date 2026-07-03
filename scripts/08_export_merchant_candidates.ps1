$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
  Write-Host "Virtual environment not found. Run scripts\01_setup.ps1 first."
  exit 1
}
Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  & $Python -m mfblue.export_merchant_candidates
} finally {
  Pop-Location
}
