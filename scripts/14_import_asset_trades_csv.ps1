param(
  [Parameter(Position=0)]
  [string[]]$Path
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
  Write-Host "Virtual environment not found. Run scripts\01_setup.ps1 first."
  exit 1
}

if (!$Path -or $Path.Count -eq 0) {
  $Path = @("data/imports/assets/trades/*.csv")
}

$args = @("-m", "mfblue.import_asset_trades_csv")
$args += $Path

Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  & $Python @args
} finally {
  Pop-Location
}

