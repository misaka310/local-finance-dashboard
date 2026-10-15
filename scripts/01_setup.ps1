$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Invoke-ProjectPython {
  param([string[]]$Arguments)

  $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
  if ($pyLauncher) {
    & py -3 @Arguments
    return
  }

  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand) {
    & python @Arguments
    return
  }

  throw "Python 3 was not found. Install Python 3 and enable PATH, then run this script again."
}

if (!(Test-Path ".venv")) {
  Invoke-ProjectPython @("-m", "venv", ".venv")
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt

$env:PYTHONPATH = Join-Path $Root "src"
& .\.venv\Scripts\python.exe -c "from mfblue.db import db, init_db; conn_cm=db(); conn=conn_cm.__enter__(); init_db(conn); conn_cm.__exit__(None, None, None); print('SQLite DB initialized.')"

Write-Host "Setup completed. Next run scripts/02_authorize_gmail.ps1"
