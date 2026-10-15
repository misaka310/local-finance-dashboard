@echo off

if not defined WT_SESSION (
  wt -w 0 new-tab -d "%CD%" cmd /k ""%~f0" %*"
  exit /b
)

set "ROOT=%~dp0"
cd /d "%ROOT%"

powershell.exe -NoExit -ExecutionPolicy Bypass -File ".\scripts\04_run_app.ps1"
