@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"
set "CHZZK_MSI_PATH=%~1"
if not defined CHZZK_MSI_PATH if exist "dist-installer\ChzzkAutoCategory-4.11.4.msi" set "CHZZK_MSI_PATH=%CD%\dist-installer\ChzzkAutoCategory-4.11.4.msi"
if not defined CHZZK_MSI_PATH if exist "website\downloads\ChzzkAutoCategory-4.11.4.msi" set "CHZZK_MSI_PATH=%CD%\website\downloads\ChzzkAutoCategory-4.11.4.msi"
if not defined CHZZK_MSI_PATH if exist "ChzzkAutoCategory-4.11.4.msi" set "CHZZK_MSI_PATH=%CD%\ChzzkAutoCategory-4.11.4.msi"
if not defined CHZZK_MSI_PATH goto missing
if not exist "%CHZZK_MSI_PATH%" goto missing
set "CHZZK_MSI_LOG=%TEMP%\chzzk-msi-%RANDOM%-%RANDOM%.log"
echo MSI: "%CHZZK_MSI_PATH%"
echo 로그: "%CHZZK_MSI_LOG%"
if /i "%~2"=="native" goto native
start "" /wait "%SystemRoot%\System32\msiexec.exe" /i "%CHZZK_MSI_PATH%" /L*V "%CHZZK_MSI_LOG%"
goto result
:native
start "" /wait "%SystemRoot%\System32\msiexec.exe" /i "%CHZZK_MSI_PATH%" CHZZK_USE_NATIVE_UI=1 /L*V "%CHZZK_MSI_LOG%"
:result
set "CHZZK_MSI_RESULT=%errorlevel%"
echo.
echo 설치 종료 코드: %CHZZK_MSI_RESULT%
echo 설치 로그: "%CHZZK_MSI_LOG%"
echo 전용 UI 로그: "%LOCALAPPDATA%\ChzzkAutoCategory\logs\msi-ui-*.log"
echo 창이 닫히면 위 설치 로그 파일을 전달해 주세요.
pause
exit /b %CHZZK_MSI_RESULT%
:missing
echo MSI 파일이 없습니다. 먼저 installer\build_installer.bat을 실행해 주세요.
echo MSI 경로를 직접 지정하거나 파일을 이 BAT에 끌어놓을 수도 있습니다.
pause
exit /b 1
