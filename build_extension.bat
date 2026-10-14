@echo off
setlocal
cd /d "%~dp0"

if not exist "extension\manifest.json" (
    echo extension\manifest.json not found.
    exit /b 1
)

if not exist "dist-webstore" mkdir "dist-webstore"
if exist "dist-webstore\CHZZK-Auto-Category-Bridge.zip" del /q "dist-webstore\CHZZK-Auto-Category-Bridge.zip"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path 'extension\*' -DestinationPath 'dist-webstore\CHZZK-Auto-Category-Bridge.zip' -CompressionLevel Optimal"

if errorlevel 1 exit /b 1

echo.
echo Created: dist-webstore\CHZZK-Auto-Category-Bridge.zip
endlocal
