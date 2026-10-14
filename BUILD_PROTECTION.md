# 소스 분석 난이도를 높이는 빌드

## 준비

- Windows 10/11 x64, Python x64 (`python` 명령 사용 가능, 특정 Python 버전을 강제하지 않음)
- Visual Studio 2022 Build Tools의 **Desktop development with C++** 워크로드: MSVC v143 x64/x86 도구와 Windows SDK
- 선택한 Python은 `requirements-build.txt`의 빌드 도구와 실행 라이브러리가 지원하는 버전이어야 합니다. 호환되지 않으면 패키지 설치 단계에서 오류가 표시됩니다.
- 빌드 패키지 설치용 인터넷 연결. 일반 실행에 C++ 빌드 도구는 필요하지 않습니다.
- 최초 실행 시 `python -m venv .venv`로 가상환경을 만듭니다. 기존 `.venv`가 있으면 그대로 사용합니다. PC의 다른 Python으로 바꾸려면 기존 가상환경을 이름 변경한 뒤 다시 빌드하세요.

## Windows 경로 길이 주의

보호 빌드는 Cython/MSVC 중간 파일을 생성합니다. 0.5.0 수정본부터 Cython 소스·생성 C 파일·오브젝트 경로를 `build/protected/<target>` 기준의 상대 경로로 컴파일합니다. 따라서 프로젝트가 Desktop처럼 비교적 긴 경로에 있어도 절대 경로가 중간 산출물 경로에 반복 삽입되지 않습니다.

이전 방식에서 `objects\Release\Users\...\generated\Users\...`처럼 프로젝트 경로가 반복되어 MSVC `C1083: Cannot open compiler generated file: '': Invalid argument`가 발생했다면 이 수정본으로 다시 빌드하세요. 기존 `build/protected/` 폴더는 빌드 스크립트가 대상별로 정리합니다.

## 빌드

전체 배포 파일은 `build_release.bat`을 실행합니다. 각 명령은 컴파일 실패 시 종료하며 소스/바이트코드 빌드로 대체하지 않습니다.

| 명령 | 결과 |
| --- | --- |
| `build.bat` | `dist/ChzzkAutoCategory/ChzzkAutoCategory.exe`와 `_internal/` |
| `build_updater.bat` | `dist-updater/ChzzkAutoUpdater.exe` 및 앱 폴더 복사 |
| `build_uninstaller.bat` | MSI 제거 기능 사용 안내만 표시 |
| `installer/build_installer.bat` | `dist-installer/ChzzkAutoCategory-<version>.msi` |
| `build_release.bat` | 위 전체 빌드와 `website/downloads/` 배포 자산 생성 |

업데이터 빌드는 메인 앱 빌드 후 실행하세요. MSI 빌드는 .NET 8 SDK x64가 필요합니다. 상세 내용은 MSI_BUILD.md를 확인하세요. GitHub Actions는 `3.13` x64 환경에서 같은 보호 빌드 경로를 사용합니다. 소스 실행은 기존 `run.bat`을 사용합니다.

## 적용 범위

- 앱 자체 모듈은 Python → C → Windows 네이티브 `.pyd` 모듈로 컴파일합니다.
- 메인 진입점도 컴파일합니다. EXE에 남는 작은 Python 실행 코드는 컴파일된 진입점을 호출하는 로더입니다.
- 업데이터도 같은 방식입니다. 설치·제거는 MSI가 담당하며 별도 Setup/Uninstall EXE를 만들지 않습니다.
- MSI 전용 UI는 별도의 C# WPF 모듈입니다. Python 보호 빌드 대상은 아니며 치지직 인증 정보를 포함하지 않습니다.
- 컴파일된 모듈의 의존성을 추적해 PyInstaller에 전달합니다. `_internal` 폴더와 EXE 이름은 유지합니다.
- 패키징 전에 보호 대상이 Python 바이트코드로 포함되지 않고 네이티브 확장으로 포함되는지 검사합니다. 실패하면 빌드를 중단합니다.
- 문서 문자열, 소스 주석 포함, 프로파일링·라인 추적을 끄고 C 컴파일러 최적화를 사용합니다. 단순한 Base64 인코딩이나 변수 이름 변경 방식은 아닙니다.
- `build/protected/<target>/native-audit.json`에서 패키징 전 검사를 통과한 모듈 목록을 확인할 수 있습니다.

## 배포할 파일

사용자에게는 `website/downloads/`의 MSI를 제공합니다. MSI는 `dist/ChzzkAutoCategory`의 실행 파일과 라이브러리를 포함합니다. SHA256SUMS.txt와 latest.json도 릴리스에 함께 업로드합니다.

이 저장소는 공개 원본 소스입니다. 사용자 설치 파일은 MSI를 제공하고, `build/`의 인증 정보가 주입된 생성 C 코드·중간 파일과 가상환경은 업로드하지 않습니다. 공개 저장소의 Source code 다운로드에서는 원본 소스를 볼 수 있습니다. Client Secret은 Actions secret 또는 로컬 환경변수에서 컴파일 대상에만 주입합니다.

외부 라이브러리와 Python 실행 환경의 바이트코드는 포함될 수 있습니다. Chrome 확장프로그램의 JavaScript는 이번 Python 컴파일 대상이 아닙니다. 네이티브 컴파일은 소스 복원을 어렵게 하지만 바이너리 분석이나 포함된 문자열·Secret 추출을 완전히 차단하지 않습니다.

## 이전 보호 빌드 검증 기록

이번 MSI 변경의 검증 범위는 MSI_BUILD.md를 참고하세요. 아래는 이전 빌드의 기록입니다.

Linux 검증 환경에서 앱 자체 모듈 10개와 보조 프로그램 3개의 네이티브 컴파일 및 로딩을 확인했습니다. 컴파일된 메인 앱의 설정 화면·설정 저장·고정 인증 요청 모의 테스트, 게임 규칙/별칭/감지 대기 로직과 빌드 검사 5개 테스트도 통과했습니다. Linux PyInstaller 패키징도 완료했고, 자체 모듈 10개가 Python 바이트코드로 포함되지 않고 네이티브 확장으로 포함되는 패키징 전 검사를 통과했습니다.

Windows EXE 빌드와 Windows 설치·자동 업데이트 실동작은 별도 Windows 환경에서 확인해야 합니다. `--compile-only`는 개발용 네이티브 컴파일 검증이며 Windows EXE를 생성하지 않습니다.

## 참고 문서

- Cython 컴파일: https://cython.readthedocs.io/en/stable/src/userguide/source_files_and_compilation.html
- PyInstaller의 Cython 의존성 처리: https://pyinstaller.org/en/stable/feature-notes.html
