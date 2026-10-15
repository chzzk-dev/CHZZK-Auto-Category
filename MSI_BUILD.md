# 4.12.6 정식 MSI 전용 빌드

현재 로컬 소스는 4.12.6 정식 릴리스 빌드 대상입니다. GitHub 자동 빌드와 배포 기록은 [GITHUB_RELEASE.md](GITHUB_RELEASE.md)를 참고하세요. 배포용 설치 파일은 MSI 하나이며 서명 기능은 추가하지 않았습니다.
앱 자체는 기존 Python → Cython → PyInstaller 빌드를 유지합니다. MSI 안에 앱 EXE, 업데이트 보조 EXE, `_internal`이 들어가므로 사용자에게 Python 설치가 필요하지 않습니다.
전용 설치 화면은 C# WPF / .NET Framework 4.8 모듈입니다. .NET 8 SDK는 빌드 PC에서만 사용하고, 사용자 PC에는 .NET Framework 4.8이 필요합니다. 앱 본체는 Python을 유지합니다.

## 빌드 PC 준비

- Windows x64, 기존에 사용하던 호환 Python x64. Python 3.12를 요구하지 않습니다.
- 기존 MSVC C++ Build Tools와 Windows SDK.
- 추가로 **.NET 8 SDK x64**: https://dotnet.microsoft.com/download/dotnet/8.0
- 최초 빌드 시 Python 패키지와 WiX 다운로드를 위한 인터넷 연결.

WiX CLI와 UI/Util 확장은 재현성을 위해 **5.0.2**로 고정합니다. 최신 버전을 의미하지 않습니다.
빌드 스크립트가 프로젝트의 `build/wix-5.0.2`에 설치하며 전역 WiX 설치는 변경하지 않습니다.
툴 실행에는 .NET 8로의 major roll-forward를 사용합니다.
이 버전의 MS-RL 안내: https://www.nuget.org/packages/wix/5.0.2
WiX UI 원본을 수정한 `installer/msi/SetupUI.wxs`와 해당 MS-RL 전문 `WIX-LICENSE.txt`를 함께 제공합니다.
빌드 시 `installer/modern-ui/ChzzkInstallerUI.csproj`와 `installer/custom-actions/ChzzkInstallerActions.csproj`를 각각 컴파일합니다.
DTF 5.0.2는 UI와 Custom Action 진입점이 같은 어셈블리에 있으면 빌드를 거부합니다. 따라서 UI 래퍼 `ChzzkInstallerUI.CA.dll`과 완료 통지 래퍼 `ChzzkInstallerActions.CA.dll`을 분리합니다.
UI DLL에는 MSI UI 진입점 3개만, 완료 통지 DLL에는 ReportCompleted만 있는지 빌드에서 검사합니다. 두 DLL은 MSI 내부에 포함되며 별도 배포 파일을 만들지 않습니다.
UI 프로젝트는 화면·상태·진단 소스를 명시적으로 지정하므로 덮어쓴 폴더에 예전 CompletionAction.cs가 남아 있어도 UI DLL에 포함되지 않습니다.
NuGet에서 .NET Framework 참조 어셈블리를 가져오므로 별도 Developer Pack 경로 설정을 요구하지 않습니다.

## 한 번에 빌드

```bat
build_release.bat
```

`build_msi.bat`도 같은 전체 빌드를 실행합니다. 앱과 업데이터를 이미 빌드했다면 `installer\build_installer.bat`으로 MSI만 다시 만들 수 있습니다.
`.venv`가 없으면 기존 `prepare_build.bat`이 `python -m venv .venv`로 만듭니다.

결과:

- `dist-installer/ChzzkAutoCategory-4.12.6.msi`
- `website/downloads/ChzzkAutoCategory-4.12.6.msi`
- `website/downloads/SHA256SUMS.txt`
- `website/downloads/latest.json`
- `website/downloads/RELEASE_NOTES-4.12.6.md`
- `build/release-notes/CHANGELOG.md`

