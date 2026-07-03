@echo off
setlocal

set "ROOT=%~dp0"
set "PS1=%ROOT%scripts\11_run_app_with_codex_analysis.ps1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Launch failed with exit code %EXIT_CODE%.
  pause
)

exit /b %EXIT_CODE%
