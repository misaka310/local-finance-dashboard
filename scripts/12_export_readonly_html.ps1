$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (!(Test-Path $Python)) {
  Write-Host ".venv was not found. Run scripts\\01_setup.ps1 first."
  exit 1
}

Push-Location $Root
try {
  $env:PYTHONPATH = Join-Path $Root "src"
  $env:PYTHONIOENCODING = "utf-8"
  & $Python -m mfblue.export_readonly_html
  if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
  }
} finally {
  Pop-Location
}

Write-Host ""
Write-Host "Read-only HTML export completed."
Write-Host "HTML: dist\\readonly\\mfblue_readonly.html"
Write-Host "ZIP : dist\\readonly\\mfblue_readonly.zip"
Write-Host ""
Write-Host "On Galaxy: unzip the archive and open mfblue_readonly.html."
