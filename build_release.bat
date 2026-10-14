@echo off
setlocal
cd /d "%~dp0"
where dotnet >nul 2>nul
if errorlevel 1 (
    echo Install the .NET 8 SDK x64, reopen the terminal, and retry.
    exit /b 1
)
echo [1/4] Building protected Windows app...
call build.bat
if errorlevel 1 exit /b 1
echo [2/4] Building MSI update helper...
call build_updater.bat
if errorlevel 1 exit /b 1
echo [3/4] Building MSI installer...
call installer\build_installer.bat
if errorlevel 1 exit /b 1
echo [4/4] Creating MSI release assets...
.venv\Scripts\python.exe release.py
if errorlevel 1 exit /b 1
echo.
echo Done. Output: website\downloads\ChzzkAutoCategory-*.msi
endlocal