Setup.exe, 앱 배포 ZIP, 별도 제거 EXE는 빌드·배포하지 않습니다. 개발용 소스 ZIP과 Chrome 확장 ZIP은 설치 패키지와 별개입니다.
기존 `installer/installer.py`, `uninstaller_app.py`는 이전 동작 참고용 소스로만 남아 있고 빌드 대상에서 제외했습니다.

## 4.11.3 DTF 진입점 오류 수정본

`CA and UI entry points cannot be in the same assembly` 오류를 수정했습니다. 버전은 4.11.3으로 유지합니다.
앱과 업데이터가 이미 빌드되었다면 수정본 ZIP의 `installer` 폴더를 기존 프로젝트에 덮어쓰고 아래 명령만 실행하세요.

```bat
installer\build_installer.bat
.venv\Scripts\python.exe release.py
```

첫 명령이 성공한 경우 두 번째 명령으로 배포 폴더의 MSI·체크섬·latest.json을 생성합니다.
새 폴더에서 시작한다면 기존처럼 `build_release.bat`으로 전체 빌드합니다.

## MSI 실행 직후 닫히는 경우 — Fix2

Windows 로그를 받기 전에는 실제 종료 원인을 확정할 수 없습니다. Fix2는 초기화 전체 예외 처리와 진단 기능을 보완한 소스입니다.
초기화 중 AppSearch를 직접 실행하는 대신 MSI 속성과 이전 설치 레지스트리를 읽고, AppSearch는 엔진의 정상 시퀀스에서 실행합니다.
관리 코드 초기화가 실패하면 로그와 안내를 남기고 기본 MSI UI로 전환합니다. WPF 리소스 이름도 명시했습니다.
CLR/DLL 로드 자체가 실패해 관리 코드에 진입하지 못하면 UI의 개인 로그가 없을 수 있으므로 MSI 전체 로그가 필요합니다.

수정본의 `installer` 폴더와 루트의 `diagnose_msi.bat`을 기존 프로젝트에 복사한 뒤 다음 순서로 실행합니다.

```bat
installer\build_installer.bat
diagnose_msi.bat
```

진단 BAT은 MSI 종료 후에도 콘솔을 유지하고 종료 코드와 `%TEMP%\chzzk-msi-*.log` 경로를 표시합니다.
관리 UI 로그는 `%LOCALAPPDATA%\ChzzkAutoCategory\logs\msi-ui-*.log`입니다.
직접 MSI 경로를 지정하거나 MSI 파일을 BAT에 끌어놓아 실행할 수 있습니다.

```bat
diagnose_msi.bat "dist-installer\ChzzkAutoCategory-4.12.6.msi" native
```

위 명령은 Fix2의 관리 UI 초기화를 건너뛰고 기본 MSI 화면으로 진행하는 진단 옵션입니다. DLL 로드 전 실패에는 적용되지 않을 수 있습니다.
관리 UI 전체를 건너뛰는 임시 설치는 다음처럼 `/passive`를 사용할 수 있습니다. 이 경우 설치 후 앱을 시작 메뉴에서 직접 실행합니다.

```bat
msiexec /i "dist-installer\ChzzkAutoCategory-4.12.6.msi" /passive /norestart /L*V "%TEMP%\chzzk-msi-passive.log"
```

## 설치와 최초 설정

기본 설치 위치는 `C:\Program Files\CHZZK Auto Category`이며 관리자 권한 요청이 나올 수 있습니다.
MSI에 모든 앱 파일을 포함하므로 설치 과정에서 GitHub ZIP을 다운로드하지 않습니다.
앱의 치지직·확장 연결 및 업데이트 확인에는 기존처럼 네트워크가 필요합니다.

