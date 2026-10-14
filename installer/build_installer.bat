@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
    echo Run build_release.bat first.
    exit /b 1
)
.venv\Scripts\python.exe installer\build_msi.py
if errorlevel 1 exit /b 1
endlocal
