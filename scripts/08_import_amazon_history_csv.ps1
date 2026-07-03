param(
  [Parameter(Position=0)]
  [string[]]$Path,
  [switch]$DryRun,
  [switch]$MoveImported,
  [string]$MoveImportedTo = "data/imports/amazon/imported"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
  Write-Host "Virtual environment not found. Run scripts\01_setup.ps1 first."
  exit 1
}

if (!$Path -or $Path.Count -eq 0) {
  Write-Host "引数未指定のため data/imports/amazon/*.csv を対象にします。古いCSV混入防止のため、可能ならファイルを明示指定してください。"
  $Path = @("data/imports/amazon/*.csv")
}

Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  $args = @("-m", "mfblue.import_amazon_history_csv")
  if ($DryRun) {
    $args += "--dry-run"
  }
  if ($MoveImported) {
    $args += "--move-imported"
    if ($MoveImportedTo) {
      $args += $MoveImportedTo
    }
  }
  $args += $Path
  & $Python @args
} finally {
  Pop-Location
}
