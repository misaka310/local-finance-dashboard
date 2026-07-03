$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$ClientSecret = Join-Path $Root "secrets\google_oauth_client.json"
if (!(Test-Path $ClientSecret)) {
  Write-Host "Google OAuth client JSON was not found."
  Write-Host "Save it here: $ClientSecret"
  exit 1
}

$env:PYTHONPATH = Join-Path $Root "src"
& .\.venv\Scripts\python.exe -m mfblue.auth authorize
