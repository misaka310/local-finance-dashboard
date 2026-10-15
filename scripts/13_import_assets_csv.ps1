param(
  [Parameter(Position=0)]
  [string[]]$Path,
  [string]$ValuationDate,
  [string]$Institution = "SBI証券",
  [string]$AccountType = "新NISA",
  [string]$AssetType = "investment_trust"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
  Write-Host "Virtual environment not found. Run scripts\01_setup.ps1 first."
  exit 1
}

if (!$Path -or $Path.Count -eq 0) {
  $Path = @("data/imports/assets/*.csv")
}

$args = @("-m", "mfblue.import_assets_csv")
$args += $Path
if ($ValuationDate) {
  $args += @("--valuation-date", $ValuationDate)
}
$args += @("--institution", $Institution)
$args += @("--account-type", $AccountType)
$args += @("--asset-type", $AssetType)

Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  & $Python @args
} finally {
  Pop-Location
}
