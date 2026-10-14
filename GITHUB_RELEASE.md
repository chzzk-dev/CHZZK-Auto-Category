# GitHub MSI 배포

배포 저장소는 https://github.com/chzzk-dev/CHZZK-Auto-Category 입니다. `.github/workflows/windows-release.yml`을 사용합니다.

## 최초 설정

저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 `CHZZK_CLIENT_SECRET`을 등록하세요. Secret 값은 소스, 커밋, Markdown에 쓰지 않습니다. Client ID는 공개 소스의 고정값을 사용하며 변경하려면 Actions variable `CHZZK_CLIENT_ID`를 설정합니다.

Secret이 없는 일반 빌드도 테스트 및 MSI 생성은 가능합니다. 그 빌드에는 공식 API 연결 정보가 포함되지 않습니다. 실제 릴리스 게시에는 Secret 설정이 필수입니다. 앱 설정 화면에 ID/Secret 입력란은 추가하지 않습니다.

## 새 버전 게시

1. `version.py`의 `APP_VERSION`을 기존 배포보다 높은 세 자리 버전으로 수정합니다.
2. `CHANGELOG.md`의 `## 미배포`에 사용자가 이해할 변경 사항을 적고 main에 업로드합니다.
3. Actions → **Windows MSI Build and Release** → **Run workflow**에서 main과 `publish_release = true`를 선택합니다. version은 비워 두거나 소스와 같은 버전을 입력합니다. 또는 main의 검증된 커밋에 `v4.11.4`와 같은 태그를 올립니다. 기존 형식 `4.11.4`도 지원합니다.

main/PR 업로드와 기본 수동 실행은 빌드만 합니다. 태그 또는 게시 옵션을 선택한 수동 실행이 실제 배포입니다. 동일하거나 낮은 버전, 소스와 다른 버전·태그는 거부합니다. 게시한 릴리스의 파일을 덮어쓰지 않습니다.

## 자동 처리

- Python 3.13 x64 앱·업데이터 컴파일, 회귀 테스트, MSI 빌드.
- UI와 Custom Action의 DTF 래퍼 분리 검사, 설치 상태 검사, 실제 WPF 화면 로딩 검사.
- MSI, `SHA256SUMS.txt`, `latest.json`, `RELEASE_NOTES-버전.md`, `CHANGELOG.md` 생성.
- 임시 릴리스에 파일을 업로드한 뒤 공개 릴리스로 전환합니다.
- 게시가 완료되면 main의 `CHANGELOG.md`에 기록하는 별도 커밋을 만듭니다. 빌드만 성공한 경우에는 배포 기록을 남기지 않습니다.

자동 기록은 `미배포` 설명과 이전 버전 이후의 커밋 제목을 사용합니다. 커밋 제목을 사용자가 읽을 수 있게 작성하세요. 릴리스 이후 main에 새로운 변경이 들어왔다면 해당 `미배포` 설명을 지우지 않습니다. 브랜치 보호로 자동 기록 커밋이 거부될 경우 Actions 오류에 표시되며, 릴리스에 포함된 Markdown으로 기록을 복구할 수 있습니다.

앱 업데이터는 최신 릴리스의 MSI와 SHA256을 확인합니다. `latest.json`의 다운로드 URL과 릴리스 노트 URL은 실제 태그를 사용합니다. Chrome 웹 스토어 배포는 이 workflow에 포함되지 않습니다.

## 로컬 빌드

같은 빌드 환경에서 환경변수 `CHZZK_CLIENT_SECRET`을 설정한 뒤 `build_release.bat`을 실행합니다. 결과는 `website/downloads/`에 생성됩니다. 로컬 빌드는 저장소의 `CHANGELOG.md`에 배포 완료 기록을 쓰지 않습니다.

진단 로그 업로드는 보호된 Python/C 소스를 포함하지 않습니다. 컴파일로 원본 확인을 어렵게 만들 수 있지만 배포 앱에 포함된 Secret의 추출을 완전히 막을 수는 없습니다.