MSI를 직접 실행하면 민트색·보라색 포인트, 궤도 그래픽, 단계 표시가 있는 한국어 전용 창에서 설치합니다.
설치 준비 화면의 프로그램 실행 체크가 켜진 상태로 성공 화면에서 시작하기를 누르면 최초 설정창을 엽니다.
이미 설정 완료된 사용자는 설정창을 다시 표시하지 않습니다. 자동화된 무인 설치에서는 앱을 자동으로 열지 않습니다.
전용 설치 창은 WPF의 논리 단위로 시작/최소 크기 1200×820이며 Windows 배율에 따라 실제 픽셀 크기가 달라집니다.
MSI를 다시 실행하면 복구·제거를 선택할 수 있고, 이 작업도 같은 전용 화면을 사용합니다.
Windows 설정에서 제거하거나 `/passive`, `/qn`으로 실행하면 Windows가 선택한 기본/무인 UI를 사용할 수 있습니다. 관리자 권한 확인 및 설치 소스 찾기는 Windows 창입니다.
기본 WiX UI도 폴백으로 유지합니다. 전용 UI 초기화가 관리 코드에 진입한 뒤 실패하면 오류를 기록하고 기본 UI로 전환하도록 예외를 처리합니다. CLR 자체 로드 실패 등은 실제 Windows 환경에서 별도로 확인해야 합니다.
Qt 업데이터도 같은 밝은 색상으로 맞췄고 시작 및 최소 크기 1200×820을 유지합니다.

## 기존 MSI에서 새 UI 버전 설치

`build_release.bat`으로 4.11.3를 빌드한 뒤 새 MSI를 실행하면 이전 MSI를 업그레이드합니다.
앱을 트레이에서 완전히 종료한 상태로 설치해 주세요. 사용자 설정은 유지합니다.
기존 설치된 앱 목록·시작 메뉴 아이콘 수정도 포함합니다.
탐색기의 MSI 파일 자체는 Windows 기본 설치 아이콘으로 표시됩니다.

## 기존 EXE 설치본에서 처음 전환

1. 트레이에서 앱을 완전히 종료합니다.
2. Windows 설정 → 앱에서 기존 CHZZK Auto Category를 제거합니다.
3. 기존 제거 창의 **사용자 설정, 게임 규칙, 캐시와 로그도 함께 삭제** 체크를 반드시 해제합니다. 기존 버전의 기본값은 체크되어 있습니다.
4. 새 MSI를 설치합니다.

기존 제거기가 나중에 MSI 관리 파일까지 삭제하지 않도록, MSI는 기존 EXE 설치 등록이 남아 있으면 안내를 표시하고 중단합니다.
구버전 앱은 ZIP만 인식하므로 이 최초 전환은 수동 설치가 필요합니다.
이후 MSI 버전끼리는 동일 UpgradeCode를 사용해 높은 버전으로 업그레이드합니다.
동일 버전 재배포 대신 다음 수정에는 `version.py`의 APP_VERSION을 올린 뒤 빌드하세요.

## 업데이트와 제거

앱이 최신 릴리스의 `ChzzkAutoCategory-<버전>.msi`를 찾고 업데이터로 넘깁니다.
업데이터는 MSI를 다운로드하고 SHA-256을 필수 검증한 뒤 `msiexec`를 실행합니다.
설치 폴더를 직접 삭제하거나 ZIP 파일을 덮어쓰지 않습니다. Windows Installer가 업그레이드와 실패 롤백을 관리합니다.
설치 취소·다른 설치 진행 중·일반 오류를 구분하고, 재부팅 필요 시 자동 재부팅이나 앱 재시작을 하지 않습니다.
설치 로그: `%LOCALAPPDATA%\ChzzkAutoCategory\logs\msi-update-*.log`.
업데이터는 일반 사용자로 실행하고 설치 시에만 Windows Installer가 승격을 요청하므로 앱 재시작도 원래 사용자 세션에서 수행합니다.

제거는 Windows 설정 → 앱에서 합니다. MSI가 설치 파일과 시작 메뉴 등록을 제거합니다.
사용자 설정·게임 규칙·캐시는 유지합니다. 현재 제거 실행 사용자의 자동 시작 등록도 정리합니다.
다른 Windows 사용자 프로필의 자동 시작 등록은 해당 사용자 설정에서 별도로 끌 수 있습니다.
Chrome 확장프로그램은 Chrome에서 별도로 제거합니다.

## 확장프로그램

