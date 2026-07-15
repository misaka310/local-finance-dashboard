@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& { $ErrorActionPreference = 'Stop'; & '.\scripts\01_setup.ps1'; & '.\scripts\05_seed_sample_data.ps1'; & '.\scripts\04_run_app.ps1' }"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Sample launch failed with exit code %EXIT_CODE%.
  pause
)

exit /b %EXIT_CODE%
