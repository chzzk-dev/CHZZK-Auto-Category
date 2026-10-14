@echo off
setlocal
cd /d "%~dp0"
call prepare_build.bat
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe build_protected.py updater
if errorlevel 1 exit /b 1
endlocal
