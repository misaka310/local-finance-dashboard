param(
  [Parameter(Mandatory=$true, Position=0)]
  [string[]]$Path
)

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
  & $Python -m mfblue.import_paypay_csv @Path
} finally {
  Pop-Location
}