확장 0.5.3은 팝업과 최초 설치 안내를 MSI 다운로드 페이지로 연결합니다.
`build_extension.bat`으로 웹스토어용 ZIP을 만들 수 있습니다.
확장은 기존 웹스토어 항목에 업데이트하고, 다운로드 사이트와 GitHub의 MSI 릴리스도 함께 반영하세요.

## 배포

GitHub Release 태그와 `version.py`의 버전을 일치시키고 위 MSI, SHA256SUMS.txt, latest.json 3개 파일을 업로드합니다.
다운로드 페이지 변경도 적용하려면 `website` 내용을 정적 사이트에 반영합니다.
`.github/workflows/windows-release.yml`도 MSI만 산출하도록 변경했습니다. 수동 실행의 게시 옵션 기본값은 꺼져 있습니다.
이미 게시된 예전 Release 자산은 자동 삭제하지 않습니다. 같은 태그에 구형 Setup.exe/ZIP이 남아 있으면 배포 시 직접 정리하세요.

## 화면 미리보기

`installer/modern-ui/design-preview.html`을 브라우저에서 열면 설치 준비·진행·완료·복구/제거·오류 화면을 확인할 수 있습니다.
HTML은 디자인 시안이며 실제 MSI를 설치하거나 프로그램을 실행하지 않습니다. 실제 배포 UI는 `SetupWindow.xaml`과 C# 코드입니다.

## 검증 범위

초기 MSI 전환에서 회귀 테스트 70개, Python·다운로드 JavaScript 구문 검사 및 GitHub Actions YAML 파싱을 확인했습니다.
4.11.2 아이콘 수정에서는 아이콘 참조 검사와 기존 MSI 테스트 13개, 수정 Python 파일 구문 검사를 통과했습니다.
4.11.3에서는 .NET Framework 4.8 대상 UI 관리 DLL 컴파일, 설치 상태 검증 18개, MSI 구성·업데이트 테스트 14개 및 XAML 컨트롤 참조 검사를 수행했습니다.
진입점 오류 수정본에서는 UI/Custom Action 관리 DLL을 각각 .NET Framework 4.8 대상으로 컴파일하고, 컴파일된 메타데이터에서 UI DLL은 IEmbeddedUI 1개/Custom Action 0개, 완료 DLL은 UI 0개/Custom Action 1개인지 확인했습니다.
MSI 구성·업데이트 테스트 17개가 통과했습니다. Windows 네이티브 래퍼 생성과 실제 MSI 설치는 이 환경에서 실행하지 못했습니다.
HTML 디자인 시안의 한국어 렌더링·화면 전환도 별도로 검사했습니다. WPF 창을 Windows에서 실행한 스크린샷은 아닙니다.
실제 MSI 파일을 생성한 결과가 아니라 관리 DLL 컴파일, 소스와 모의 동작 검증 결과입니다.

제공된 테스트는 MSI 구성 XML, 전체 파일 포함, 안정된 컴포넌트 GUID, 구 설치본 감지,
MSI 릴리스 선택, 체크섬 불일치/누락 차단, 설치 실패 시 직접 파일 삭제 방지, MSI 결과 코드 처리를 검증합니다.
Windows용 네이티브 빌드, WiX 링크/ICE 검증, 실제 설치·업그레이드·제거는 Windows에서 추가 확인해야 합니다.
Windows Sandbox에서 신규 설치 → 최초 설정 → 재실행 → 높은 버전 설치 → 취소/복구 → 제거 순서로 확인해 주세요.

## 1639 업데이트 오류

4.11.5는 공백이 있는 설치 경로의 MSI 명령 인수를 수정합니다. 기존 업데이터에서 1639가 발생하면 수정본 MSI를 직접 실행해 한 번 업데이트하세요. 기존 설치를 먼저 제거할 필요가 없습니다. 설치된 새 업데이터부터 수정한 인수를 사용합니다. CI에서는 기존 명령의 1639 재현, 수정 명령으로의 실제 설치·업그레이드·제거 및 설정 보존을 검사합니다.
