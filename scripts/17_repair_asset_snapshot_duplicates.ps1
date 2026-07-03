param(
  [string]$VerifyMonth,
  [int]$ExpectTotal
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
  Write-Host "Virtual environment not found. Run scripts\01_setup.ps1 first."
  exit 1
}

$args = @("-m", "mfblue.repair_asset_snapshot_duplicates")
if ($VerifyMonth) {
  $args += @("--verify-month", $VerifyMonth)
}
if ($PSBoundParameters.ContainsKey("ExpectTotal")) {
  $args += @("--expect-total", $ExpectTotal)
}

Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  & $Python @args
} finally {
  Pop-Location
}

