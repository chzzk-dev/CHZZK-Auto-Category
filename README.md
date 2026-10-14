# CHZZK Auto Category

실행 중인 게임을 감지해 치지직 방송 카테고리를 자동으로 변경하는 Windows 앱입니다. 현재 앱 소스 버전은 **4.11.4**, Chrome 확장은 **0.5.3**입니다.

- 실행 프로세스 이름과 Discord 공개 게임 목록으로 감지합니다. Discord 로그인은 필요하지 않습니다.
- LoL 대기실과 게임 프로세스를 한 게임으로 묶고 보조 프로세스의 중복 등록을 줄입니다. LoL/TFT 자동 구분은 지원하지 않습니다.
- 트레이에서 백그라운드로 실행하며 처음 실행할 때 채널과 Chrome 확장 연결을 안내합니다.
- 배포 설치 파일은 **MSI**입니다. 설치·복구·제거용 WPF UI의 시작 및 최소 크기는 1200×820입니다.

## 설치와 사용

[최신 릴리스](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/latest)에서 MSI를 내려받아 설치하세요. 처음 시작하기 안내에서 채널 주소와 확장 연결을 설정한 뒤 자동 변경을 시작합니다.

Chrome 확장 소스는 `extension/`, 직접 설치용 파일은 `extension.zip`입니다. Chrome 웹 스토어 확장은 별도로 게시해야 합니다. 이 저장소에 ZIP을 올리는 것만으로 웹 스토어가 업데이트되지는 않습니다. 자세한 내용은 [WEBSTORE.md](WEBSTORE.md)를 참고하세요.

기존 EXE 설치본에서 전환할 때는 사용자 설정 삭제를 해제한 상태로 기존 앱을 제거하고 MSI를 설치하세요. MSI 업데이트는 기존 설정을 보존합니다.

## 개발과 빌드

Windows x64, 호환 Python x64, MSVC C++ Build Tools/Windows SDK, .NET 8 SDK가 필요합니다. GitHub Actions는 **Python 3.13 x64**를 사용합니다.

```bat
build_release.bat
```

앱과 업데이터를 Cython으로 컴파일하고 PyInstaller로 묶은 뒤 MSI와 릴리스 파일을 만듭니다. 설치 파일에 Python이 포함되므로 사용자 PC에 Python을 설치할 필요는 없습니다. [MSI_BUILD.md](MSI_BUILD.md)와 [BUILD_PROTECTION.md](BUILD_PROTECTION.md)를 참고하세요.

## 자동 빌드·배포와 변경 기록

[Windows workflow](.github/workflows/windows-release.yml)는 main 업로드와 PR에서 테스트와 MSI 빌드를 실행합니다. 숫자 버전 태그를 올리거나 수동 실행에서 `publish_release`를 선택하면 검증된 파일을 GitHub Release에 게시합니다.

릴리스마다 `RELEASE_NOTES-버전.md`를 만들고 같은 내용을 릴리스 설명에 넣습니다. 게시 성공 후에는 저장소의 [CHANGELOG.md](CHANGELOG.md)에 버전, 한국 시간 기준 날짜와 커밋 목록을 자동으로 기록합니다. `미배포` 항목에 적어 둔 변경 설명도 포함합니다.

공개 소스에는 Client Secret을 넣지 않습니다. 릴리스 빌드 전에 저장소 Actions secret `CHZZK_CLIENT_SECRET`을 설정하세요. 빌드할 때만 컴파일 대상에 주입하므로 사용자에게 ID/Secret 입력란을 표시하지 않습니다. 상세 절차는 [GITHUB_RELEASE.md](GITHUB_RELEASE.md)를 참고하세요.

## 설치 화면이 닫히는 경우

`diagnose_msi.bat`을 실행하면 MSI 종료 코드와 로그 위치를 확인할 수 있습니다. UI 초기화 로그는 `%LOCALAPPDATA%\ChzzkAutoCategory\logs\msi-ui-*.log`에 저장됩니다. CI는 실제 WPF 화면 로딩을 검사하며, 실제 설치 중 오류는 해당 Windows PC의 MSI 로그로 확인해야 합니다.
