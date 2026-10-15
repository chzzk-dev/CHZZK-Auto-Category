# GitHub MSI 배포

배포 저장소는 https://github.com/chzzk-dev/CHZZK-Auto-Category 입니다. `.github/workflows/windows-release.yml`을 사용합니다.

현재 소스는 앱 4.12.7 / 확장프로그램 0.6.0입니다. 사용자 승인에 따라 정식 최신 릴리스로 게시합니다. 모든 Windows 검증 게이트가 통과해야 게시됩니다.

## 최초 설정

저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 `CHZZK_CLIENT_ID`와 `CHZZK_CLIENT_SECRET`을 각각 등록하세요. workflow는 두 값 모두 Actions Secret에서 읽습니다. Secret 값은 소스, 커밋, Markdown에 쓰지 않습니다.

Secret이 없는 일반 빌드도 테스트 및 MSI 생성은 가능합니다. 그 빌드에는 공식 API 연결 정보가 포함되지 않습니다. 실제 릴리스 게시에는 두 Secret 설정이 모두 필수입니다. 앱 설정 화면에 ID/Secret 입력란은 추가하지 않습니다.

## 새 버전 게시

기존 `4.11.5`는 업데이터 복구를 위한 수동 설치용 사전 릴리스입니다. `version.py`의 `RELEASE_PRERELEASE = True`를 사용하며 Latest로 지정하지 않습니다. 기존 앱이 조회하는 `/releases/latest`에 포함되지 않으므로 자동 업데이트 오류를 다시 유발하지 않습니다. 사용자는 MSI를 한 번 직접 설치해 업데이터를 교체합니다. 이후 정식 업데이트를 배포할 때는 버전을 올리고 `RELEASE_PRERELEASE = False`로 설정하세요.

1. `version.py`의 `APP_VERSION`을 기존 배포보다 높은 세 자리 버전으로 수정합니다.
2. `CHANGELOG.md`의 `## 미배포`에 사용자가 이해할 변경 사항을 적고 main에 업로드합니다.
3. main 업로드로 시작한 Windows 빌드와 검증이 성공하면 새 버전을 GitHub Release에 자동 게시합니다. 수동으로 시작하려면 Actions → **Windows MSI Build and Release** → **Run workflow**에서 main과 `publish_release = true`를 선택합니다. version은 비워 두거나 소스와 같은 버전을 입력합니다. 또는 `v4.11.5`와 같은 태그를 올립니다. 기존 형식 `4.11.5`도 지원합니다.

main 업로드는 소스 버전이 모든 공개 정식 릴리스보다 높을 때 빌드 후 자동 배포합니다. 이미 배포된 버전이면 기본적으로 빌드만 진행합니다. PR과 기본 수동 실행도 빌드만 합니다. 일반적인 업데이트는 `APP_VERSION`을 먼저 올리세요.

같은 버전의 재배포를 명시적으로 요청한 경우에만 main 커밋 제목에 `[rebuild-release]`를 넣거나 수동 실행에서 `publish_release`와 `rebuild_release`를 함께 선택합니다. 더 높은 정식 버전이 있으면 교체할 수 없습니다. 모든 검증 후 동일 태그의 MSI·체크섬·메타데이터를 함께 교체하며, 태그도 검증한 소스 커밋으로 이동합니다. 태그가 다른 작업으로 바뀌면 게시를 중단합니다. 기존 버전의 변경 기록은 해당 버전 섹션에 추가합니다. 같은 버전이 설치된 사용자는 새 MSI를 직접 다시 설치해야 합니다. 앱 자동 업데이트는 버전이 더 높을 때 동작합니다.

## 자동 처리

- Python 3.13 x64 앱·업데이터 컴파일, 회귀 테스트, MSI 빌드.
- 새 후보: 확장프로그램 모의 통신, Qt 4배율 화면 렌더링, 실제 패키징 EXE의 오프라인 UI·아이콘 검증.
- UI와 Custom Action의 DTF 래퍼 분리 검사, 설치 상태 검사, 실제 WPF 화면 로딩 검사.
- MSI, `SHA256SUMS.txt`, `latest.json`, `RELEASE_NOTES-버전.md`, `CHANGELOG.md` 생성.
- 임시 릴리스에 파일을 업로드한 뒤 공개 릴리스로 전환합니다.
- 게시가 완료되면 main의 `CHANGELOG.md`에 기록하는 별도 커밋을 만듭니다. 빌드만 성공한 경우에는 배포 기록을 남기지 않습니다.

자동 기록은 `미배포` 설명과 이전 버전 이후의 커밋 제목을 사용합니다. 커밋 제목을 사용자가 읽을 수 있게 작성하세요. 릴리스 이후 main에 새로운 변경이 들어왔다면 해당 `미배포` 설명을 지우지 않습니다. 브랜치 보호로 자동 기록 커밋이 거부될 경우 Actions 오류에 표시되며, 릴리스에 포함된 Markdown으로 기록을 복구할 수 있습니다.

앱 업데이터는 최신 릴리스의 MSI와 SHA256을 확인합니다. `latest.json`의 다운로드 URL과 릴리스 노트 URL은 실제 태그를 사용합니다. Chrome 웹 스토어 배포는 이 workflow에 포함되지 않습니다.

## 로컬 빌드

같은 빌드 환경에서 환경변수 `CHZZK_CLIENT_ID`와 `CHZZK_CLIENT_SECRET`을 설정한 뒤 `build_release.bat`을 실행합니다. 결과는 `website/downloads/`에 생성됩니다. 로컬 빌드는 저장소의 `CHANGELOG.md`에 배포 완료 기록을 쓰지 않습니다.

진단 로그 업로드는 보호된 Python/C 소스를 포함하지 않습니다. 컴파일로 원본 확인을 어렵게 만들 수 있지만 배포 앱에 포함된 Secret의 추출을 완전히 막을 수는 없습니다.
