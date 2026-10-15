param(
  [string]$From,
  [string]$To,
  [switch]$ForceGenerated
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
  Write-Host "Virtual environment not found. Run scripts\01_setup.ps1 first."
  exit 1
}

$args = @("-m", "mfblue.generate_asset_snapshots")
if ($From) {
  $args += @("--from", $From)
}
if ($To) {
  $args += @("--to", $To)
}
if ($ForceGenerated) {
  $args += "--force-generated"
}

Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  & $Python @args
} finally {
  Pop-Location
}

