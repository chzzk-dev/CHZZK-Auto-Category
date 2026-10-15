# 변경 기록

릴리스를 게시하면 이 파일에 버전, 한국 시간 기준 날짜, 변경 사항과 커밋 링크가 자동으로 기록됩니다.
배포 전 사용자에게 설명할 내용은 아래 `미배포` 항목에 추가할 수 있습니다.

## 미배포

- 데스크톱 기본 창을 1440×960으로 확대하고 대시보드 카드 간격과 비율을 정리합니다.
- 자동화·프로그램 설정을 2열 카드와 왼쪽 설명/오른쪽 컨트롤 구조로 개편합니다.
- 체크박스를 키보드 조작을 지원하는 좌우 토글로 바꾸고 버튼·선택창·스크롤바 스타일을 통일합니다.
- 설정 저장 버튼을 화면 하단에 고정해 스크롤 위치와 관계없이 저장할 수 있게 합니다.
- 공식 API를 필수 사용으로 고정하고 빌드 인증 정보로 앱 시작 시 연결 상태를 자동 확인합니다. 인증 정보가 없는 빌드는 상태를 명확히 안내합니다.

## [4.12.4](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.4) — 2026-10-15 (KST)

### 변경 사항

- 롤토체스 빠른 선택에서 TFT 카테고리의 시즌 부제(콜론 뒤 이름) 때문에 연결에 실패하던 문제를 수정합니다.
- 기본 이름으로 검색하고 비교하되 실제 검색 결과의 카테고리 ID와 전체 이름을 저장합니다.
- 다른 게임이나 서로 다른 ID의 후보가 여러 개면 임의로 연결하지 않습니다.

### 커밋

- Match TFT seasonal category subtitles in quick selection for stable 4.12.4 ([7ef7c71](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/7ef7c717e7f615d49d765a723bf2e55e63bb7eb8))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.3...v4.12.4)

### 설치 파일

- `ChzzkAutoCategory-4.12.4.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.3](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.3) — 2026-10-14 (KST)

### 변경 사항

- 게임 설정을 게임 이름·방송 카테고리·사용 버튼 중심의 간편 창으로 바꿉니다.
- 롤/롤토체스는 두 버튼으로 선택하고 실제 검색 결과를 확인한 뒤 연결을 저장합니다.
- 기술 정보와 별칭·실행 파일·연결 방식 변경은 접힌 고급 설정으로 이동합니다.
- 게임 행 클릭은 선택만 수행하며 간편 설정 버튼 또는 더블클릭으로 설정 창을 엽니다.

### 커밋

- Simplify game setup and add verified one-click LoL or TFT selection for 4.12.3 ([d6275f0](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/d6275f095b6aaedca9aa00dda968eb82c4f86963))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.2...v4.12.3)

### 설치 파일

- `ChzzkAutoCategory-4.12.3.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.2](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.2) — 2026-10-14 (KST)

### 변경 사항

- 롤/TFT 모드 확인 대기를 중복 항목으로 삭제한 뒤 재등록하던 문제를 수정합니다.
- 같은 게임을 감지할 때 정리 로그와 확인 알림이 반복되지 않도록 합니다.
- 게임 종료 또는 수동 연결 시 대기 항목을 정상 정리하며, 근거 없는 롤/TFT 자동 선택은 방지합니다.

### 커밋

- Fix repeated cleanup and re-registration of LoL/TFT mode prompts in 4.12.2 ([a154a34](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/a154a34baa77668708c99593960e7be7d25515ac))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.1...v4.12.2)

### 설치 파일

- `ChzzkAutoCategory-4.12.2.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.1](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.1) — 2026-10-14 (KST)

### 변경 사항

- 쿠키앤크림 스타일의 크림 배경·다크그레이 카드·두꺼운 흰 테두리로 데스크톱 UI를 전면 개편합니다.
- 대시보드를 큰 게임 패널, 오른쪽 연결·자동화 패널, 하단 감지·카테고리·활동 패널로 재배치합니다.
- 메뉴·게임 목록·설정·연결·로그·팝업과 지원 아이콘의 스타일 및 대비를 통일합니다.
- 기존 감지·자동 변경·확장 연결·사용자 설정은 유지합니다.
- 4.12.1은 정식 최신 릴리스로 배포하며 기존 안정 버전의 업데이트 확인 대상에 포함됩니다.

### 커밋

- Publish cookie-and-cream desktop redesign as stable 4.12.1 ([d2fdb4b](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/d2fdb4bfca8abc3d784d17f2a777fdd127e351f6))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.12.0...v4.12.1)

### 설치 파일

- `ChzzkAutoCategory-4.12.1.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

## [4.12.0](https://github.com/chzzk-dev/CHZZK-Auto-Category/releases/tag/v4.12.0) — 2026-10-14 (KST)

### 변경 사항

- 밝은 설치 UI와 공통 테마/아이콘을 사용하는 대시보드·게임 목록·자동화·연결·설정·로그 6개 페이지로 개편합니다.
- 게임별 검색·검증 상태와 적용 대기를 분리하며 수동 규칙, 시리즈/버전 구분, 종료된 게임의 지연 결과 차단을 강화합니다.
- Discord ID와 사용자 별칭을 유지하고 검증 캐시를 재사용합니다. LoL/TFT는 실행 파일만으로 추측하지 않습니다.
- 확장프로그램 0.6.0에서 실제 manifest 버전·프로토콜·heartbeat를 전달하며 오래된 응답과 중복 요청을 차단합니다.
- 앱 업데이트는 기본 3시간, 카테고리 동기화는 기본 6시간이며 두 자동 주기의 최소값은 1시간입니다.
- 설정 마이그레이션 원본 백업, 순환 로그와 민감 정보 마스킹, 단일 업데이터 잠금 및 실패 후 기존 앱 재실행 경로를 추가합니다.
- Windows CI에 Qt DPI 렌더링과 실제 보호 EXE의 오프라인 아이콘 검사를 추가합니다. 기존 MSI 설치·업그레이드·제거 검증은 유지합니다.
- 4.12.0은 사전 릴리스 후보입니다. GitHub 반영과 게시에는 사용자 승인이 필요하며 Chrome Web Store 게시와는 별개입니다.

### 커밋

- Redesign desktop UI and strengthen verified category automation for 4.12.0 ([49e59fc](https://github.com/chzzk-dev/CHZZK-Auto-Category/commit/49e59fcc1ba7497736feb713b602c3702feefd08))

[전체 변경 비교](https://github.com/chzzk-dev/CHZZK-Auto-Category/compare/v4.11.5...v4.12.0)

### 설치 파일

- `ChzzkAutoCategory-4.12.0.msi`
- `SHA256SUMS.txt`에서 설치 파일의 SHA-256을 확인할 수 있습니다.
- 기존 MSI 설치본은 새 MSI로 업그레이드하며 사용자 설정을 유지합니다.

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
