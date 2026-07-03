@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv was not found. Please run scripts\01_setup.ps1 first.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\12_export_readonly_html.ps1"
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Export failed.
    exit /b %ERRORLEVEL%
)

exit /b 0
