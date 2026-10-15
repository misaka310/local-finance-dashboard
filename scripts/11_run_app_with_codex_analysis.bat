@echo off
if not defined WT_SESSION (
  wt -w 0 new-tab -d "%CD%" cmd /k ""%~f0" %*"
  exit /b
)
setlocal

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%11_run_app_with_codex_analysis.ps1"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Launch failed with exit code %EXIT_CODE%.
  pause
)

exit /b %EXIT_CODE%
