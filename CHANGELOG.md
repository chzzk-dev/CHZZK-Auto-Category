# 변경 기록

릴리스를 게시하면 이 파일에 버전, 한국 시간 기준 날짜, 변경 사항과 커밋 링크가 자동으로 기록됩니다.
배포 전 사용자에게 설명할 내용은 아래 `미배포` 항목에 추가할 수 있습니다.

## 미배포

- 밝은 설치 UI와 공통 테마/아이콘을 사용하는 대시보드·게임 목록·자동화·연결·설정·로그 6개 페이지로 개편합니다.
- 게임별 검색·검증 상태와 적용 대기를 분리하며 수동 규칙, 시리즈/버전 구분, 종료된 게임의 지연 결과 차단을 강화합니다.
- Discord ID와 사용자 별칭을 유지하고 검증 캐시를 재사용합니다. LoL/TFT는 실행 파일만으로 추측하지 않습니다.
- 확장프로그램 0.6.0에서 실제 manifest 버전·프로토콜·heartbeat를 전달하며 오래된 응답과 중복 요청을 차단합니다.
- 앱 업데이트는 기본 3시간, 카테고리 동기화는 기본 6시간이며 두 자동 주기의 최소값은 1시간입니다.
- 설정 마이그레이션 원본 백업, 순환 로그와 민감 정보 마스킹, 단일 업데이터 잠금 및 실패 후 기존 앱 재실행 경로를 추가합니다.
- Windows CI에 Qt DPI 렌더링과 실제 보호 EXE의 오프라인 아이콘 검사를 추가합니다. 기존 MSI 설치·업그레이드·제거 검증은 유지합니다.
- 4.12.0은 사전 릴리스 후보입니다. GitHub 반영과 게시에는 사용자 승인이 필요하며 Chrome Web Store 게시와는 별개입니다.

## [4.11.5](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.11.5) — 2026-10-14 (KST)

### 변경 사항

- 4.11.5는 기존 업데이터의 반복 오류를 막기 위해 사전 릴리스로 게시합니다. 자동 업데이트에는 노출되지 않으며 MSI를 직접 설치해야 합니다.
- 공백이 있는 설치 경로의 MSI 인수 따옴표 처리를 수정해 자동 업데이트의 오류 1639를 해결합니다.
- Windows CI에서 실제 MSI 설치·업그레이드·제거와 사용자 설정 보존을 확인한 뒤 릴리스합니다.
- 기존 업데이터에 이 오류가 있는 경우 이번 수정본 MSI를 한 번 직접 실행해 업데이트하세요.

### 커밋

- test: validate invalid MSI property syntax without interactive error dialogs ([cdc297a](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/cdc297acab043d18d7965b4b3377a6f3b8716a24))
- ci: publish the updater repair as a manual prerelease \[cancel obsolete builds\] ([8bc2d0f](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/8bc2d0f8f310eff8f476885ccb6a2ad74adb264c))
- test: select an available stable MSI baseline and verify both updated executables ([ab79759](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/ab797597bc9c9e285310ee59a3dd9185a2c94e9e))
- fix: quote MSI property values correctly and verify real upgrades for 4.11.5 ([bce1ed8](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/bce1ed8e740250b72a9129ce5559ab63b497e046))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.11.4...v4.11.5)

### 설치 파일

- `ChzzkAutoCategory-4.11.5.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.11.4](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.11.4) — 2026-10-14 (KST)

### 변경 사항

- 새 버전을 main에 업로드하면 Windows 검증 후 MSI와 변경 기록을 GitHub Release에 자동 게시합니다.
- 자동 감지 대기 목록에 새 게임이 추가되면 알림음을 재생합니다. 같은 게임의 반복 감지와 LoL 대기실·게임 전환에는 중복 재생하지 않습니다.
- 설정에서 대기 목록 알림음을 켜거나 끌 수 있습니다. 기존 사용자도 기본으로 활성화됩니다.
- Python 앱과 Chrome 확장 소스를 저장소에서 관리하도록 연결했습니다.
- 설치 패키지를 MSI로 통일하고 전용 설치·복구·제거 UI를 추가했습니다.
- UI와 Custom Action DLL을 분리하고 설치 화면 초기화 진단을 보완했습니다.
- Windows CI에서 설치 UI 로딩과 네이티브 래퍼·MSI 빌드를 검사합니다.
- 릴리스 변경 기록을 MD 파일과 GitHub 릴리스 설명에 자동으로 남깁니다.

### 커밋

- ci: publish new MSI versions automatically after successful main builds ([565451f](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/565451f0779a7a00488483c02742dd3b33d2eac1))
- feat: play an alert once when detected games enter the pending list ([610a2c2](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/610a2c2fc8b66250ab618ff32d84d560cdd3ce6e))
- Remove outdated information from README.md ([ecde489](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/ecde489d87c49dad391cf147f1e8400eb79caea1))
- fix: read both CHZZK build credentials from Actions secrets ([f92f4a0](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/f92f4a0960ae96e6f14328f8bfa297b5f9f7285a))
- Update chzzk_open.py ([13a45da](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/13a45dac15665a738647947395e8acf55d291f1e))
- test: compare resolved native paths in Windows MSI checks ([4e58f94](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/4e58f9458a48edd51296f5c92870731055a2a575))
- feat: add 4.11.4 MSI source, Windows CI, and automatic release Markdown ([c206ab6](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/c206ab651899012c68b86e8b836e1e5482a358cb))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/4.11.3...v4.11.4)

### 설치 파일

- `ChzzkAutoCategory-4.11.4.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## 이전 배포

저장소에 소스가 등록되기 전 배포 내역은 [GitHub Releases](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases)에서 확인할 수 있습니다.
