$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$ReadyUrl = "http://127.0.0.1:8787/readyz"
$ListenUrl = "ws://127.0.0.1:8787"
$AppServerPort = 8787
$PythonExe = Join-Path $Root ".venv\\Scripts\\python.exe"

function Resolve-CodexCommandPath {
  $cmd = Get-Command "codex.cmd" -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }
  $fallback = Get-Command "codex" -ErrorAction SilentlyContinue
  if ($fallback) {
    return $fallback.Source
  }
  throw "codex command was not found. Install Codex CLI and ensure it is on PATH."
}

function Test-AnalysisDependencies {
  if (!(Test-Path $PythonExe)) {
    throw ".venv was not found. Run scripts\\01_setup.ps1 first."
  }
  try {
    & $PythonExe -c "import websocket" | Out-Null
  } catch {
    throw "websocket-client is missing. Run scripts\\01_setup.ps1 again."
  }
}

function Test-CodexAppServerReady {
  param(
    [int]$TimeoutSec = 2
  )
  try {
    $res = Invoke-WebRequest -Uri $ReadyUrl -Method Get -TimeoutSec $TimeoutSec -UseBasicParsing
    return $res.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Get-PortOwners {
  param(
    [int]$Port
  )
  $connections = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -gt 0 })
  if ($connections.Count -eq 0) {
    return @()
  }

  $owners = @()
  foreach ($conn in $connections) {
    $ownerPid = [int]$conn.OwningProcess
    $procName = "<unknown>"
    try {
      $procName = (Get-Process -Id $ownerPid -ErrorAction Stop).ProcessName
    } catch {
      $procName = "<exited>"
    }
    $owners += [PSCustomObject]@{
      PID = $ownerPid
      ProcessName = $procName
      LocalAddress = $conn.LocalAddress
      State = $conn.State
    }
  }

  return $owners | Sort-Object PID, LocalAddress, State -Unique
}

function Stop-ProcessesUsingPort {
  param(
    [int]$Port
  )
  $owners = @(Get-PortOwners -Port $Port)
  if ($owners.Count -eq 0) {
    Write-Host "No existing process is using port $Port."
    return
  }

  Write-Host "Found existing process(es) on port ${Port}:"
  foreach ($owner in $owners) {
    Write-Host ("  PID={0} Name={1} LocalAddress={2} State={3}" -f $owner.PID, $owner.ProcessName, $owner.LocalAddress, $owner.State)
  }

  $targetPids = $owners | Select-Object -ExpandProperty PID -Unique
  foreach ($targetPid in $targetPids) {
    try {
      $proc = Get-Process -Id $targetPid -ErrorAction Stop
      Stop-Process -Id $targetPid -Force -Confirm:$false -ErrorAction Stop
      Write-Host ("Stopped PID={0} Name={1}" -f $targetPid, $proc.ProcessName)
    } catch {
      throw "Failed to stop PID=$targetPid using port $Port. $($_.Exception.Message)"
    }
  }

  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 300
    if ((Get-PortOwners -Port $Port).Count -eq 0) {
      Write-Host "Port $Port is now free."
      return
    }
  }
  throw "Port $Port is still in use after stop attempts."
}

function Start-CodexAppServer {
  $codexCmd = Resolve-CodexCommandPath
  Write-Host "Starting Codex App Server on $ListenUrl ..."
  $proc = Start-Process -FilePath $codexCmd -ArgumentList @("app-server", "--listen", $ListenUrl) -WorkingDirectory $Root -WindowStyle Hidden -PassThru

  $started = $false
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Seconds 1
    if ($proc.HasExited) {
      throw "Codex App Server process exited before ready. Start scripts\\10_run_codex_app_server.ps1 directly and check logs."
    }
    if (Test-CodexAppServerReady -TimeoutSec 2) {
      $started = $true
      break
    }
  }

  if (-not $started) {
    throw "Codex App Server did not become ready at $ReadyUrl."
  }

  Write-Host "Codex App Server is ready."
}

Test-AnalysisDependencies
Stop-ProcessesUsingPort -Port $AppServerPort
Start-CodexAppServer

& (Join-Path $PSScriptRoot "04_run_app.ps1")
