$ErrorActionPreference = "Stop"

Write-Host "Starting Codex App Server on ws://127.0.0.1:8787 ..."
codex app-server --listen ws://127.0.0.1:8787
